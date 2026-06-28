from datetime import datetime, timedelta, timezone

from app.schemas import TaskCreate
from app.services import reminder_service, task_service


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def test_due_reminders_splits_upcoming_and_overdue(client):
    now = datetime.now()
    client.post("/tasks", json={"title": "逾期", "due_date": _iso(now - timedelta(days=1))})
    client.post("/tasks", json={"title": "即将到期", "due_date": _iso(now + timedelta(hours=3))})
    client.post("/tasks", json={"title": "还很远", "due_date": _iso(now + timedelta(days=10))})
    client.post("/tasks", json={"title": "已完成但逾期", "due_date": _iso(now - timedelta(days=2)), "status": "完成"})

    resp = client.get("/reminders/due?hours=24")
    assert resp.status_code == 200
    body = resp.json()
    assert [t["title"] for t in body["overdue"]] == ["逾期"]
    assert [t["title"] for t in body["upcoming"]] == ["即将到期"]


def test_due_reminders_ignores_deleted(client):
    now = datetime.now()
    tid = client.post("/tasks", json={"title": "要删的", "due_date": _iso(now - timedelta(days=1))}).json()["id"]
    client.delete(f"/tasks/{tid}")
    body = client.get("/reminders/due?hours=24").json()
    assert body["overdue"] == []
    assert body["upcoming"] == []


def test_due_reminders_handles_timezone_aware_datetimes(db_session):
    tz = timezone(timedelta(hours=8))
    now = datetime(2026, 6, 27, 10, 0, tzinfo=tz)
    task_service.create_task(
        db_session,
        TaskCreate(title="带时区提醒", due_date=datetime(2026, 6, 27, 11, 0, tzinfo=tz)),
    )

    upcoming, overdue = reminder_service.due_reminders(db_session, hours=24, now=now)

    assert [task.title for task in upcoming] == ["带时区提醒"]
    assert overdue == []
