from datetime import datetime, timedelta


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
