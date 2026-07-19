"""确定性统计分析 API：不依赖 AI，直接由任务/用量数据聚合。

与 ai_report_service 的区别：那里是为模型报告收集 prompt 素材；
这里是给前端仪表盘提供结构化统计数据（趋势、分布、token 用量）。
"""
from __future__ import annotations

from datetime import datetime, time, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AIConfig, AIUsageLog, Tag, Task
from app.services import risk_service
from app.schemas import (
    RiskItem,
    RiskResponse,
    StatsByPriorityResponse,
    StatsByTagResponse,
    StatsDailyPoint,
    StatsDailyResponse,
    StatsPriorityItem,
    StatsSummary,
    StatsTagItem,
    TokenUsageDay,
    TokenUsageModel,
    TokenUsageResponse,
)

router = APIRouter(prefix="/stats", tags=["stats"])

ACTIVE_STATUSES = ("待办", "进行中", "完成")


def _active_tasks(db: Session) -> list[Task]:
    return list(
        db.execute(select(Task).where(Task.deleted_at.is_(None))).scalars().all()
    )


@router.get("/summary", response_model=StatsSummary)
def summary(db: Session = Depends(get_db)):
    """当前存量概览：状态计数 + 时效分桶（逾期/今日/未来 7 天）。"""
    today = datetime.now().date()
    week_end = today + timedelta(days=7)
    by_status = {s: 0 for s in ACTIVE_STATUSES}
    overdue = due_today = due_this_week = 0
    tasks = _active_tasks(db)
    for t in tasks:
        by_status[t.status] = by_status.get(t.status, 0) + 1
        if t.status == "完成" or not t.due_date:
            continue
        d = t.due_date.date()
        if d < today:
            overdue += 1
        elif d == today:
            due_today += 1
        if today <= d <= week_end:
            due_this_week += 1
    return StatsSummary(
        total=len(tasks),
        by_status=by_status,
        overdue=overdue,
        due_today=due_today,
        due_this_week=due_this_week,
        completed_total=by_status.get("完成", 0),
    )


@router.get("/daily", response_model=StatsDailyResponse)
def daily(days: int = Query(90, ge=1, le=365), db: Session = Depends(get_db)):
    """每日完成数（按 completed_at）与新增数（按 created_at），含无数据的日期补零。"""
    today = datetime.now().date()
    start = today - timedelta(days=days - 1)
    completed_map: dict = {}
    created_map: dict = {}
    for t in _active_tasks(db):
        if t.completed_at:
            d = t.completed_at.date()
            if start <= d <= today:
                completed_map[d] = completed_map.get(d, 0) + 1
        if t.created_at:
            d = t.created_at.date()
            if start <= d <= today:
                created_map[d] = created_map.get(d, 0) + 1
    points = []
    for i in range(days):
        d = start + timedelta(days=i)
        points.append(
            StatsDailyPoint(
                date=d,
                completed=completed_map.get(d, 0),
                created=created_map.get(d, 0),
            )
        )
    return StatsDailyResponse(days=points)


@router.get("/by-tag", response_model=StatsByTagResponse)
def by_tag(db: Session = Depends(get_db)):
    """标签维度：各标签的任务总数与完成数（只列有任务的标签，按总数降序）。"""
    tags = list(db.execute(select(Tag).order_by(Tag.name)).scalars().all())
    items = []
    for tag in tags:
        active = [t for t in tag.tasks if t.deleted_at is None]
        if not active:
            continue
        items.append(
            StatsTagItem(
                name=tag.name,
                color=tag.color,
                total=len(active),
                completed=sum(1 for t in active if t.status == "完成"),
            )
        )
    items.sort(key=lambda i: i.total, reverse=True)
    return StatsByTagResponse(tags=items)


