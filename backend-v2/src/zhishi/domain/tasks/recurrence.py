# src/zhishi/domain/tasks/recurrence.py
"""重复规则推进：简单枚举 + RFC5545 RRULE（dateutil）。
规则：从原截止推进；结果早于 after 则继续推进（补卡不生成已逾期实例）。"""
from __future__ import annotations
import calendar
from datetime import datetime, timedelta
from dateutil.rrule import rrulestr


def _step(due: datetime, rule: str, interval: int) -> datetime:
    if rule == "daily":
        return due + timedelta(days=interval)
    if rule == "weekdays":
        nxt = due + timedelta(days=interval)
        while nxt.weekday() >= 5:
            nxt += timedelta(days=1)
        return nxt
    if rule == "weekly":
        return due + timedelta(weeks=interval)
    if rule == "monthly":
        month_index = due.month - 1 + interval
        year = due.year + month_index // 12
        month = month_index % 12 + 1
        day = min(due.day, calendar.monthrange(year, month)[1])
        return due.replace(year=year, month=month, day=day)
    raise ValueError(f"未知重复规则: {rule}")


def advance_occurrence(due: datetime, rule: str, interval: int,
                       after: datetime | None = None) -> datetime | None:
    if rule == "none":
        return None
    after = after or datetime.combine(datetime.now().date(), datetime.min.time())
    if due.tzinfo is not None or after.tzinfo is not None:
        due, after = due.replace(tzinfo=None), after.replace(tzinfo=None)
    nxt = _step(due, rule, max(1, interval))
    while nxt < after:
        nxt = _step(nxt, rule, max(1, interval))
    return nxt


def next_rrule_occurrence(rrule_text: str, after: datetime) -> datetime | None:
    """RRULE 下一次出现（不含 after 本身）。无 DTSTART 时以 after 为锚。
    相位锚定：先把 after 就近对齐到规则的第一个匹配出现（忽略 INTERVAL 的探针），
    再以该锚点按原规则推进——周中查询与"锚点即真实出现日"两种场景都正确。"""
    after = after.replace(tzinfo=None)
    try:
        rule = rrulestr(rrule_text, dtstart=after)
    except ValueError:
        return None
    parts = ";".join(p for p in rrule_text.upper().split(";") if not p.startswith("INTERVAL"))
    anchor = None
    if parts:
        try:
            probe = rrulestr(parts, dtstart=after)
            anchor = probe.after(after, inc=True)
        except ValueError:
            anchor = None
    if anchor is not None:
        rule = rrulestr(rrule_text, dtstart=anchor)
    nxt = rule.after(after, inc=False)
    return nxt.replace(tzinfo=None) if nxt is not None else None
