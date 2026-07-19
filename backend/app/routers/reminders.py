from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import TaskResponse
from app.services import notification_service, reminder_service

router = APIRouter(prefix="/reminders", tags=["reminders"])


@router.get("/due")
def due(hours: int = 24, db: Session = Depends(get_db)):
    upcoming, overdue = reminder_service.due_reminders(db, hours)
    triggered = reminder_service.triggered_reminders(db)
    # 到点提醒幂等落库（通知中心可回溯）；写库失败不影响提醒主流程
    try:
        notification_service.log_triggered(db, triggered)
    except Exception:
        db.rollback()
    return {
        "upcoming": [TaskResponse.model_validate(t).model_dump(mode="json") for t in upcoming],
        "overdue": [TaskResponse.model_validate(t).model_dump(mode="json") for t in overdue],
        # 到点提醒（按 remind_offsets 命中当前时刻的提醒项，前端按 task.id+remind_at 去重通知）
        "triggered": [
            {
                "task": TaskResponse.model_validate(item["task"]).model_dump(mode="json"),
                "remind_at": item["remind_at"].isoformat(),
                "due_at": item["due_at"].isoformat(),
                "offset_minutes": item["offset_minutes"],
            }
            for item in triggered
        ],
    }
