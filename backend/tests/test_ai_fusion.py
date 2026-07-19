"""内嵌 AI 动作 + 秘书自动档（后端）。"""
import json

import pytest


def _enable_config(client):
    config = client.post(
        "/ai/configs",
        json={"name": "t", "provider": "openai_responses", "model": "fake", "api_key": "k"},
    ).json()
    client.post(f"/ai/configs/{config['id']}/enable")
    return config


def _enable_feature(client, key):
    client.put("/settings", json={"settings": {key: "true"}})


# ---- 内嵌 AI 动作 ----

@pytest.mark.anyio
async def test_breakdown_subtasks_creates_from_ai(client, monkeypatch):
    _enable_config(client)
    task = client.post("/tasks", json={"title": "准备发布会", "due_date": "2026-07-25T18:00:00"}).json()

    async def fake_provider(_req):
        return {"output_text": '{"subtasks": ["定场地", "写讲稿", "彩排"]}'}

    monkeypatch.setattr("app.services.ai_client.call_provider", fake_provider)
    resp = client.post("/ai/actions/breakdown-subtasks", json={"task_id": task["id"]})
    assert resp.status_code == 200
    titles = [s["title"] for s in resp.json()["subtasks"]]
    assert titles == ["定场地", "写讲稿", "彩排"]
    task_after = client.get(f"/tasks/{task['id']}").json()
    assert len(task_after["subtasks"]) == 3

    # 已有子任务的任务拒绝重复拆解
    resp = client.post("/ai/actions/breakdown-subtasks", json={"task_id": task["id"]})
    assert resp.status_code == 409


def test_breakdown_requires_config_and_feature(client):
    task = client.post("/tasks", json={"title": "无配置任务"}).json()
    # 无 AI 配置 → 400
    assert client.post("/ai/actions/breakdown-subtasks", json={"task_id": task["id"]}).status_code == 400
    # 功能关闭 → 403
    _enable_config(client)
    client.put("/settings", json={"settings": {"feature_inline_ai_enabled": "false"}})
    assert client.post("/ai/actions/breakdown-subtasks", json={"task_id": task["id"]}).status_code == 403


def test_schedule_task_with_explicit_date_needs_no_ai(client):
    task = client.post("/tasks", json={"title": "手动排程"}).json()
    resp = client.post("/ai/actions/schedule-task", json={"task_id": task["id"], "date": "2026-07-22"})
    assert resp.status_code == 200
    assert resp.json()["date"] == "2026-07-22"


@pytest.mark.anyio
async def test_schedule_task_ai_picks_date(client, monkeypatch):
    _enable_config(client)
    task = client.post("/tasks", json={"title": "智能排程", "due_date": "2026-07-25T18:00:00"}).json()

    async def fake_provider(_req):
        return {"output_text": '{"date": "2026-07-24", "reason": "截止前一天负载最低"}'}

    monkeypatch.setattr("app.services.ai_client.call_provider", fake_provider)
    resp = client.post("/ai/actions/schedule-task", json={"task_id": task["id"]})
    assert resp.status_code == 200
    assert resp.json()["date"] == "2026-07-24"
    assert "负载最低" in resp.json()["note"]


def test_journal_draft_rule_fallback_without_config(client):
    done = client.post("/tasks", json={"title": "已完成的事", "status": "完成"}).json()
    resp = client.post("/ai/actions/journal-draft", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "rule"
    assert "已完成的事" in body["content"]


@pytest.mark.anyio
async def test_timer_signoff_ai_text(client, monkeypatch, db_session):
    from app.models import TimeLog
    from datetime import datetime

    _enable_config(client)
    _enable_feature(client, "feature_companion_enabled")
    log = TimeLog(task_id=None, task_title="写方案", started_at=datetime.now(), minutes=25)
    db_session.add(log)
    db_session.commit()

    async def fake_provider(_req):
        return {"output_text": "25 分钟推进了方案，喝口水再决定下一步。"}

    monkeypatch.setattr("app.services.ai_client.call_provider", fake_provider)
    resp = client.post("/ai/actions/timer-signoff", json={"log_id": log.id})
    assert resp.status_code == 200
    assert resp.json()["source"] == "ai"
    assert "方案" in resp.json()["text"]


def test_timer_signoff_feature_off_403(client, db_session):
    from app.models import TimeLog
    from datetime import datetime

    log = TimeLog(task_id=None, task_title="x", started_at=datetime.now(), minutes=25)
    db_session.add(log)
    db_session.commit()
    assert client.post("/ai/actions/timer-signoff", json={"log_id": log.id}).status_code == 403


# ---- 秘书自动档 ----

@pytest.mark.anyio
async def test_autopilot_run_schedules_and_breaks_down(client, monkeypatch):
    from datetime import datetime, timedelta

    _enable_config(client)
    _enable_feature(client, "feature_autopilot_enabled")
    tomorrow = (datetime.now() + timedelta(days=1)).isoformat()
    big = client.post(
        "/tasks", json={"title": "重大项目汇报", "priority": "高", "due_date": tomorrow}
    ).json()

    calls = {"n": 0}

    async def fake_provider(_req):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"output_text": '{"assignments": []}'}
        return {"output_text": '{"subtasks": ["列提纲", "写初稿", "做演示稿"]}'}

    monkeypatch.setattr("app.services.ai_client.call_provider", fake_provider)
    resp = client.post("/ai/autopilot/run")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ran"] is True
    kinds = {a["kind"] for a in body["actions"]}
    assert "breakdown" in kinds
    task_after = client.get(f"/tasks/{big['id']}").json()
    assert len(task_after["subtasks"]) == 3

    # 当天幂等：第二次返回缓存，不再调用模型
    resp2 = client.post("/ai/autopilot/run")
    assert resp2.json().get("cached") is True
    assert calls["n"] == 2


@pytest.mark.anyio
async def test_autopilot_schedules_tasks(client, monkeypatch):
    from datetime import datetime, timedelta

    _enable_config(client)
    _enable_feature(client, "feature_autopilot_enabled")
    due = (datetime.now() + timedelta(days=2)).isoformat()
    task = client.post("/tasks", json={"title": "待排任务", "due_date": due}).json()
    target_day = (datetime.now() + timedelta(days=1)).date().isoformat()

    async def fake_provider(_req):
        return {
            "output_text": json.dumps(
                {"assignments": [{"task_id": task["id"], "date": target_day, "note": "尽早处理"}]},
                ensure_ascii=False,
            )
        }

    monkeypatch.setattr("app.services.ai_client.call_provider", fake_provider)
    body = client.post("/ai/autopilot/run").json()
    assert body["ran"] is True
    action = next(a for a in body["actions"] if a["kind"] == "schedule")
    assert action["date"] == target_day
    assert action["entry_id"] > 0
    assert "已为你" in body["message"]


def test_autopilot_requires_flag_and_config(client):
    # 默认关闭 → 403
    assert client.post("/ai/autopilot/run").status_code == 403
    # 开启但无配置 → ran False 友好返回
    _enable_feature(client, "feature_autopilot_enabled")
    body = client.post("/ai/autopilot/run").json()
    assert body["ran"] is False
    assert "配置" in body["reason"]
