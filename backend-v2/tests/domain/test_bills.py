# ruff: noqa: DTZ001 -- explicit local dates match the application's calendar convention.
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from zhishi.domain.ledger import bills
from zhishi.domain.ledger import service as ledger
from zhishi.domain.ledger.bill_schemas import BillCreate, BillPayment, BillSkip, BillUpdate
from zhishi.domain.ledger.schemas import EntryCreate, EntryData
from zhishi.domain.models import BillOccurrence, NotificationLog


def new(db, **kw):
    return bills.create(db, BillCreate(**{'title':'房租','amount':'2000.00',
        'first_due':'2026-01-31','request_key':'rent', **kw}))


def payment(row, **kw):
    return BillPayment(**{'version':row.version, 'day':'2026-01-31',
        'amount':'2000', 'account':'默认账户', **kw})


def test_fixed_anchor_month_end_leap_year_and_one_time():
    assert [bills.due_at(date(2026,1,31),'monthly',n) for n in range(4)] == [
        date(2026,1,31),date(2026,2,28),date(2026,3,31),date(2026,4,30)]
    assert bills.due_at(date(2024,2,29),'yearly',4) == date(2028,2,29)
    assert bills.due_at(date(2024,2,29),'yearly',1) == date(2025,2,28)
    assert bills.due_at(date(2026,1,31),'weekly',1) == date(2026,2,7)
    assert bills.due_at(date(2026,1,31),'once',1) is None
    with pytest.raises(ValidationError):
        BillCreate(title='日元', amount='1.01', currency='JPY', first_due='2026-01-31', request_key='j')


def test_pending_does_not_enter_actual_ledger_and_payment_replay_preserves_edits(db):
    bill = new(db)
    assert new(db).id == bill.id
    assert ledger.list_entries(db).total == 0
    p = payment(bill.pending)
    paid = bills.pay(db, bill.pending.id, p)
    assert paid.status == 'paid' and paid.ledger_entry.amount_minor == 200000
    assert bills.read(db,bill.id).pending.due == date(2026,2,28)
    assert bills.pay(db, bill.pending.id, p).ledger_entry.id == paid.ledger_entry.id
    entry = ledger.replace_entry(db,paid.ledger_entry.id,EntryData(day=date(2026,1,31),
        direction='expense',amount='1900'),1)
    ledger.delete_entry(db,entry.id,entry.version)
    replay = bills.pay(db,bill.pending.id,p)
    assert replay.ledger_entry.deleted_at and replay.ledger_entry.amount == '1900.00'
    assert ledger.list_entries(db).total == 0 and ledger.list_entries(db,deleted=True).total == 1
    with pytest.raises(ledger.LedgerConflict):
        bills.pay(db,bill.pending.id,payment(bill.pending,amount='2100'))
    assert len(bills.history(db,bill.id).items) == 2


def test_edit_conflict_history_preservation_pause_and_skip_later_payment(db):
    bill = new(db)
    skipped = bills.skip(db,bill.pending.id,BillSkip(version=1,reason='本期免租'))
    assert bills.skip(db,bill.pending.id,BillSkip(version=1,reason='本期免租')).id == skipped.id
    current = bills.read(db,bill.id)
    changed = bills.replace(db,bill.id,BillUpdate(**{**current.details.model_dump(),
        'version':current.version,'title':'新租金','amount':'2100','enabled':False}))
    assert changed.pending.details.amount == 2100
    assert bills.history(db,bill.id).items[-1].details.amount == 2000
    with pytest.raises(ledger.LedgerConflict):
        bills.replace(db,bill.id,BillUpdate(**bill.details.model_dump(),version=1))
    assert bills.remind(db,datetime(2026,2,28,10)) == 0
    with pytest.raises(ledger.LedgerConflict):
        bills.pay(db,current.pending.id,payment(current.pending))
    paid = bills.pay(db,skipped.id,payment(skipped))
    assert paid.status == 'paid'
    assert bills.read(db,bill.id).pending.id == changed.pending.id
    assert len(bills.history(db,bill.id).items) == 2


