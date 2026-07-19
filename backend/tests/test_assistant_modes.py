"""双助手模式：知时助手（原版问答式）/ 知时代理（主动代劳）。"""
import pytest

from app.services import ai_prompt_service


def _enable_config(client, assistant_name="知时助手"):
    config = client.post(
        "/ai/configs",
        json={
            "name": "t",
            "provider": "openai_responses",
            "model": "fake",
            "api_key": "k",
            "assistant_name": assistant_name,
        },
    ).json()
    client.post(f"/ai/configs/{config['id']}/enable")
    return config


def _set_mode(client, mode):
    client.put("/settings", json={"settings": {"assistant_mode": mode}})


def test_agent_mode_default_persona_and_name(db_session):
    from app.models import AIConfig

    config = AIConfig(provider="openai_chat", model="m", api_key="k", assistant_name="知时助手")
    # 默认 agent 模式：内置名升级为知时代理，人设是秘书行为准则
    assert ai_prompt_service.resolve_assistant_name(db_session, config) == "知时代理"
    prompt = ai_prompt_service.build_system_prompt(db_session, config)
    assert "主动关联" in prompt
    assert "知时代理" in prompt


def test_assistant_mode_classic_persona_and_name(db_session):
    from app.models import AIConfig
    from app.services import app_setting_service

    app_setting_service.set_setting(db_session, "assistant_mode", "assistant")
    config = AIConfig(provider="openai_chat", model="m", api_key="k", assistant_name="知时助手")
    assert ai_prompt_service.resolve_assistant_name(db_session, config) == "知时助手"
    prompt = ai_prompt_service.build_system_prompt(db_session, config)
    assert "有求必应" in prompt
    assert "主动关联" not in prompt
    # 上下文不含幕僚观察段
    ctx = ai_prompt_service.build_local_context(db_session)
    assert "幕僚观察" not in ctx


def test_custom_name_respected_in_both_modes(db_session):
    from app.models import AIConfig
    from app.services import app_setting_service

    config = AIConfig(provider="openai_chat", model="m", api_key="k", assistant_name="小秘")
    assert ai_prompt_service.resolve_assistant_name(db_session, config) == "小秘"
    app_setting_service.set_setting(db_session, "assistant_mode", "assistant")
    assert ai_prompt_service.resolve_assistant_name(db_session, config) == "小秘"


@pytest.mark.anyio
async def test_chat_response_uses_mode_name(client, monkeypatch):
    _enable_config(client)
    _set_mode(client, "agent")

    async def fake_provider(_req):
        return {"output_text": '```json\n{"reply":"好","tools":[],"dangerous_actions":[]}\n```'}

    monkeypatch.setattr("app.services.ai_client.call_provider", fake_provider)
    body = client.post("/ai/chat", json={"message": "你好"}).json()
    assert body["assistant_name"] == "知时代理"

    _set_mode(client, "assistant")
    body = client.post("/ai/chat", json={"message": "你好"}).json()
    assert body["assistant_name"] == "知时助手"


def test_autopilot_blocked_in_assistant_mode(client):
    _set_mode(client, "assistant")
    client.put("/settings", json={"settings": {"feature_autopilot_enabled": "true"}})
    resp = client.post("/ai/autopilot/run")
    assert resp.status_code == 403
    assert "知时代理" in resp.json()["detail"]


def test_companion_blocked_in_assistant_mode(client, db_session):
    from app.models import TimeLog
    from datetime import datetime

    _set_mode(client, "assistant")
    client.put("/settings", json={"settings": {"feature_companion_enabled": "true"}})
    log = TimeLog(task_id=None, task_title="x", started_at=datetime.now(), minutes=25)
    db_session.add(log)
    db_session.commit()
    resp = client.post("/ai/actions/timer-signoff", json={"log_id": log.id})
    assert resp.status_code == 403
    assert "知时代理" in resp.json()["detail"]
