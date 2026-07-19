"""番茄钟时间记录 + OKR 目标管理（后端）。"""
from datetime import date, datetime, timedelta


# ---- 计时器 ----

def _task(client, title="专注任务", **kw):
    return client.post("/tasks", json={"title": title, **kw}).json()


def test_timer_start_stop_flow(client):
    task = _task(client)
    resp = client.post("/timer/start", json={"task_id": task["id"]})
    assert resp.status_code == 201
    log = resp.json()
    assert log["task_title"] == "专注任务"
    assert log["ended_at"] is None

    current = client.get("/timer/current").json()
    assert current["id"] == log["id"]

    stopped = client.post("/timer/stop").json()
    assert stopped["ended_at"] is not None
    assert stopped["minutes"] >= 1
    assert client.get("/timer/current").json() is None


def test_timer_single_running_semantics(client):
    t1 = _task(client, "任务一")
    t2 = _task(client, "任务二")
    client.post("/timer/start", json={"task_id": t1["id"]})
    client.post("/timer/start", json={"task_id": t2["id"]})  # 自动停掉前一个
    current = client.get("/timer/current").json()
    assert current["task_title"] == "任务二"
    logs = client.get("/time-logs?days=1").json()
    assert len(logs) == 1  # 已结束的只有任务一
    assert logs[0]["task_title"] == "任务一"


def test_timer_start_missing_task_404(client):
    assert client.post("/timer/start", json={"task_id": 9999}).status_code == 404


def test_time_stats_aggregation(client, db_session):
    from app.models import TimeLog

    task = _task(client, "统计任务", tags=["学习"], estimated_minutes=120)
    today = datetime.now()
    db_session.add(
        TimeLog(task_id=task["id"], task_title="统计任务", kind="pomodoro",
                started_at=today - timedelta(hours=2), ended_at=today - timedelta(hours=1), minutes=60)
    )
    db_session.add(
        TimeLog(task_id=None, task_title="已删任务", kind="stopwatch",
                started_at=today - timedelta(days=1), ended_at=today - timedelta(days=1, hours=-1), minutes=30)
    )
    db_session.commit()

    body = client.get("/stats/time?days=7").json()
    assert body["total_minutes"] == 90
    assert len(body["daily"]) == 7
    today_minutes = next(d for d in body["daily"] if d["date"] == today.date().isoformat())
    assert today_minutes["minutes"] == 60
    study = next(t for t in body["by_tag"] if t["name"] == "学习")
    assert study["minutes"] == 60
    assert any(t["name"] == "无标签" for t in body["by_tag"])  # 已删任务计入无标签
    est = body["estimates"][0]
    assert est["estimated_minutes"] == 120
    assert est["actual_minutes"] == 60


def test_estimated_minutes_roundtrip(client):
    task = _task(client, estimated_minutes=90)
    assert task["estimated_minutes"] == 90
    updated = client.put(f"/tasks/{task['id']}", json={"estimated_minutes": 45}).json()
    assert updated["estimated_minutes"] == 45
    cleared = client.put(f"/tasks/{task['id']}", json={"estimated_minutes": None}).json()
    assert cleared["estimated_minutes"] is None


# ---- OKR 目标管理 ----

def test_goal_crud_with_krs(client):
    resp = client.post(
        "/goals",
        json={
            "title": "Q3 练出英语会话",
            "key_results": [
                {"title": "背完 3000 词", "target_value": 3000, "unit": "词"},
                {"title": "口语练习 12 次", "target_value": 12, "unit": "次"},
            ],
        },
    )
    assert resp.status_code == 201
    goal = resp.json()
    assert goal["progress"] == 0
    assert len(goal["key_results"]) == 2

    kr = goal["key_results"][0]
    updated = client.put(f"/goals/krs/{kr['id']}", json={"current_value": 1500}).json()
    assert updated["progress"] == 50

    goal_after = client.get(f"/goals/{goal['id']}").json()
    assert goal_after["progress"] == 25  # 两个 KR 均值

    client.put(f"/goals/{goal['id']}", json={"status": "done"})
    assert client.get(f"/goals/{goal['id']}").json()["status"] == "done"
    assert client.delete(f"/goals/{goal['id']}").status_code == 204
    assert client.get("/goals").json() == []


