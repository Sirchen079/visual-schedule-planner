from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import pytest
from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from zhishi.domain.inbox import service as inbox
from zhishi.domain.inbox.schemas import CaptureBatch, Revision
from zhishi.domain.library import service as library
from zhishi.domain.models import Event, InboxItem, LedgerEntry, Task


def batch(fid=None, **changes):
    item = dict(source_file_id=fid, item_key="receipt-total", source_excerpt="实付28.50元",
                proposal={"kind": "ledger", "data": {"day": "2026-09-05", "direction": "expense", "amount": "28.50"}})
    item.update(changes)
    return CaptureBatch(capture_key="test-capture", items=[item])


def test_renamed_uploads_share_source_and_processed_result(db, tmp_path):
    root = tmp_path / "attachments"
    first = library.save_upload(db, storage_root=root, upload=UploadFile(filename="receipt.txt", file=BytesIO(b"paid 28.50")))
    second = library.save_upload(db, storage_root=root, upload=UploadFile(filename="renamed.txt", file=BytesIO(b"paid 28.50")))
    assert first.id != second.id and first.content_sha256 == second.content_sha256
    one = inbox.capture(db, batch(first.id))[0]
    two = inbox.capture(db, batch(second.id))[0]
    assert one.id == two.id
    assert db.scalar(select(func.count()).select_from(LedgerEntry)) == 0
    applied = inbox.apply_item(db, one.id, one.version)
    assert applied.target_state == "active"
    assert inbox.apply_item(db, one.id, one.version).target_id == applied.target_id
    assert inbox.capture(db, batch(second.id))[0].status == "applied"
    assert inbox.list_items(db, status=None, source_file_id=second.id).total == 1
    assert db.scalar(select(func.count()).select_from(LedgerEntry)) == 1
    library.purge(db, first.id, storage_root=root)
    assert inbox.to_read(db, inbox.get_item(db, one.id)).source_excerpt == "实付28.50元"
    assert (root.parent / second.storage_path).is_file()


def test_uncertainty_revision_rejection_and_stale_apply(db):
    row = inbox.capture(db, batch(uncertainty="付款日期待确认"))[0]
    with pytest.raises(inbox.InboxConflict, match="澄清"):
        inbox.apply_item(db, row.id, row.version)
    revised = inbox.revise(db, row.id, Revision(version=row.version, proposal=row.proposal))
    with pytest.raises(inbox.InboxConflict):
        inbox.apply_item(db, row.id, row.version)
    rejected = inbox.reject(db, row.id, revised.version)
    with pytest.raises(inbox.InboxConflict):
        inbox.apply_item(db, row.id, rejected.version)
    reopened = inbox.revise(db, row.id, Revision(version=rejected.version, proposal=row.proposal))
    assert inbox.apply_item(db, row.id, reopened.version).status == "applied"


def test_deleted_applied_target_is_reported_without_recreation(db):
    from zhishi.domain.ledger import service
    row = inbox.capture(db, batch())[0]
    applied = inbox.apply_item(db, row.id, row.version)
    service.delete_entry(db, applied.target_id, version=1)
    assert inbox.apply_item(db, row.id, row.version).target_state == 'deleted'
    assert service.list_entries(db).total == 0
    assert service.list_entries(db, deleted=True).total == 1


def test_failed_target_rolls_back_claim_and_target(db, monkeypatch):
    from zhishi.domain.ledger import service
    row = inbox.capture(db, batch())[0]
    original = service.create_entry
    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("simulated interruption before inbox commit")
    monkeypatch.setattr(service, "create_entry", fail)
    with pytest.raises(RuntimeError):
        inbox.apply_item(db, row.id, row.version)
    assert inbox.get_item(db, row.id).status == "pending"
    assert db.scalar(select(func.count()).select_from(LedgerEntry)) == 0
    monkeypatch.setattr(service, "create_entry", original)
    assert inbox.apply_item(db, row.id, row.version).status == "applied"


def test_concurrent_apply_creates_one_target(db):
    row = inbox.capture(db, batch())[0]
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    def apply(_):
        with factory() as session:
            return inbox.apply_item(session, row.id, row.version).target_id
    with ThreadPoolExecutor(max_workers=4) as executor:
        ids = list(executor.map(apply, range(8)))
    assert len(set(ids)) == 1
    assert db.scalar(select(func.count()).select_from(LedgerEntry)) == 1


def test_task_event_and_ledger_material_and_atomic_batch(db):
    items = [
        {"item_key": "p1-line1", "source_excerpt": "提交报告", "proposal": {"kind": "task", "data": {"title": "提交报告", "tag_names": ["研究"]}}},
        {"item_key": "p1-line2", "source_excerpt": "9月6日10点会面", "proposal": {"kind": "event", "data": {"title": "会面", "date": "2026-09-06", "start_time": "10:00", "end_time": "11:00"}}},
    ]
    rows = inbox.capture(db, CaptureBatch(capture_key="mixed", items=items))
    for row in rows:
        inbox.apply_item(db, row.id, row.version)
    assert db.scalar(select(Task)).title == "提交报告"
    assert db.scalar(select(Event)).title == "会面"
    before = db.scalar(select(func.count()).select_from(InboxItem))
    invalid = CaptureBatch(capture_key="rollback", items=[items[0], {**items[1], "source_file_id": 99999}])
    with pytest.raises(ValueError):
        inbox.capture(db, invalid)
    assert db.scalar(select(func.count()).select_from(InboxItem)) == before
