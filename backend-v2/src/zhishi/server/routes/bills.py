# ruff: noqa: B008
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from zhishi.domain.ledger import bills
from zhishi.domain.ledger.bill_schemas import (
    BillCreate,
    BillHistory,
    BillOccurrenceRead,
    BillPage,
    BillPayment,
    BillRead,
    BillSkip,
    BillUpdate,
)
from zhishi.server.deps import get_db
from zhishi.server.routes.ledger import _call

router = APIRouter(prefix='/api/bills', tags=['bills'])


@router.get('', response_model=BillPage)
def list_bills(limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0),
               db: Session = Depends(get_db)):
    return _call(bills.list_bills, db, limit=limit, offset=offset)


@router.post('', response_model=BillRead, status_code=201)
def create(payload: BillCreate, db: Session = Depends(get_db)):
    return _call(bills.create, db, payload)


@router.get('/{bill_id}', response_model=BillRead)
def read(bill_id: int, db: Session = Depends(get_db)):
    return _call(bills.read, db, bill_id)


@router.put('/{bill_id}', response_model=BillRead)
def replace(bill_id: int, payload: BillUpdate, db: Session = Depends(get_db)):
    return _call(bills.replace, db, bill_id, payload)


@router.get('/{bill_id}/history', response_model=BillHistory)
def history(bill_id: int, before: int | None = Query(None, gt=0), db: Session = Depends(get_db)):
    return _call(bills.history, db, bill_id, before)


@router.post('/occurrences/{occurrence_id}/pay', response_model=BillOccurrenceRead)
def pay(occurrence_id: int, payload: BillPayment, db: Session = Depends(get_db)):
    return _call(bills.pay, db, occurrence_id, payload)


@router.get('/occurrences/{occurrence_id}', response_model=BillOccurrenceRead)
def read_occurrence(occurrence_id: int, db: Session = Depends(get_db)):
    return _call(bills.read_occurrence, db, occurrence_id)


@router.post('/occurrences/{occurrence_id}/skip', response_model=BillOccurrenceRead)
def skip(occurrence_id: int, payload: BillSkip, db: Session = Depends(get_db)):
    return _call(bills.skip, db, occurrence_id, payload)
