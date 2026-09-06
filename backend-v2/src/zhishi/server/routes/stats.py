from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from zhishi.domain import stats
from zhishi.domain.stats import (StatsDailyPoint, StatsPriorityItem, StatsSummary,
                                 StatsTagItem, RiskItem)
from zhishi.server.deps import get_db

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/summary", response_model=StatsSummary)
def summary(db: Session = Depends(get_db)):
    return stats.summary(db)


@router.get("/daily", response_model=list[StatsDailyPoint])
def daily(days: int = 14, db: Session = Depends(get_db)):
    return stats.daily(db, days=days)


@router.get("/by-tag", response_model=list[StatsTagItem])
def by_tag(db: Session = Depends(get_db)):
    return stats.by_tag(db)


@router.get("/by-priority", response_model=list[StatsPriorityItem])
def by_priority(db: Session = Depends(get_db)):
    return stats.by_priority(db)


@router.get("/risk", response_model=list[RiskItem])
def risk(limit: int = 10, db: Session = Depends(get_db)):
    return stats.risk(db, limit=limit)
