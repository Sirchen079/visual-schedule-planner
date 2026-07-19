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


def test_due_time_delays_overdue_until_that_moment(client):
    """纯日期任务到期日 0 点即算逾期；带 due_time 的任务到时刻才算逾期。"""
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    # 截止时刻取 2 小时后，且 due_date 取该时刻所在日期（跨午夜也安全）
    later_dt = now + timedelta(hours=2)
    later_day = later_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    client.post("/tasks", json={"title": "纯日期", "due_date": _iso(today)})
    client.post(
        "/tasks",
        json={
            "title": "带时刻",
            "due_date": _iso(later_day),
            "due_time": later_dt.strftime("%H:%M"),
        },
    )
    body = client.get("/reminders/due").json()
    overdue_titles = [t["title"] for t in body["overdue"]]
    upcoming_titles = [t["title"] for t in body["upcoming"]]
    assert "纯日期" in overdue_titles
    assert "带时刻" not in overdue_titles
    assert "带时刻" in upcoming_titles


def test_triggered_reminders_hit_offset_window(client):
    """remind_offsets 命中当前时刻的任务出现在 triggered 中。"""
    now = datetime.now()
    in_30 = (now + timedelta(minutes=30))
    client.post(
        "/tasks",
        json={
            "title": "半小时后截止",
            "due_date": _iso(in_30),
            "due_time": in_30.strftime("%H:%M"),
            "remind_offsets": [0, 60],  # 60 分钟前已命中；0 截止时未命中
        },
    )
    body = client.get("/reminders/due").json()
    hits = [i for i in body["triggered"] if i["task"]["title"] == "半小时后截止"]
    assert len(hits) == 1
    assert hits[0]["offset_minutes"] == 60
    assert hits[0]["task"]["due_time"] == in_30.strftime("%H:%M")


def test_triggered_reminders_empty_offsets_no_hits(client):
    now = datetime.now()
    client.post(
        "/tasks",
        json={"title": "无提醒设置", "due_date": _iso(now + timedelta(minutes=5))},
    )
    body = client.get("/reminders/due").json()
    assert body["triggered"] == []
