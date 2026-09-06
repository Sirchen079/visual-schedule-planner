# src/zhishi/domain/schedule/conflicts.py
"""冲突检测与空闲时段发现：仅对带起止时刻的项生效。"""
from __future__ import annotations
from datetime import date, timedelta
from sqlalchemy.orm import Session
from zhishi.domain.schedule.service import day_schedule, expand_events_between


def _to_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _timed_items(db: Session, day: date) -> list[dict]:
    items = [e for e in expand_events_between(db, day, day)
             if e.get("start_time") and e.get("end_time")]
    items += [t for t in day_schedule(db, day)["tasks"]
              if t.get("start_time") and t.get("end_time")]
    return items


def check_conflicts(db: Session, start: date, end: date) -> list[dict]:
    """逐日找时间重叠对（含跨任务排期与日程）。"""
    conflicts: list[dict] = []
    d = start
    while d <= end:
        items = _timed_items(db, d)
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, b = items[i], items[j]
                if _to_min(a["start_time"]) < _to_min(b["end_time"]) and \
                   _to_min(b["start_time"]) < _to_min(a["end_time"]):
                    conflicts.append({"date": d.isoformat(), "items": [a, b]})
        d += timedelta(days=1)
    return conflicts


def find_free_slots(db: Session, day: date, *, working: tuple[str, str],
                    min_minutes: int = 30) -> list[dict]:
    """工作时段内减去已占用时段，返回 ≥min_minutes 的连续空闲段。"""
    busy = sorted((_to_min(i["start_time"]), _to_min(i["end_time"]))
                  for i in _timed_items(db, day))
    slots = free_intervals(_to_min(working[0]), _to_min(working[1]), busy)
    return [{"start": f"{s // 60:02d}:{s % 60:02d}",
             "end": f"{e // 60:02d}:{e % 60:02d}", "minutes": e - s}
            for s, e in slots if e - s >= min_minutes]


def free_intervals(lo: int, hi: int, busy: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Subtract occupied ranges after clipping to the requested window."""
    if hi <= lo:
        return []
    clipped = sorted((max(lo, s), min(hi, e)) for s, e in busy if s < hi and e > lo and e > s)
    slots, cursor = [], lo
    for s, e in clipped + [(hi, hi)]:
        if s > cursor:
            slots.append((cursor, s))
        cursor = max(cursor, e)
    return slots
