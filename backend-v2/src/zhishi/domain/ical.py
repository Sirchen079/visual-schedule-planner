"""ICS 互通：events ↔ VEVENT（含 RRULE 透传）。"""
from __future__ import annotations
from datetime import UTC, datetime, time as dtime, timedelta
from uuid import NAMESPACE_URL, uuid5
from icalendar import Calendar, Event as VEvent
from sqlalchemy.orm import Session
from zhishi.domain.models import Event
from zhishi.domain.schedule.schemas import EventCreate
from zhishi.domain.schedule.service import create_event


def export_ics(db: Session) -> str:
    cal = Calendar()
    cal.add("PRODID", "-//zhishi backend v2//CN")
    cal.add("VERSION", "2.0")
    cal.add("CALSCALE", "GREGORIAN")
    cal.add("X-WR-CALNAME", "知时日程")
    for event in db.query(Event).all():
        ve = VEvent()
        # Stable across exports and edits, distinct for independently created records.
        ve.add("UID", str(uuid5(NAMESPACE_URL, f"zhishi:event:{event.id}:{event.created_at.isoformat()}")))
        ve.add("DTSTAMP", datetime.now(UTC))
        ve.add("SUMMARY", event.title)
        if event.start_time:
            start = datetime.combine(event.date, dtime.fromisoformat(event.start_time))
            ve.add("DTSTART", start)
            if event.end_time:
                end = datetime.combine(event.date, dtime.fromisoformat(event.end_time))
                if end <= start:
                    end += timedelta(days=1)
                ve.add("DTEND", end)
        else:
            ve.add("DTSTART", event.date)
            ve.add("DTEND", event.date + timedelta(days=1))
        if event.recur_rrule:
            ve.add("RRULE", event.recur_rrule)
        if event.location:
            ve.add("LOCATION", event.location)
        if event.notes:
            ve.add("DESCRIPTION", event.notes)
        cal.add_component(ve)
    return cal.to_ical().decode("utf-8")


def import_ics(db: Session, content: str) -> int:
    """导入 VEVENT → events。重复导入=新增（去重属产品策略，决定）。"""
    cal = Calendar.from_ical(content)
    created = 0
    for component in cal.walk("VEVENT"):
        summary = str(component.get("SUMMARY", "导入日程"))
        dtstart = component.get("DTSTART")
        if dtstart is None:
            continue
        dt = dtstart.dt
        day = dt.date() if isinstance(dt, datetime) else dt
        rrule = None
        if component.get("RRULE") is not None:
            rrule = component["RRULE"].to_ical().decode()
        location = str(component.get("LOCATION", "") or "")
        create_event(db, **EventCreate(title=summary, date=day,
                                        start_time=_hhmm(dt) if isinstance(dt, datetime) else None,
                                        recur_rrule=rrule, location=location).model_dump())
        created += 1
    return created


def _hhmm(dt: datetime) -> str:
    return f"{dt.hour:02d}:{dt.minute:02d}"