def test_goal_kr_tag_task_count_rollup(client):
    goal = client.post(
        "/goals",
        json={
            "title": "交付重构",
            "key_results": [
                {"title": "完成 2 个重构任务", "kind": "tag_task_count",
                 "target_value": 2, "link": {"tag": "重构"}}
            ],
        },
    ).json()
    t1 = client.post("/tasks", json={"title": "重构A", "tags": ["重构"]}).json()
    t2 = client.post("/tasks", json={"title": "重构B", "tags": ["重构"]}).json()
    client.put(f"/tasks/{t1['id']}", json={"status": "完成"})

    kr = client.get(f"/goals/{goal['id']}").json()["key_results"][0]
    assert kr["current_value"] == 1
    assert kr["progress"] == 50

    client.put(f"/tasks/{t2['id']}", json={"status": "完成"})
    kr = client.get(f"/goals/{goal['id']}").json()["key_results"][0]
    assert kr["current_value"] == 2
    assert kr["progress"] == 100


def test_goal_kr_habit_checkins_rollup(client):
    habit = client.post("/habits", json={"name": "运动"}).json()
    goal = client.post(
        "/goals",
        json={
            "title": "本月运动 3 次",
            "start_date": date.today().isoformat(),
            "key_results": [
                {"title": "运动 3 次", "kind": "habit_checkins", "target_value": 3,
                 "link": {"habit_id": habit["id"]}}
            ],
        },
    ).json()
    client.post(f"/habits/{habit['id']}/check", json={})
    client.post(f"/habits/{habit['id']}/check", json={})
    kr = client.get(f"/goals/{goal['id']}").json()["key_results"][0]
    assert kr["current_value"] == 2
    assert kr["progress"] == 66 or kr["progress"] == 67


def test_kr_current_value_locked_for_auto_kinds(client):
    goal = client.post(
        "/goals",
        json={
            "title": "自动KR",
            "key_results": [
                {"title": "打卡 5 次", "kind": "habit_checkins", "target_value": 5,
                 "link": {"habit_id": 1}}
            ],
        },
    ).json()
    kr = goal["key_results"][0]
    updated = client.put(f"/goals/krs/{kr['id']}", json={"current_value": 99}).json()
    assert updated["current_value"] == 0  # 自动类 KR 不允许直接改值


def test_goal_add_and_delete_kr(client):
    goal = client.post("/goals", json={"title": "目标"}).json()
    kr = client.post(
        f"/goals/{goal['id']}/krs", json={"title": "新增KR", "target_value": 10}
    ).json()
    assert kr["id"] > 0
    assert client.delete(f"/goals/krs/{kr['id']}").status_code == 204
    assert client.get(f"/goals/{goal['id']}").json()["key_results"] == []


# ---- AI 新工具 ----

def test_ai_tool_goal_and_timer_flow(db_session):
    from app.services import ai_tool_service, task_service
    from app.schemas import TaskCreate

    result = ai_tool_service.execute_tool(
        db_session,
        "create_goal",
        {"title": "AI 目标", "key_results": [{"title": "KR1", "target_value": 4}]},
    )
    assert result["ok"] is True
    assert result["goal"]["key_results"][0]["progress"] == 0

    kr_id = result["goal"]["key_results"][0]["id"]
    result = ai_tool_service.execute_tool(
        db_session, "update_kr_progress", {"kr_id": kr_id, "current_value": 2}
    )
    assert result["ok"] is True
    assert result["kr"]["progress"] == 50

    task = task_service.create_task(db_session, TaskCreate(title="计时任务"))
    result = ai_tool_service.execute_tool(db_session, "start_timer", {"task_id": task.id})
    assert result["ok"] is True
    result = ai_tool_service.execute_tool(db_session, "stop_timer", {})
    assert result["ok"] is True
    assert result["timer"]["minutes"] >= 1

    result = ai_tool_service.execute_tool(db_session, "stop_timer", {})
    assert result["ok"] is False  # 没有运行中的计时
