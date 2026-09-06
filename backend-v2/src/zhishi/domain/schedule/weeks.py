# src/zhishi/domain/schedule/weeks.py
"""学期周次 → RRULE 引擎（课表导入的确定性核心）。
semester_start 必须是第 1 周的周一；weekday 1=周一..7=周日。
week_kind: range=连续周 / odd=单周(奇数学期周) / even=双周(偶数周)。"""
from __future__ import annotations
from datetime import date, timedelta

_BYDAY = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


def _week_monday(semester_start: date, week: int) -> date:
    return semester_start + timedelta(weeks=week - 1)


def _sunday(semester_start: date, week: int) -> date:
    return _week_monday(semester_start, week) + timedelta(days=6)


def repeat_note(week_kind: str, start_week: int, end_week: int) -> str:
    """周次规则的人类可读描述（re #020 事项2）：单周课（第1-16周）/ 双周课（第2-16周）/ 每周（第1-16周）。"""
    label = {"odd": "单周课", "even": "双周课"}.get(week_kind, "每周")
    return f"{label}（第{start_week}-{end_week}周）"


def week_spec_to_event(*, title: str, weekday: int, week_kind: str,
                       start_week: int, end_week: int,
                       semester_start: date) -> dict:
    """返回 {title, date(首次出现), recur_rrule, repeat_note}。校验失败抛 ValueError。"""
    if not 1 <= weekday <= 7:
        raise ValueError(f"weekday 必须在 1-7，收到 {weekday}")
    if start_week < 1 or end_week < start_week:
        raise ValueError(f"周次区间非法: {start_week}-{end_week}")
    byday = _BYDAY[weekday - 1]
    until = _sunday(semester_start, end_week).strftime("%Y%m%d")

    if week_kind in ("odd", "even"):
        parity = 1 if week_kind == "odd" else 0
        first = next(w for w in range(start_week, end_week + 1) if w % 2 == parity)
        anchor = _week_monday(semester_start, first) + timedelta(days=weekday - 1)
        rrule = f"FREQ=WEEKLY;INTERVAL=2;BYDAY={byday};UNTIL={until}"
    elif week_kind == "range":
        anchor = _week_monday(semester_start, start_week) + timedelta(days=weekday - 1)
        rrule = f"FREQ=WEEKLY;BYDAY={byday};UNTIL={until}" if end_week > start_week else None
    else:
        raise ValueError(f"未知 week_kind: {week_kind}")
    return {"title": title, "date": anchor, "recur_rrule": rrule,
            "repeat_note": repeat_note(week_kind, start_week, end_week)}
