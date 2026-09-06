# tests/domain/schedule/test_events.py
from datetime import date
from zhishi.domain.schedule import service as ss


def test_event_crud(db):
    e = ss.create_event(db, title="高数", date=date(2026, 9, 7),
                        start_time="08:00", end_time="09:40", location="教一 201",
                        recur_rrule="FREQ=WEEKLY;INTERVAL=2;BYDAY=MO")
    got = ss.get_event(db, e.id)
    assert got.title == "高数" and got.location == "教一 201"


def test_rrule_expands_only_in_biweekly_mondays(db):
    ss.create_event(db, title="双周课", date=date(2026, 9, 7), start_time="08:00",
                    recur_rrule="FREQ=WEEKLY;INTERVAL=2;BYDAY=MO")
    hits = ss.expand_events_between(db, date(2026, 9, 1), date(2026, 10, 12))
    hit_dates = [h["date"] for h in hits]
    assert hit_dates == ["2026-09-07", "2026-09-21", "2026-10-05"]  # 单双周：只落双周周一


def test_unified_day_view_merges_tasks_and_events(db):
    from zhishi.domain.tasks import service as ts
    from zhishi.domain.tasks.schemas import TaskCreate
    t = ts.create_task(db, TaskCreate(title="课后作业"))
    ss.assign_task_to_day(db, t.id, date(2026, 9, 7))
    ss.create_event(db, title="高数", date=date(2026, 9, 7), start_time="08:00", end_time="09:40")
    view = ss.unified_day(db, date(2026, 9, 7))
    assert [i["title"] for i in view["items"]] == ["高数", "课后作业"]
    assert view["items"][0]["kind"] == "event"
