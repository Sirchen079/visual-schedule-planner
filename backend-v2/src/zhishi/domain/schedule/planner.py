# src/zhishi/domain/schedule/planner.py
"""确定性日调度器（Motion 心法：LLM 管意图、算法管调度）。
排序：逾期>高优>截止近>创建早；装入工作时段空闲块，尊重每日容量。"""
from __future__ import annotations
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
from zhishi.domain import settingsvc
from zhishi.domain.schedule.conflicts import _timed_items, free_intervals
from zhishi.domain.schedule.service import day_schedule
from zhishi.domain.tasks import service as ts


def _to_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _priority_rank(p: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(p, 1)


def plan_day(db: Session, day: date) -> dict:
    """只读：为 day 生成建议排期（不写库）。返回 assignments/unassigned/capacity。"""
    working = settingsvc.working_hours(db)
    capacity = settingsvc.daily_capacity_minutes(db)
    lo, hi = _to_min(working[0]), _to_min(working[1])
    busy = sorted((_to_min(i["start_time"]), _to_min(i["end_time"]))
                  for i in _timed_items(db, day))
    blocks = free_intervals(lo, hi, busy)
    booked = day_schedule(db, day)["tasks"]
    booked_ids = {t["task_id"] for t in booked}
    consumed = sum(max(t.get("estimated_minutes") or 0,
        _to_min(t["end_time"]) - _to_min(t["start_time"])
        if t.get("start_time") and t.get("end_time") else 0) for t in booked)

    now = datetime.now()
    tasks = [t for t in ts.list_tasks(db, status="todo")
             if t.id not in booked_ids and (t.due_date is None or t.due_date.date() <= day + timedelta(days=3))]
    tasks.sort(key=lambda t: (
        0 if (t.due_date and t.due_date < now) else 1,
        _priority_rank(t.priority),
        t.due_date or datetime.max,
        t.id))
    assignments, unassigned = [], []
    for t in tasks:
        need = t.estimated_minutes or 60
        remaining = capacity - consumed - sum(a["estimated_minutes"] for a in assignments)
        if need > remaining:
            unassigned.append({"task_id": t.id, "title": t.title,
                               "reason": "超出当日容量", "estimated_minutes": need})
            continue
        placed = False
        for block_idx, (b0, b1) in enumerate(blocks):
            if b1 - b0 >= need:
                start, end = b0, b0 + need
                blocks[block_idx] = (b0 + need, b1)
                assignments.append({
                    "task_id": t.id, "title": t.title, "estimated_minutes": need,
                    "start": f"{start // 60:02d}:{start % 60:02d}",
                    "end": f"{end // 60:02d}:{end % 60:02d}"})
                placed = True
                break
        if not placed:
            unassigned.append({"task_id": t.id, "title": t.title,
                               "reason": "无连续空闲时段", "estimated_minutes": need})
    return {"date": day.isoformat(), "assignments": assignments,
            "unassigned": unassigned, "capacity_minutes": capacity}
