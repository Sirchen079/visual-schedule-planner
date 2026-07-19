from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from fastapi import File as UploadFileParam
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.schemas import TaskCreate
from app.services import ical_service, task_service

router = APIRouter(tags=["ical"])


@router.get("/export/tasks.ics")
def export_tasks(db: Session = Depends(get_db)):
    """导出全部未删除任务为 .ics 日历文件。"""
    tasks = task_service.list_tasks(db)
    content = ical_service.export_tasks(tasks)
    return Response(
        content=content.encode("utf-8"),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="zhishi-tasks.ics"'},
    )


@router.post("/import/tasks.ics")
async def import_tasks(file: UploadFile = UploadFileParam(...), db: Session = Depends(get_db)):
    """从 .ics 文件导入任务（VEVENT → 任务）。返回创建/跳过计数。"""
    max_bytes = settings.max_ical_bytes
    raw = await file.read()
    if len(raw) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大（上限 {settings.max_ical_mb}MB）",
        )
    try:
        content = raw.decode("utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(status_code=400, detail="文件编码无法识别") from exc
    parsed = ical_service.parse_ical(content)
    if not parsed:
        raise HTTPException(status_code=400, detail="未在文件中找到可导入的日程（VEVENT）")
    created = 0
    for item in parsed:
        task_service.create_task(db, TaskCreate(**item))
        created += 1
    return {"created": created, "skipped": 0}