@router.get("/by-priority", response_model=StatsByPriorityResponse)
def by_priority(db: Session = Depends(get_db)):
    """优先级 × 状态矩阵。"""
    order = ["高", "中", "低"]
    groups: dict[str, dict[str, int]] = {
        p: {s: 0 for s in ACTIVE_STATUSES} for p in order
    }
    for t in _active_tasks(db):
        bucket = groups.setdefault(t.priority, {s: 0 for s in ACTIVE_STATUSES})
        bucket[t.status] = bucket.get(t.status, 0) + 1
    items = [
        StatsPriorityItem(priority=p, by_status=groups[p], total=sum(groups[p].values()))
        for p in order
    ]
    return StatsByPriorityResponse(priorities=items)


@router.get("/risk", response_model=RiskResponse)
def risk(db: Session = Depends(get_db)):
    """逾期风险预测：确定性规则打分，返回分数最高的前 10 个未完成任务。"""
    return RiskResponse(
        items=[RiskItem(**item) for item in risk_service.compute_risk(db, limit=10)]
    )


@router.get("/token-usage", response_model=TokenUsageResponse)
def token_usage(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)):
    """AI token 用量：按日序列 + 按模型汇总 + 按配置价目估算成本。

    total_tokens 为 0 的记录说明接口未返回 usage（untracked），单独计数提示。
    """
    today = datetime.now().date()
    start = today - timedelta(days=days - 1)
    start_dt = datetime.combine(start, time.min)
    logs = list(
        db.execute(select(AIUsageLog).where(AIUsageLog.created_at >= start_dt))
        .scalars()
        .all()
    )
    price_map = {
        c.id: (float(c.price_input or 0), float(c.price_output or 0))
        for c in db.execute(select(AIConfig)).scalars().all()
    }
    day_map: dict = {}
    model_map: dict = {}
    untracked = 0
    for log in logs:
        d = log.created_at.date()
        bucket = day_map.setdefault(d, [0, 0, 0])
        bucket[0] += log.prompt_tokens
        bucket[1] += log.completion_tokens
        bucket[2] += log.total_tokens
        if log.total_tokens == 0:
            untracked += 1
        key = (log.model or "未知模型", log.provider or "")
        m = model_map.setdefault(
            key,
            {"call_count": 0, "prompt": 0, "completion": 0, "total": 0,
             "cost": 0.0, "priced": False},
        )
        m["call_count"] += 1
        m["prompt"] += log.prompt_tokens
        m["completion"] += log.completion_tokens
        m["total"] += log.total_tokens
        price = price_map.get(log.config_id)
        if price and (price[0] or price[1]):
            m["priced"] = True
            m["cost"] += (
                log.prompt_tokens / 1_000_000 * price[0]
                + log.completion_tokens / 1_000_000 * price[1]
            )
    full_days = []
    for i in range(days):
        d = start + timedelta(days=i)
        v = day_map.get(d, [0, 0, 0])
        full_days.append(
            TokenUsageDay(
                date=d, prompt_tokens=v[0], completion_tokens=v[1], total_tokens=v[2]
            )
        )
    models = [
        TokenUsageModel(
            model=model,
            provider=provider,
            call_count=m["call_count"],
            prompt_tokens=m["prompt"],
            completion_tokens=m["completion"],
            total_tokens=m["total"],
            estimated_cost=round(m["cost"], 4) if m["priced"] else None,
        )
        for (model, provider), m in sorted(
            model_map.items(), key=lambda kv: kv[1]["total"], reverse=True
        )
    ]
    any_priced = any(m["priced"] for m in model_map.values())
    return TokenUsageResponse(
        days=full_days,
        models=models,
        total_prompt_tokens=sum(m["prompt"] for m in model_map.values()),
        total_completion_tokens=sum(m["completion"] for m in model_map.values()),
        total_tokens=sum(m["total"] for m in model_map.values()),
        total_estimated_cost=(
            round(sum(m["cost"] for m in model_map.values()), 4) if any_priced else None
        ),
        untracked_calls=untracked,
    )
