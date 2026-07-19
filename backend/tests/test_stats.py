"""统计分析 API：summary / daily / by-tag / by-priority。"""
from datetime import datetime, timedelta


def _iso(dt: datetime) -> str:
    return dt.replace(second=0, microsecond=0).isoformat()


def test_stats_summary_counts(client):
    now = datetime.now()
    client.post("/tasks", json={"title": "逾期任务", "due_date": _iso(now - timedelta(days=2))})
    client.post("/tasks", json={"title": "今日任务", "due_date": _iso(now)})
    client.post("/tasks", json={"title": "本周任务", "due_date": _iso(now + timedelta(days=5))})
    client.post("/tasks", json={"title": "远期任务", "due_date": _iso(now + timedelta(days=30))})
    done = client.post("/tasks", json={"title": "已完成", "status": "完成"}).json()

    body = client.get("/stats/summary").json()
    assert body["total"] == 5
    assert body["by_status"]["完成"] == 1
    assert body["overdue"] == 1
    assert body["due_today"] == 1
    assert body["due_this_week"] == 2  # 今日 + 5 天后
    assert body["completed_total"] == 1
    # 已完成任务不计入逾期
    assert done["id"] > 0


def test_stats_daily_completed_and_created(client):
    now = datetime.now()
    task = client.post("/tasks", json={"title": "趋势任务"}).json()
    client.put(f"/tasks/{task['id']}", json={"status": "完成"})

    body = client.get("/stats/daily?days=7").json()
    assert len(body["days"]) == 7
    today_point = body["days"][-1]
    assert today_point["date"] == now.date().isoformat()
    assert today_point["completed"] == 1
    assert today_point["created"] == 1


def test_stats_daily_uses_completed_at_date(client, db_session):
    # 完成时间落在过去某天的任务，趋势应记在那一天（按 completed_at 分桶）
    from app.models import Task

    task = client.post("/tasks", json={"title": "历史任务"}).json()
    client.put(f"/tasks/{task['id']}", json={"status": "完成"})
    row = db_session.get(Task, task["id"])
    row.completed_at = datetime.now() - timedelta(days=3)
    db_session.commit()

    body = client.get("/stats/daily?days=7").json()
    completed_by_date = {p["date"]: p["completed"] for p in body["days"]}
    target = (datetime.now() - timedelta(days=3)).date().isoformat()
    assert completed_by_date[target] == 1
    # 今天不应重复计数
    assert completed_by_date[datetime.now().date().isoformat()] == 0


def test_stats_by_tag(client):
    client.post("/tasks", json={"title": "任务A", "tags": ["工作"]})
    t2 = client.post("/tasks", json={"title": "任务B", "tags": ["工作", "学习"]}).json()
    client.put(f"/tasks/{t2['id']}", json={"status": "完成"})

    body = client.get("/stats/by-tag").json()
    work = next(t for t in body["tags"] if t["name"] == "工作")
    assert work["total"] == 2
    assert work["completed"] == 1
    study = next(t for t in body["tags"] if t["name"] == "学习")
    assert study["total"] == 1
    # 无任务的标签不出现
    assert all(t["total"] > 0 for t in body["tags"])


def test_stats_by_priority(client):
    client.post("/tasks", json={"title": "高优1", "priority": "高"})
    client.post("/tasks", json={"title": "高优2", "priority": "高", "status": "完成"})
    client.post("/tasks", json={"title": "低优", "priority": "低"})

    body = client.get("/stats/by-priority").json()
    high = next(p for p in body["priorities"] if p["priority"] == "高")
    assert high["total"] == 2
    assert high["by_status"]["待办"] == 1
    assert high["by_status"]["完成"] == 1
    order = [p["priority"] for p in body["priorities"]]
    assert order == ["高", "中", "低"]
