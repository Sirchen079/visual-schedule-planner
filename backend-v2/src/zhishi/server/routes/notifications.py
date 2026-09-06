from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from zhishi.domain import notifications as service
from zhishi.server.deps import get_db
from zhishi.server.routes.ai import EnableOut

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    """通知响应模型。task_id/read_at 可空，
    read_at 为 null 即未读；remind_at/read_at 序列化为 ISO 串（与既有回包一致）。"""
    id: int
    task_id: int | None = None
    kind: str
    title: str
    body: str
    remind_at: datetime
    read_at: datetime | None = None
    target_path: str | None = None


class UnreadOut(BaseModel):
    """未读数（前端 30s 轮询依据）。"""
    count: int


@router.get("", response_model=list[NotificationOut])
def list_notifications(limit: int = 50, db: Session = Depends(get_db)):
    return [{"id": n.id, "task_id": n.task_id, "kind": n.kind, "title": n.title,
             "body": n.body, "remind_at": n.remind_at, "read_at": n.read_at,
             "target_path": n.target_path or None}
            for n in service.list_notifications(db, limit=limit)]


@router.get("/unread", response_model=UnreadOut)
def unread(db: Session = Depends(get_db)):
    return {"count": service.unread_count(db)}


@router.post("/{notification_id}/read", response_model=EnableOut,
             response_model_exclude_none=True)   # 回 {"ok": true}，无 enabled 键（实形守恒）
def mark_read(notification_id: int, db: Session = Depends(get_db)):
    service.mark_read(db, notification_id)
    return {"ok": True}


@router.post("/read-all", response_model=EnableOut,
             response_model_exclude_none=True)   # 同上
def mark_all_read(db: Session = Depends(get_db)):
    service.mark_read(db)
    return {"ok": True}
