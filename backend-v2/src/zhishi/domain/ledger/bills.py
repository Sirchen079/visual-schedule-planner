"""Pending obligations and explicit, atomic settlement into the actual ledger."""
# ruff: noqa: DTZ005, DTZ011
# v2 stores local calendar dates and naive timestamps.
import calendar
import json
from datetime import date, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from zhishi.domain.ledger import service as ledger
from zhishi.domain.ledger.bill_schemas import (
    BillCreate,
    BillDetails,
    BillHistory,
    BillOccurrenceRead,
    BillPage,
    BillPayment,
    BillRead,
    BillSkip,
    BillUpdate,
)
from zhishi.domain.ledger.schemas import EntryCreate
from zhishi.domain.models import Bill, BillOccurrence, NotificationLog


def due_at(first: date, cycle: str, sequence: int) -> date | None:
    if sequence == 0:
        return first
    if cycle == 'once':
        return None
    if cycle == 'weekly':
        return first + timedelta(weeks=sequence)
    months = sequence * (12 if cycle == 'yearly' else 1)
    year, month = divmod(first.year * 12 + first.month - 1 + months, 12)
    return date(year, month + 1, min(first.day, calendar.monthrange(year, month + 1)[1]))


def _json(payload) -> str:
    values = payload.model_dump(mode='json')
    if getattr(payload, 'amount', None) is not None:
        values['amount'] = format(payload.amount.normalize(), 'f')
    return json.dumps(values, ensure_ascii=False, sort_keys=True)


def _details(payload) -> BillDetails:
    return BillDetails.model_validate(payload.model_dump(include=set(BillDetails.model_fields)))


def get(db: Session, bill_id: int) -> Bill:
    row = db.get(Bill, bill_id, populate_existing=True)
    if row is None:
        raise LookupError('账单不存在')
    return row


def _occurrence(db: Session, occurrence_id: int) -> BillOccurrence:
    row = db.get(BillOccurrence, occurrence_id, populate_existing=True)
    if row is None:
        raise LookupError('这期账单不存在')
    return row


def occurrence_read(db: Session, row: BillOccurrence) -> BillOccurrenceRead:
    entry = ledger.get_entry(db, row.ledger_entry_id) if row.ledger_entry_id else None
    return BillOccurrenceRead(id=row.id, bill_id=row.bill_id, sequence=row.sequence,
        due=row.due, details=BillDetails.model_validate_json(row.spec_json),
        status=row.status, version=row.version,
        ledger_entry=ledger.to_read(entry) if entry else None,
        resolution=json.loads(row.resolution_json) if row.resolution_json else None,
        resolved_at=row.resolved_at)


def read_occurrence(db: Session, occurrence_id: int) -> BillOccurrenceRead:
    return occurrence_read(db, _occurrence(db, occurrence_id))


def read(db: Session, bill_id: int) -> BillRead:
    row = get(db, bill_id)
    pending = db.scalar(select(BillOccurrence).where(
        BillOccurrence.bill_id == bill_id, BillOccurrence.status == 'pending'))
    return BillRead(id=row.id, first_due=row.first_due, cycle=row.cycle, version=row.version,
        details=BillDetails.model_validate_json(row.spec_json),
        pending=occurrence_read(db, pending) if pending else None)


def list_bills(db: Session, *, limit: int = 20, offset: int = 0) -> BillPage:
    if not 1 <= limit <= 50 or offset < 0:
        raise ValueError('分页参数无效')
    total = db.scalar(select(func.count()).select_from(Bill)) or 0
    ids = db.scalars(select(Bill.id).order_by(Bill.enabled.desc(), Bill.id.desc()).offset(offset).limit(limit))
    return BillPage(items=[read(db, i) for i in ids], total=total, offset=offset, limit=limit)


def history(db: Session, bill_id: int, before: int | None = None, limit: int = 20) -> BillHistory:
    get(db, bill_id)
    if not 1 <= limit <= 20 or (before is not None and before <= 0):
        raise ValueError('分页参数无效')
    clauses = [BillOccurrence.bill_id == bill_id]
    if before is not None:
        clauses.append(BillOccurrence.id < before)
    rows = list(db.scalars(select(BillOccurrence).where(*clauses)
        .order_by(BillOccurrence.id.desc()).limit(limit + 1)))
    return BillHistory(items=[occurrence_read(db, r) for r in rows[:limit]],
        next_before=rows[limit - 1].id if len(rows) > limit else None)


def create(db: Session, payload: BillCreate) -> BillRead:
    fingerprint = _json(payload)
    result = db.execute(insert(Bill).values(spec_json=_json(_details(payload)),
        first_due=payload.first_due, cycle=payload.cycle, enabled=payload.enabled,
        request_key=payload.request_key, original_payload=fingerprint).on_conflict_do_nothing(
        index_elements=['request_key']))
    row = db.scalar(select(Bill).where(Bill.request_key == payload.request_key))
    if row.original_payload != fingerprint:
        db.rollback()
        raise ledger.LedgerConflict('同一账单请求已有不同内容，请读取并修改原账单')
    if result.rowcount:
        db.add(BillOccurrence(bill_id=row.id, sequence=0, due=row.first_due, spec_json=row.spec_json))
    db.commit()
    return read(db, row.id)


def replace(db: Session, bill_id: int, payload: BillUpdate) -> BillRead:
    get(db, bill_id)
    spec = _json(_details(payload))
    result = db.execute(update(Bill).where(Bill.id == bill_id, Bill.version == payload.version)
        .values(spec_json=spec, enabled=payload.enabled, version=Bill.version + 1))
    if result.rowcount != 1:
        db.rollback()
        raise ledger.LedgerConflict('账单已变更，请重新读取账单和版本')
    # Resolved periods retain the exact details in effect when they were settled.
    db.execute(update(BillOccurrence).where(BillOccurrence.bill_id == bill_id,
        BillOccurrence.status == 'pending').values(spec_json=spec, version=BillOccurrence.version + 1))
    db.commit()
    return read(db, bill_id)


