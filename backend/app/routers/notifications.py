from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import NotificationResponse, NotificationUnreadCount
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationResponse])
def list_notifications(limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    return notification_service.list_notifications(db, limit)


@router.get("/unread-count", response_model=NotificationUnreadCount)
def get_unread_count(db: Session = Depends(get_db)):
    return {"unread": notification_service.unread_count(db)}


@router.post("/{notification_id}/read", response_model=NotificationResponse)
def mark_read(notification_id: int, db: Session = Depends(get_db)):
    entry = notification_service.mark_read(db, notification_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="通知不存在")
    return entry


@router.post("/read-all")
def mark_all_read(db: Session = Depends(get_db)):
    return {"marked": notification_service.mark_all_read(db)}
