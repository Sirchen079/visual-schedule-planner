"""重复任务：完成时打点 + 惰性生成下一实例。"""
from datetime import datetime, timedelta

from app.services import task_service


# ---- next_occurrence 纯函数 ----

def test_next_occurrence_daily():
    due = datetime(2026, 7, 17, 9, 30)
    after = datetime(2026, 7, 17, 0, 0)
    assert task_service.next_occurrence(due, "daily", 1, after) == datetime(2026, 7, 18, 9, 30)


def test_next_occurrence_daily_with_interval():
    due = datetime(2026, 7, 17)
    after = datetime(2026, 7, 17)
    assert task_service.next_occurrence(due, "daily", 3, after) == datetime(2026, 7, 20)


def test_next_occurrence_weekdays_skips_weekend():
    # 2026-07-17 是周五，下一个工作日是 7-20 周一
    friday = datetime(2026, 7, 17)
    nxt = task_service.next_occurrence(friday, "weekdays", 1, friday)
    assert nxt == datetime(2026, 7, 20)
    assert nxt.weekday() < 5


def test_next_occurrence_weekly():
    due = datetime(2026, 7, 17)
    assert task_service.next_occurrence(due, "weekly", 2, due) == datetime(2026, 7, 31)


def test_next_occurrence_monthly_clamps_to_month_end():
    # 1 月 31 日 + 1 个月 → 2 月 28 日（2026 非闰年）
    due = datetime(2026, 1, 31)
    assert task_service.next_occurrence(due, "monthly", 1, due) == datetime(2026, 2, 28)


def test_next_occurrence_none_rule_returns_none():
    assert task_service.next_occurrence(datetime(2026, 7, 17), "none", 1) is None


def test_next_occurrence_overdue_advances_past_floor():
    # 逾期 10 天的每日任务完成后，下一实例不应仍是逾期
    due = datetime(2026, 7, 7)
    after = datetime(2026, 7, 17)
    nxt = task_service.next_occurrence(due, "daily", 1, after)
    assert nxt >= after.replace(hour=0, minute=0, second=0, microsecond=0)


# ---- API 级：完成重复任务生成下一实例 ----

def _create(client, **overrides):
    payload = {"title": "每日站会", "due_date": _tomorrow_iso(), **overrides}
    resp = client.post("/tasks", json=payload)
    assert resp.status_code == 201
    return resp.json()


def _tomorrow_iso():
    return (datetime.now() + timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0).isoformat()


def test_complete_recurring_task_spawns_next_instance(client):
    task = _create(client, recur_rule="daily", due_time="18:00", remind_offsets=[0, 30])
    resp = client.put(f"/tasks/{task['id']}", json={"status": "完成"})
    assert resp.status_code == 200
    completed = resp.json()
    assert completed["completed_at"] is not None

    tasks = client.get("/tasks").json()
    spawned = [t for t in tasks if t["id"] != task["id"] and t["title"] == "每日站会"]
    assert len(spawned) == 1
    nxt = spawned[0]
    assert nxt["status"] == "待办"
    assert nxt["progress"] == 0
    assert nxt["recur_rule"] == "daily"
    assert nxt["due_time"] == "18:00"
    assert nxt["remind_offsets"] == [0, 30]
    old_due = datetime.fromisoformat(completed["due_date"])
    new_due = datetime.fromisoformat(nxt["due_date"])
    assert new_due > old_due


def test_spawned_instance_copies_tags_and_subtasks_reset(client):
    task = _create(client, recur_rule="weekly", tags=["工作"], priority="高")
    client.post(f"/tasks/{task['id']}/subtasks", json={"title": "准备议程"})
    client.post(f"/tasks/{task['id']}/subtasks", json={"title": "发纪要"})

    client.put(f"/tasks/{task['id']}", json={"status": "完成"})
    tasks = client.get("/tasks").json()
    spawned = [t for t in tasks if t["id"] != task["id"] and t["title"] == "每日站会"]
    assert len(spawned) == 1
    nxt = spawned[0]
    assert [t["name"] for t in nxt["tags"]] == ["工作"]
    assert nxt["priority"] == "高"
    assert len(nxt["subtasks"]) == 2
    assert all(not s["done"] for s in nxt["subtasks"])


def test_complete_non_recurring_task_does_not_spawn(client):
    task = _create(client)
    client.put(f"/tasks/{task['id']}", json={"status": "完成"})
    tasks = client.get("/tasks").json()
    assert len([t for t in tasks if t["title"] == "每日站会"]) == 1


def test_reopen_completed_task_clears_completed_at(client):
    task = _create(client)
    client.put(f"/tasks/{task['id']}", json={"status": "完成"})
    completed = client.get(f"/tasks/{task['id']}").json()
    assert completed["completed_at"] is not None

    resp = client.put(f"/tasks/{task['id']}", json={"status": "进行中", "progress": 50})
    assert resp.json()["completed_at"] is None


def test_subtask_full_completion_sets_completed_at(client):
    task = _create(client)
    sub = client.post(f"/tasks/{task['id']}/subtasks", json={"title": "唯一子任务"}).json()
    client.put(f"/tasks/{task['id']}/subtasks/{sub['id']}", json={"done": True})
    task_after = client.get(f"/tasks/{task['id']}").json()
    assert task_after["status"] == "完成"
    assert task_after["completed_at"] is not None


def test_remind_offsets_roundtrip_and_dedup(client):
    task = _create(client, remind_offsets=[1440, 0, 30, 30])
    assert task["remind_offsets"] == [0, 30, 1440]
    resp = client.put(f"/tasks/{task['id']}", json={"remind_offsets": [60]})
    assert resp.json()["remind_offsets"] == [60]
