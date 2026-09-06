# src/zhishi/server/routes/ical.py
from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from zhishi.domain import ical
from zhishi.server.deps import get_db

router = APIRouter(prefix="/api/ical", tags=["ical"])


class IcalImportOut(BaseModel):
    """ICS 导入回包（re #048）：created=新建日程数。"""
    created: int


@router.get("/export", response_class=Response,
            responses={200: {"description": "ICS 日历文本（text/calendar）",
                             "content": {"text/calendar": {
                                 "schema": {"type": "string"}}}}})
def export(db: Session = Depends(get_db)):
    """response_class=Response（media_type None）：openapi 不再自动误标
    application/json 空 schema，200 只声明 text/calendar（re #048）。"""
    return Response(content=ical.export_ics(db), media_type="text/calendar",
                    headers={"Content-Disposition": 'attachment; filename="zhishi-calendar.ics"',
                             "Cache-Control": "no-store"})


@router.post("/import", response_model=IcalImportOut)
def import_ics(file: UploadFile, db: Session = Depends(get_db)):
    content = file.file.read().decode("utf-8")
    created = ical.import_ics(db, content)
    return {"created": created}
