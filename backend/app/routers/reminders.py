from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import TaskResponse
from app.services import reminder_service

router = APIRouter(prefix="/reminders", tags=["reminders"])


@router.get("/due")
def due(hours: int = 24, db: Session = Depends(get_db)):
    upcoming, overdue = reminder_service.due_reminders(db, hours)
    return {
        "upcoming": [TaskResponse.model_validate(t).model_dump(mode="json") for t in upcoming],
        "overdue": [TaskResponse.model_validate(t).model_dump(mode="json") for t in overdue],
    }
