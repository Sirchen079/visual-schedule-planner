import hashlib
import json
from datetime import datetime

from pydantic import TypeAdapter
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from zhishi.domain.inbox.schemas import CaptureBatch, InboxPage, InboxRead, Proposal, Revision
from zhishi.domain.ledger.schemas import EntryCreate
from zhishi.domain.models import Event, InboxItem, LedgerEntry, LibraryFile, Task

_proposal = TypeAdapter(Proposal)


class InboxConflict(ValueError):
    def __init__(self, message: str, item_id: int | None = None):
        super().__init__(message)
        self.item_id = item_id


def get_item(db: Session, item_id: int) -> InboxItem:
    row = db.get(InboxItem, item_id, populate_existing=True)
    if row is None:
        raise LookupError("收件箱条目不存在")
    return row


def to_read(db: Session, row: InboxItem) -> InboxRead:
    target_state = None
    if row.status == "applied":
        target = db.get({"task": Task, "event": Event, "ledger": LedgerEntry}[row.kind], row.target_id)
        target_state = "missing" if target is None else "deleted" if getattr(target, "deleted_at", None) else "active"
    return InboxRead(id=row.id, source_file_id=row.source_file_id, source_name=row.source_name,
        source_excerpt=row.source_excerpt, item_key=row.item_key,
        proposal=_proposal.validate_json(row.payload_json), uncertainty=row.uncertainty,
        status=row.status, version=row.version, target_id=row.target_id, target_state=target_state,
        created_at=row.created_at, updated_at=row.updated_at)


def _json(proposal) -> str:
    return json.dumps(proposal.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def capture(db: Session, batch: CaptureBatch) -> list[InboxRead]:
    """All drafts are saved together. Source content + stable location survives renamed uploads."""
    def stage():
        rows = []
        for item in batch.items:
            name = "文字输入"
            material = f"text:{batch.capture_key}"
            if item.source_file_id is not None:
                file = db.get(LibraryFile, item.source_file_id)
                if file is None or file.deleted_at is not None:
                    raise ValueError("来源附件不存在或已删除")
                if not file.content_sha256:
                    raise ValueError("请先用 import_document 读取附件，再整理候选条目")
                name, material = file.original_name, f"sha256:{file.content_sha256}"
            key = f"{material}:{item.item_key}"
            payload = _json(item.proposal)
            row = db.scalar(select(InboxItem).where(InboxItem.source_key == key))
            if row is not None:
                # An applied/rejected item stays processed, even if the model rewrites its wording.
                if row.status == "pending" and (_json(_proposal.validate_json(row.payload_json)) != payload
                                                or row.uncertainty != item.uncertainty):
                    raise InboxConflict(f"同一材料位置已有候选 #{row.id}，请读取后修改，不要另建", row.id)
            else:
                row = InboxItem(source_key=key, source_file_id=item.source_file_id,
                    source_name=name, source_excerpt=item.source_excerpt, item_key=item.item_key,
                    kind=item.proposal.kind, payload_json=payload, uncertainty=item.uncertainty)
                db.add(row)
                db.flush()
            if row not in rows:
                rows.append(row)
        return rows
    for attempt in range(2):
        try:
            rows = stage()
            db.commit()
            return [to_read(db, row) for row in rows]
        except IntegrityError:
            db.rollback()
            if attempt:
                raise
        except Exception:
            db.rollback()
            raise
    raise RuntimeError("无法保存候选条目")


def list_items(db: Session, status: str | None = "pending", source_file_id: int | None = None,
               limit: int = 50, offset: int = 0) -> InboxPage:
    if not 1 <= limit <= 200 or offset < 0:
        raise ValueError("分页参数无效")
    clauses = []
    if status:
        if status not in ("pending", "applied", "rejected"):
            raise ValueError("收件箱状态无效")
        clauses.append(InboxItem.status == status)
    if source_file_id:
        file = db.get(LibraryFile, source_file_id)
        if file and file.content_sha256:
            clauses.append(InboxItem.source_key.startswith(f"sha256:{file.content_sha256}:"))
        else:
            clauses.append(InboxItem.source_file_id == source_file_id)
    total = db.scalar(select(func.count()).select_from(InboxItem).where(*clauses))
    rows = db.scalars(select(InboxItem).where(*clauses).order_by(InboxItem.id.desc()).offset(offset).limit(limit))
    return InboxPage(items=[to_read(db, row) for row in rows], total=total)


def _change(db: Session, row: InboxItem, version: int, values: dict):
    result = db.execute(update(InboxItem).where(InboxItem.id == row.id,
        InboxItem.version == version, InboxItem.status != "applied").values(
            **values, version=InboxItem.version + 1, updated_at=datetime.now()))  # noqa: DTZ005 — v2 stores local wall time
    if result.rowcount != 1:
        db.rollback()
        raise InboxConflict("条目已变更或已应用，请刷新后操作", row.id)
    db.commit()
    return to_read(db, get_item(db, row.id))


def revise(db: Session, item_id: int, revision: Revision) -> InboxRead:
    row = get_item(db, item_id)
    return _change(db, row, revision.version, {"kind": revision.proposal.kind,
        "payload_json": _json(revision.proposal), "uncertainty": revision.uncertainty.strip(),
        "status": "pending"})


def reject(db: Session, item_id: int, version: int) -> InboxRead:
    return _change(db, get_item(db, item_id), version, {"status": "rejected"})


def apply_item(db: Session, item_id: int, version: int) -> InboxRead:
    row = get_item(db, item_id)
    if row.status == "applied" and row.version == version + 1:
        return to_read(db, row)
    if row.status != "pending" or row.version != version:
        raise InboxConflict("条目已变更或不在待确认状态，请刷新后操作", item_id)
    if row.uncertainty.strip():
        raise InboxConflict("仍有待澄清的信息，请编辑候选、解决疑问后再应用", item_id)
    draft = _proposal.validate_json(row.payload_json)
    try:
        claimed = db.execute(update(InboxItem).where(InboxItem.id == item_id,
            InboxItem.version == version, InboxItem.status == "pending").values(
                status="applied", version=version + 1, updated_at=datetime.now()))  # noqa: DTZ005 — v2 stores local wall time
        if claimed.rowcount != 1:
            db.rollback()
            fresh = get_item(db, item_id)
            if fresh.status == "applied" and fresh.version == version + 1:
                return to_read(db, fresh)
            raise InboxConflict("条目已变更，请刷新后操作", item_id)
        if draft.kind == "task":
            from zhishi.domain.tasks.service import create_task
            target = create_task(db, draft.data, commit=False)
            source = db.get(LibraryFile, row.source_file_id) if row.source_file_id else None
            if source is not None and source.deleted_at is None:
                target.files.append(source)
        elif draft.kind == "event":
            from zhishi.domain.schedule.service import create_event
            target = create_event(db, commit=False, **draft.data.model_dump())
        else:
            from zhishi.domain.ledger.service import create_entry
            values = draft.data.model_dump()
            source = db.get(LibraryFile, row.source_file_id) if row.source_file_id else None
            values.update(source_file_id=source.id if source and not source.deleted_at else None,
                          source_excerpt=row.source_excerpt[:4000])
            target = create_entry(db, EntryCreate(**values,
                idempotency_key="inbox:" + hashlib.sha256(row.source_key.encode()).hexdigest()), commit=False)
        row.target_id = target.id
        db.commit()
    except Exception:
        db.rollback()
        raise
    return to_read(db, get_item(db, item_id))
