# src/zhishi/server/routes/reports.py
"""AI 报告端点：日报/周报生成（失败 422）、报告列表/详情/删除、晨报（同日幂等 + 规则降级）。"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from zhishi.domain import reports
from zhishi.domain.models import AIReport
from zhishi.server.deps import get_db
from zhishi.server.routes.ai import _enabled_config

router = APIRouter(prefix="/ai", tags=["ai"])


class ReportBody(BaseModel):
    target_date: date | None = None   # 缺省 = 今天


class ReportOut(BaseModel):
    """报告实形（re #047：前端 Report 手写类型收敛依据）。
    period_start/end 为 ISO 日期串、created_at 为 ISO 时间串——与 _out() 既有回包一致。"""
    id: int
    report_type: str
    period_start: str                       # YYYY-MM-DD
    period_end: str                         # YYYY-MM-DD
    title: str
    content: str
    model_name: str                         # "rule" = 规则降级文案
    created_at: str                         # ISO datetime


def _out(r: AIReport) -> dict:
    return {"id": r.id, "report_type": r.report_type,
            "period_start": r.period_start.isoformat(),
            "period_end": r.period_end.isoformat(),
            "title": r.title, "content": r.content, "model_name": r.model_name,
            "created_at": r.created_at.isoformat()}


@router.post("/reports/{report_type}", response_model=ReportOut)
def create_report(report_type: str, body: ReportBody | None = None,
                  db: Session = Depends(get_db)):
    cfg = _enabled_config(db)   # 无启用配置 → 400
    target = body.target_date if (body and body.target_date) else date.today()
    try:
        row = reports.generate(db, cfg, report_type, target)
    except ValueError as exc:          # report_type 非法 / 缺 API key
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:           # 网络/网关/模型失败 → 统一 422
        raise HTTPException(422, f"报告生成失败：{exc}") from exc
    return _out(row)


@router.get("/reports", response_model=list[ReportOut])
def list_reports(report_type: str | None = None, limit: int = 50,
                 db: Session = Depends(get_db)):
    stmt = select(AIReport).order_by(AIReport.id.desc()).limit(max(1, min(limit, 200)))
    if report_type:
        stmt = stmt.where(AIReport.report_type == report_type)
    return [_out(r) for r in db.scalars(stmt)]


@router.get("/briefing/today", response_model=ReportOut)
def today_briefing(db: Session = Depends(get_db)):
    """幂等取当日晨报；无配置或 AI 失败自动降级规则文案，恒 200。"""
    return _out(reports.get_or_create_briefing(db, reports.enabled_config(db), date.today()))


@router.get("/reports/{report_id}", response_model=ReportOut)
def report_detail(report_id: int, db: Session = Depends(get_db)):
    row = db.get(AIReport, report_id)
    if row is None:
        raise HTTPException(404, "报告不存在")
    return _out(row)


@router.delete("/reports/{report_id}", status_code=204)
def delete_report(report_id: int, db: Session = Depends(get_db)):
    row = db.get(AIReport, report_id)
    if row is None:
        raise HTTPException(404, "报告不存在")
    db.delete(row)
    db.commit()