def test_link_existing_entry_and_failure_rolls_back_claim(db):
    a = new(db,cycle='once')
    entry = ledger.create_entry(db,EntryCreate(day=date(2026,1,31),direction='expense',amount='2000'))
    with pytest.raises(ValueError):
        bills.pay(db,a.pending.id,payment(a.pending,existing_entry_id=entry.id,amount='1'))
    assert bills.read(db,a.id).version == 1
    paid = bills.pay(db,a.pending.id,payment(a.pending,existing_entry_id=entry.id))
    assert paid.ledger_entry.id == entry.id and ledger.list_entries(db).total == 1
    assert bills.read(db,a.id).pending is None
    b = new(db,request_key='other')
    with pytest.raises(ledger.LedgerConflict):
        bills.pay(db,b.pending.id,payment(b.pending,existing_entry_id=entry.id))
    assert bills.read(db,b.id).pending.status == 'pending'
    with pytest.raises(ValueError):
        bills.pay(db,b.pending.id,payment(b.pending,source_file_id=999))
    assert bills.read(db,b.id).version == 1


def test_reminder_dedup_restart_catchup_pause_and_no_paid_notifications(db):
    bill = new(db)
    assert bills.remind(db,datetime(2026,1,27,9)) == 0
    assert bills.remind(db,datetime(2026,1,28,9)) == 1
    assert bills.remind(db,datetime(2026,1,30,9)) == 0
    assert bills.remind(db,datetime(2026,1,31,9)) == 1
    assert bills.remind(db,datetime(2026,3,1,9)) == 0
    paid = bills.pay(db,bill.pending.id,payment(bill.pending))
    assert bills.remind(db,datetime(2026,3,1,9)) == 1
    assert bills.remind(db,datetime(2026,3,1,9)) == 0
    logs = list(db.scalars(select(NotificationLog)))
    assert all(r.target_path == f'/ledger?bill={bill.id}' for r in logs)
    assert all(r.kind == 'bill_reminder' for r in logs)
    assert paid.ledger_entry and db.scalar(select(func.count()).select_from(BillOccurrence)) == 2


def test_concurrent_creation_and_settlement_are_exactly_once(db):
    factory = sessionmaker(bind=db.get_bind(),expire_on_commit=False)
    def create(_):
        with factory() as s:
            return new(s).id
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert len(set(pool.map(create,range(8)))) == 1
    bill = bills.list_bills(db).items[0]
    def pay(_):
        with factory() as s:
            try:
                return bills.pay(s,bill.pending.id,payment(bill.pending)).status
            except ledger.LedgerConflict:
                return 'conflict'
    with ThreadPoolExecutor(max_workers=4) as pool:
        result = list(pool.map(pay,range(8)))
    assert 'paid' in result
    assert ledger.list_entries(db).total == 1
    assert len(bills.history(db,bill.id).items) == 2


def test_transaction_failure_after_entry_creation_rolls_back_everything(db, monkeypatch):
    bill = new(db)
    def fail(*args):
        raise RuntimeError('injected failure after ledger flush')
    with monkeypatch.context() as m:
        m.setattr(bills,'_advance',fail)
        with pytest.raises(RuntimeError,match='injected'):
            bills.pay(db,bill.pending.id,payment(bill.pending))
    assert ledger.list_entries(db).total == 0
    unchanged = bills.read(db,bill.id)
    assert unchanged.version == 1 and unchanged.pending.version == 1
    assert bills.pay(db,bill.pending.id,payment(bill.pending)).status == 'paid'


def test_history_pagination_and_exact_tool_recovery(db):
    import json

    from zhishi.agent.tools import bill_tools
    bill = new(db,first_due='2020-01-31')
    for i in range(24):
        current = bills.read(db,bill.id)
        bills.skip(db,current.pending.id,BillSkip(version=current.pending.version,reason=f'测试免付{i}'))
    first = bills.history(db,bill.id)
    second = bills.history(db,bill.id,first.next_before)
    assert len(first.items) == 20 and len(second.items) == 5 and second.next_before is None
    assert len({r.id for r in first.items + second.items}) == 25
    oldest = second.items[-1]
    failed = json.loads(bill_tools.confirm_bill_payment(db,oldest.id,payment(oldest,version=1)))
    assert failed['code'] == 'bill_conflict'
    assert failed['next_call'] == {'tool':'get_bill_occurrence','args':{'occurrence_id':oldest.id}}
    assert json.loads(bill_tools.get_bill_occurrence(db,oldest.id))['status'] == 'skipped'
    assert len(json.loads(bill_tools.get_bill_history(db,bill.id))['items']) == 5
