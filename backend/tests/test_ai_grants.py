"""阶段 D1：权限分级 + 始终允许授权测试。

覆盖：
1. careful 档：confirm 工具永远问（grant 不生效）。
2. standard 档：grant 命中后 confirm 工具直接执行（分类降级为 safe）。
3. autonomous 档：除三大高危外全部免问。
4. autonomous 档：三大高危仍出确认卡。
5. grant CRUD（list/create/delete）。
"""
import json

import pytest

from app.models import AIConversation, AIToolGrant
from app.services import ai_grant_service, app_setting_service


def _set_autonomy(db, level):
    app_setting_service.update_settings(db, {"agent_autonomy": level})


def test_d1_careful_always_asks(client, db_session):
    """careful 档：grant 存在也不生效，confirm 工具仍分类为 dangerous。"""
    from app.routers.ai import _classify_native_call
    _set_autonomy(db_session, "careful")
    # 造一个 grant
    db_session.add(AIToolGrant(tool_name="update_task", arg_pattern=""))
    db_session.commit()
    call = {"name": "update_task", "arguments": {"task_id": 1, "patch": {"title": "x"}}}
    assert _classify_native_call(db_session, call) == "dangerous"


def test_d1_standard_grant_downgrades_to_safe(client, db_session):
    """standard 档：grant 命中 → confirm 工具分类为 safe（直接执行）。"""
    from app.routers.ai import _classify_native_call
    _set_autonomy(db_session, "standard")
    db_session.add(AIToolGrant(tool_name="update_task", arg_pattern=""))
    db_session.commit()
    call = {"name": "update_task", "arguments": {"task_id": 1, "patch": {"title": "x"}}}
    assert _classify_native_call(db_session, call) == "safe"


def test_d1_standard_no_grant_stays_dangerous(client, db_session):
    """standard 档：无 grant → confirm 工具仍 dangerous。"""
    from app.routers.ai import _classify_native_call
    _set_autonomy(db_session, "standard")
    call = {"name": "update_task", "arguments": {"task_id": 1, "patch": {"title": "x"}}}
    assert _classify_native_call(db_session, call) == "dangerous"


def test_d1_autonomous_allows_most_except_irrevocable(client, db_session):
    """autonomous 档：普通 confirm 免问；三大高危仍 dangerous。"""
    from app.routers.ai import _classify_native_call
    _set_autonomy(db_session, "autonomous")
    # 普通 confirm 工具 → safe
    assert _classify_native_call(db_session, {"name": "update_task", "arguments": {"task_id": 1}}) == "safe"
    assert _classify_native_call(db_session, {"name": "delete_task", "arguments": {"task_id": 1}}) == "safe"
    # 三大不可豁免高危 → 仍 dangerous
    assert _classify_native_call(db_session, {"name": "empty_trash", "arguments": {}}) == "dangerous"
    assert _classify_native_call(db_session, {"name": "bulk_delete_tasks", "arguments": {"task_ids": [1]}}) == "dangerous"
    assert _classify_native_call(db_session, {"name": "import_web_resources", "arguments": {}}) == "dangerous"


def test_d1_grant_crud(client, db_session):
    """grant 增删查。"""
    g = ai_grant_service.create_grant(db_session, "update_task", "")
    assert g.id > 0
    grants = ai_grant_service.list_grants(db_session)
    assert any(x.tool_name == "update_task" for x in grants)
    assert ai_grant_service.delete_grant(db_session, g.id) is True
    assert ai_grant_service.delete_grant(db_session, g.id) is False  # 已删


def test_d1_grant_endpoints(client, db_session):
    """POST/GET/DELETE /ai/grants 端点。"""
    r = client.post("/ai/grants", json={"tool_name": "delete_task", "arg_pattern": ""})
    assert r.status_code == 201
    grant_id = r.json()["id"]
    grants = client.get("/ai/grants").json()
    assert any(g["id"] == grant_id for g in grants)
    d = client.delete(f"/ai/grants/{grant_id}")
    assert d.status_code == 204


@pytest.mark.anyio
async def test_d1_granted_tool_executes_directly(client, db_session, monkeypatch):
    """standard 档 + grant：update_task 不再走两段确认，直接执行。"""
    from app.services import ai_client
    from app.routers.ai import _classify_native_call

    # 启用 native config + 造任务 + 造 grant
    payload = {
        "name": "d1", "provider": "openai_chat", "model": "fake",
        "api_key": "k", "tool_calling_mode": "native",
    }
    cfg = client.post("/ai/configs", json=payload).json()
    client.post(f"/ai/configs/{cfg['id']}/enable")
    _set_autonomy(db_session, "standard")
    db_session.add(AIToolGrant(tool_name="update_task", arg_pattern=""))
    db_session.commit()
    task = client.post("/tasks", json={"title": "D1 原标题"}).json()

    call_count = {"n": 0}

    async def fake_call_provider(request):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return {
                "choices": [{
                    "message": {
                        "content": "改一下",
                        "tool_calls": [{
                            "id": "c1", "type": "function",
                            "function": {"name": "update_task", "arguments": json.dumps(
                                {"task_id": task["id"], "patch": {"title": "D1 新标题"}}
                            )},
                        }],
                    },
                    "finish_reason": "tool_calls",
                }]
            }
        return {"choices": [{"message": {"content": "已更新"}, "finish_reason": "stop"}]}

    monkeypatch.setattr(ai_client, "call_provider", fake_call_provider)
    body = client.post("/ai/chat", json={"message": "改任务标题"}).json()
    # 无 pending_actions（grant 命中，直接执行）
    assert body["pending_actions"] == []
    # 任务标题已更新
    t = client.get("/tasks").json()
    assert any(x["title"] == "D1 新标题" for x in t)
