"""Exact bookkeeping with replay protection, optimistic edits and recoverable deletion."""
import json
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from zhishi.domain.ledger.schemas import (
    DIGITS,
    CategoryTotal,
    CurrencyTotal,
    EntryCreate,
    EntryData,
    EntryPage,
    EntryRead,
    LedgerSummary,
)
from zhishi.domain.models import LedgerEntry, LibraryFile


class LedgerConflict(ValueError):
    pass


def money(minor: int, currency: str) -> str:
    return f"{Decimal(minor).scaleb(-DIGITS[currency]):.{DIGITS[currency]}f}"


def to_read(row: LedgerEntry) -> EntryRead:
    fields = {name: getattr(row, name) for name in EntryRead.model_fields if name != "amount"}
    return EntryRead(**fields, amount=money(row.amount_minor, row.currency))


def get_entry(db: Session, entry_id: int) -> LedgerEntry:
    row = db.get(LedgerEntry, entry_id, populate_existing=True)
    if row is None:
        raise LookupError("账目不存在")
    return row


def _values(payload: EntryData) -> dict:
    values = payload.model_dump(exclude={"amount", "idempotency_key", "version"})
    return {**values, "amount_minor": payload.amount_minor}


def _source(db: Session, file_id: int | None) -> None:
    if file_id is not None:
        source = db.get(LibraryFile, file_id)
        if source is None or source.deleted_at is not None:
            raise ValueError("来源附件不存在或已在回收站")


def create_entry(db: Session, payload: EntryCreate, *, commit: bool = True) -> LedgerEntry:
    values = _values(payload)
    fingerprint = json.dumps(values, ensure_ascii=False, sort_keys=True, default=str)

    def existing():
        if not payload.idempotency_key:
            return None
        row = db.scalar(select(LedgerEntry).where(
            LedgerEntry.idempotency_key == payload.idempotency_key))
        if row is not None and row.original_payload != fingerprint:
            raise LedgerConflict("同一记账凭据已有不同内容，请读取原账目后修改")
        return row

    row = existing()
    if row is not None:
        return row  # A retry never resurrects or overwrites an edited/deleted entry.
    _source(db, payload.source_file_id)
    row = LedgerEntry(**values, idempotency_key=payload.idempotency_key,
                      original_payload=fingerprint)
    db.add(row)
    if not commit:
        db.flush()
        return row  # Caller owns rollback and commit, including the inbox state transition.
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        row = existing()  # unique key also handles concurrent retries
        if row is None:
            raise
    db.refresh(row)
    return row


def _mutate(db: Session, entry_id: int, version: int, values: dict,
            *, deleted: bool) -> LedgerEntry:
    get_entry(db, entry_id)
    condition = LedgerEntry.deleted_at.is_not(None) if deleted else LedgerEntry.deleted_at.is_(None)
    result = db.execute(update(LedgerEntry).where(
        LedgerEntry.id == entry_id, LedgerEntry.version == version, condition,
    ).values(**values, updated_at=datetime.now(), version=LedgerEntry.version + 1))  # noqa: DTZ005 -- v2 stores local naive timestamps
    if result.rowcount != 1:
        db.rollback()
        raise LedgerConflict("账目已变更或回收状态不符，请刷新后重试")
    db.commit()
    return get_entry(db, entry_id)


def replace_entry(db: Session, entry_id: int, payload: EntryData, version: int) -> LedgerEntry:
    _source(db, payload.source_file_id)
    return _mutate(db, entry_id, version, _values(payload), deleted=False)


def delete_entry(db: Session, entry_id: int, version: int) -> LedgerEntry:
    return _mutate(db, entry_id, version, {"deleted_at": datetime.now()}, deleted=False)  # noqa: DTZ005 -- v2 timestamp convention


def restore_entry(db: Session, entry_id: int, version: int) -> LedgerEntry:
    return _mutate(db, entry_id, version, {"deleted_at": None}, deleted=True)


def _filters(start: date | None, end: date | None, currency: str | None,
             account: str | None, deleted: bool = False):
    if start and end and start > end:
        raise ValueError("起始日期不能晚于结束日期")
    clauses = [LedgerEntry.deleted_at.is_not(None) if deleted else LedgerEntry.deleted_at.is_(None)]
    if start:
        clauses.append(LedgerEntry.day >= start)
    if end:
        clauses.append(LedgerEntry.day <= end)
    if currency:
        clauses.append(LedgerEntry.currency == currency)
    if account:
        clauses.append(LedgerEntry.account == account)
    return clauses


def list_entries(db: Session, *, start: date | None = None, end: date | None = None,
                 currency: str | None = None, account: str | None = None,
                 direction: str | None = None, query: str = "", deleted: bool = False,
                 limit: int = 50, offset: int = 0) -> EntryPage:
    if not 1 <= limit <= 200 or offset < 0:
        raise ValueError("分页参数无效")
    clauses = _filters(start, end, currency, account, deleted)
    if direction:
        clauses.append(LedgerEntry.direction == direction)
    if query:
        clauses.append(or_(*(column.contains(query, autoescape=True) for column in (
            LedgerEntry.category, LedgerEntry.payee, LedgerEntry.notes))))
    total = db.scalar(select(func.count()).select_from(LedgerEntry).where(*clauses))
    rows = db.scalars(select(LedgerEntry).where(*clauses).order_by(
        LedgerEntry.day.desc(), LedgerEntry.id.desc()).offset(offset).limit(limit))
    return EntryPage(items=[to_read(r) for r in rows], total=total, limit=limit, offset=offset)


def summary(db: Session, start: date, end: date, *, currency: str | None = None,
            account: str | None = None) -> LedgerSummary:
    groups: dict[str, dict] = {}
    # Python integer sums cannot overflow; never mix currencies or use float arithmetic.
    rows = db.execute(select(LedgerEntry.currency, LedgerEntry.direction,
        LedgerEntry.category, LedgerEntry.amount_minor).where(*_filters(start, end, currency, account)))
    for curr, direction, category, amount in rows:
        group = groups.setdefault(curr, {"income": 0, "expense": 0, "count": 0, "categories": {}})
        group[direction] += amount
        group["count"] += 1
        cat = group["categories"].setdefault((direction, category), [0, 0])
        cat[0] += amount
        cat[1] += 1
    return LedgerSummary(start=start, end=end, currencies=[CurrencyTotal(
        currency=curr, income=money(g["income"], curr), expense=money(g["expense"], curr),
        net=money(g["income"] - g["expense"], curr), count=g["count"],
        categories=[CategoryTotal(direction=direction, category=category,
            amount=money(amount, curr), count=count)
            for (direction, category), (amount, count) in sorted(g["categories"].items())],
    ) for curr, g in sorted(groups.items())])
