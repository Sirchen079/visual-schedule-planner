from datetime import date

import pytest
from pydantic import ValidationError

from zhishi.domain.ledger import service as ledger
from zhishi.domain.ledger.schemas import EntryCreate, EntryData
from zhishi.domain.models import LibraryFile

DAY = date(2026, 9, 5)


def entry(**kw):
    return EntryCreate(day=DAY, direction="expense", **{"amount": "0.10", **kw})


@pytest.mark.parametrize("amount", ["0", "-1", "0.001", "NaN", "Infinity",
    "1000000000", "0.100000000000000000000000000001"])
def test_invalid_money_rejected_without_rounding(amount):
    with pytest.raises(ValidationError):
        entry(amount=amount)


def test_exact_totals_and_currency_separation(db):
    ledger.create_entry(db, entry())
    ledger.create_entry(db, entry(amount="0.20"))
    ledger.create_entry(db, entry(amount="3.45", currency="USD"))
    ledger.create_entry(db, EntryCreate(day=DAY, direction="income", amount="10.00"))
    report = ledger.summary(db, DAY, DAY)
    cny, usd = report.currencies
    assert (cny.currency, cny.expense, cny.income, cny.net, cny.count) == (
        "CNY", "0.30", "10.00", "9.70", 3)
    assert usd.expense == "3.45" and usd.net == "-3.45"
    assert ledger.create_entry(db, entry(amount="125", currency="JPY")).amount_minor == 125
    with pytest.raises(ValidationError):
        entry(amount="125.10", currency="JPY")


def test_idempotency_edit_delete_restore_and_stale_version(db):
    payload = entry(idempotency_key="receipt:one:0")
    row = ledger.create_entry(db, payload)
    assert ledger.create_entry(db, entry(amount="0.100", idempotency_key="receipt:one:0")).id == row.id
    with pytest.raises(ledger.LedgerConflict):
        ledger.create_entry(db, entry(amount="0.20", idempotency_key="receipt:one:0"))
    replacement = EntryData(day=DAY, direction="expense", amount="2.50", category="餐饮")
    changed = ledger.replace_entry(db, row.id, replacement, 1)
    assert changed.version == 2 and changed.amount_minor == 250
    assert ledger.create_entry(db, payload).amount_minor == 250
    with pytest.raises(ledger.LedgerConflict):
        ledger.delete_entry(db, row.id, 1)
    deleted = ledger.delete_entry(db, row.id, 2)
    assert ledger.summary(db, DAY, DAY).currencies == []
    assert ledger.create_entry(db, payload).deleted_at is not None
    assert ledger.list_entries(db, deleted=True).total == 1
    restored = ledger.restore_entry(db, row.id, deleted.version)
    assert restored.version == 4 and restored.deleted_at is None
    assert ledger.summary(db, DAY, DAY).currencies[0].expense == "2.50"


def test_file_provenance_survives_source_removal(db):
    with pytest.raises(ValueError, match="来源附件"):
        ledger.create_entry(db, entry(source_file_id=999))
    source = LibraryFile(original_name="收据.png", storage_path="attachments/receipt.png", size=10)
    db.add(source); db.commit()
    row = ledger.create_entry(db, entry(source_file_id=source.id, source_excerpt="实付 0.10 元"))
    db.delete(source); db.commit()
    refreshed = ledger.get_entry(db, row.id)
    assert refreshed.source_file_id is None and refreshed.source_excerpt == "实付 0.10 元"


def test_date_account_filter_pagination_and_literal_search(db):
    ledger.create_entry(db, entry(account="现金", notes="餐饮 10%"))
    ledger.create_entry(db, entry(account="银行卡", notes="其他"))
    assert ledger.list_entries(db, account="现金").total == 1
    assert ledger.list_entries(db, query="%").total == 1
    page = ledger.list_entries(db, limit=1, offset=1)
    assert page.total == 2 and len(page.items) == 1
    assert ledger.summary(db, DAY, DAY, account="现金").currencies[0].expense == "0.10"
    assert ledger.list_entries(db, start=date(2026, 9, 6)).total == 0
    with pytest.raises(ValueError):
        ledger.summary(db, date(2026, 9, 6), DAY)


def test_concurrent_replay_creates_one_entry(db):
    from concurrent.futures import ThreadPoolExecutor

    from sqlalchemy.orm import sessionmaker
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    def record(_):
        with factory() as session:
            return ledger.create_entry(session, entry(idempotency_key="same-receipt")).id
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(record, range(8)))
    assert len(set(ids)) == 1
    assert ledger.list_entries(db).total == 1