def _claim(db: Session, row: BillOccurrence, version: int) -> Bill:
    # Serialize against edits to the recurring definition as well as other settlements.
    db.execute(update(Bill).where(Bill.id == row.bill_id).values(version=Bill.version + 1))
    result = db.execute(update(BillOccurrence).where(BillOccurrence.id == row.id,
        BillOccurrence.version == version, BillOccurrence.status.in_(['pending', 'skipped']))
        .values(version=BillOccurrence.version + 1))
    if result.rowcount != 1:
        db.rollback()
        raise ledger.LedgerConflict('本期账单已变更，请重新读取后确认')
    return get(db, row.bill_id)


def _advance(db: Session, bill: Bill, row: BillOccurrence) -> None:
    due = due_at(bill.first_due, bill.cycle, row.sequence + 1)
    if due is not None:
        db.execute(insert(BillOccurrence).values(bill_id=bill.id, sequence=row.sequence + 1,
            due=due, spec_json=bill.spec_json).on_conflict_do_nothing(index_elements=['bill_id', 'sequence']))


def pay(db: Session, occurrence_id: int, payload: BillPayment) -> BillOccurrenceRead:
    row = _occurrence(db, occurrence_id)
    data = payload.model_dump(exclude={'version'}, mode='json')
    # Normalize decimal spelling for exact replay (28.5 and 28.50).
    data['amount'] = str(payload.amount.normalize())
    fingerprint = json.dumps(data, ensure_ascii=False, sort_keys=True)
    if row.status == 'paid':
        if row.resolution_json != fingerprint:
            raise ledger.LedgerConflict('本期已支付且内容不同；请读取关联账目，勿再次记账')
        return occurrence_read(db, row)
    was_pending = row.status == 'pending'
    spec = BillDetails.model_validate_json(row.spec_json)
    entry = EntryCreate(day=payload.day, direction='expense', amount=payload.amount,
        currency=spec.currency, category=spec.category, account=payload.account, payee=spec.payee,
        notes=f'{spec.title} · 到期 {row.due}\n{spec.notes}'.strip(),
        source_file_id=payload.source_file_id, source_excerpt=payload.source_excerpt,
        idempotency_key=f'bill-occurrence:{row.id}')
    if payload.day > date.today():
        raise ValueError('支付日期不能在未来；未支付金额保留为待办账单')
    try:
        bill = _claim(db, row, payload.version)
        if payload.existing_entry_id:
            target = ledger.get_entry(db, payload.existing_entry_id)
            if (target.deleted_at or target.direction != 'expense' or target.day != payload.day
                    or target.amount_minor != entry.amount_minor or target.currency != spec.currency
                    or target.account != payload.account):
                raise ValueError('关联账目必须是未删除的支出，且日期、金额、币种和账户与确认内容一致')
            used = db.scalar(select(BillOccurrence.id).where(BillOccurrence.ledger_entry_id == target.id))
            if used:
                raise ledger.LedgerConflict('这笔支出已关联其他账单期次')
        else:
            target = ledger.create_entry(db, entry, commit=False)
        row.status = 'paid'
        row.ledger_entry_id = target.id
        row.resolution_json = fingerprint
        row.resolved_at = datetime.now()
        if was_pending:
            _advance(db, bill, row)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return occurrence_read(db, _occurrence(db, occurrence_id))


def skip(db: Session, occurrence_id: int, payload: BillSkip) -> BillOccurrenceRead:
    row = _occurrence(db, occurrence_id)
    if row.status == 'skipped' and json.loads(row.resolution_json)['reason'] == payload.reason:
        return occurrence_read(db, row)
    if row.status != 'pending':
        raise ledger.LedgerConflict('仅待支付账单可跳过；请读取最新期次')
    try:
        bill = _claim(db, row, payload.version)
        row.status = 'skipped'
        row.resolution_json = json.dumps({'reason': payload.reason}, ensure_ascii=False)
        row.resolved_at = datetime.now()
        _advance(db, bill, row)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return occurrence_read(db, _occurrence(db, occurrence_id))


def remind(db: Session, now: datetime | None = None) -> int:
    now = now or datetime.now()
    created = 0
    rows = db.execute(select(BillOccurrence, Bill).join(Bill).where(
        Bill.enabled.is_(True), BillOccurrence.status == 'pending'))
    for row, bill in rows:
        spec = BillDetails.model_validate_json(row.spec_json)
        due = datetime.combine(row.due, datetime.min.time()).replace(hour=9)
        ahead = due - timedelta(days=spec.remind_days)
        if now < ahead:
            continue
        # Serialize with payment/pause/edit; a scan based on an old read must not notify.
        claim = db.execute(update(Bill).where(Bill.id == bill.id, Bill.version == bill.version,
            Bill.enabled.is_(True)).values(enabled=True))
        if claim.rowcount != 1:
            continue
        stage, point = ('due', due) if now >= due else ('ahead', ahead)
        label = '已到期，请核对是否支付' if now >= due else '即将到期'
        amount = f'{spec.amount} {spec.currency}' if spec.amount is not None else '金额待确认'
        result = db.execute(insert(NotificationLog).values(kind='bill_reminder',
            title=spec.title, body=f'{spec.title} · {label}（{row.due} · {amount}）',
            target_path=f'/ledger?bill={bill.id}', remind_at=point,
            dedupe_key=f'bill:{row.id}:{stage}').on_conflict_do_nothing(index_elements=['dedupe_key']))
        created += result.rowcount
    db.commit()
    return created
