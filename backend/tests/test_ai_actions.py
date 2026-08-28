from app.services import ai_action_service, ai_tool_service


def test_delete_task_pending_action_requires_two_steps(client, db_session):
    task_id = client.post("/tasks", json={"title": "危险删除"}).json()["id"]
    action = ai_action_service.create_pending_action(
        db_session, None, "delete_task", {"task_id": task_id}, "删除任务：危险删除"
    )

    first = client.post(f"/ai/actions/{action.id}/confirm")
    assert first.status_code == 200
    token = first.json()["confirm_token"]
    assert client.get(f"/tasks/{task_id}").status_code == 200

    second = client.post(
        f"/ai/actions/{action.id}/execute", json={"confirm_token": token}
    )
    assert second.status_code == 200
    assert client.get(f"/tasks/{task_id}").status_code == 404


def test_execute_rejects_wrong_token(client, db_session):
    task_id = client.post("/tasks", json={"title": "危险删除"}).json()["id"]
    action = ai_action_service.create_pending_action(
        db_session, None, "delete_task", {"task_id": task_id}, "删除任务"
    )
    client.post(f"/ai/actions/{action.id}/confirm")
    resp = client.post(
        f"/ai/actions/{action.id}/execute", json={"confirm_token": "bad"}
    )
    assert resp.status_code == 403


def test_pending_action_preview_tolerates_invalid_payload(client, db_session):
    action = ai_action_service.create_pending_action(
        db_session, None, "delete_task", {"task_id": "abc"}, "删除任务"
    )

    resp = client.post(f"/ai/actions/{action.id}/confirm")

    assert resp.status_code == 200
    assert resp.json()["action"]["preview"] == [
        "操作: 将任务移入回收站",
        "任务: #abc 参数无效",
    ]


def test_execute_rejects_invalid_payload_without_server_error(client, db_session):
    action = ai_action_service.create_pending_action(
        db_session, None, "delete_task", {"task_id": "abc"}, "删除任务"
    )

    token = client.post(f"/ai/actions/{action.id}/confirm").json()["confirm_token"]
    resp = client.post(
        f"/ai/actions/{action.id}/execute", json={"confirm_token": token}
    )

    assert resp.status_code == 409
    assert resp.json()["detail"] == "待确认操作参数无效"


def test_bulk_update_tasks_requires_confirmation(client, db_session):
    first = client.post("/tasks", json={"title": "批量一"}).json()["id"]
    second = client.post("/tasks", json={"title": "批量二"}).json()["id"]
    action = ai_action_service.create_pending_action(
        db_session,
        None,
        "bulk_update_tasks",
        {"task_ids": [first, second], "patch": {"status": "进行中", "progress": 40}},
        "批量更新时间线",
    )

    token = client.post(f"/ai/actions/{action.id}/confirm").json()["confirm_token"]
    resp = client.post(f"/ai/actions/{action.id}/execute", json={"confirm_token": token})

    assert resp.status_code == 200
    assert client.get(f"/tasks/{first}").json()["progress"] == 40
    assert client.get(f"/tasks/{second}").json()["progress"] == 40


def test_update_task_requires_confirmation(client, db_session):
    task_id = client.post("/tasks", json={"title": "旧标题"}).json()["id"]
    action = ai_action_service.create_pending_action(
        db_session,
        None,
        "update_task",
        {"task_id": task_id, "patch": {"title": "新标题", "priority": "高"}},
        "更新任务",
    )

    first = client.post(f"/ai/actions/{action.id}/confirm")
    token = first.json()["confirm_token"]
    assert first.json()["action"]["preview"] == [
        "操作: 更新任务",
        "字段: priority, title",
        f"任务: #{task_id} 旧标题",
    ]
    assert client.get(f"/tasks/{task_id}").json()["title"] == "旧标题"

    resp = client.post(f"/ai/actions/{action.id}/execute", json={"confirm_token": token})

    assert resp.status_code == 200
    task = client.get(f"/tasks/{task_id}").json()
    assert task["title"] == "新标题"
    assert task["priority"] == "高"


def test_update_file_notes_requires_confirmation(client, db_session):
    file_id = ai_tool_service.execute_tool(
        db_session,
        "create_note_file",
        {"title": "资料一", "content": "内容", "notes": "旧备注"},
    )["file"]["id"]
    action = ai_action_service.create_pending_action(
        db_session,
        None,
        "update_file_notes",
        {"file_id": file_id, "notes": "新备注"},
        "更新资料备注",
    )

    first = client.post(f"/ai/actions/{action.id}/confirm")
    token = first.json()["confirm_token"]
    assert first.json()["action"]["preview"] == [
        "操作: 更新资料备注",
        f"资料: #{file_id} 资料一.txt",
    ]
    assert client.get(f"/files/{file_id}").json()["notes"] == "旧备注"

    resp = client.post(f"/ai/actions/{action.id}/execute", json={"confirm_token": token})

    assert resp.status_code == 200
    assert client.get(f"/files/{file_id}").json()["notes"] == "新备注"


def test_attach_and_detach_file_requires_confirmation(client, db_session):
    task_id = client.post("/tasks", json={"title": "读论文"}).json()["id"]
    file_id = ai_tool_service.execute_tool(
        db_session,
        "create_note_file",
        {"title": "论文资料", "content": "内容"},
    )["file"]["id"]
    attach = ai_action_service.create_pending_action(
        db_session,
        None,
        "attach_file_to_task",
        {"task_id": task_id, "file_id": file_id},
        "关联资料",
    )

    first = client.post(f"/ai/actions/{attach.id}/confirm")
    token = first.json()["confirm_token"]
    assert first.json()["action"]["preview"] == [
        "操作: 将资料关联到任务",
        f"任务: #{task_id} 读论文",
        f"资料: #{file_id} 论文资料.txt",
    ]
    assert client.get(f"/tasks/{task_id}/files").json() == []
    assert client.post(f"/ai/actions/{attach.id}/execute", json={"confirm_token": token}).status_code == 200
    assert len(client.get(f"/tasks/{task_id}/files").json()) == 1

    detach = ai_action_service.create_pending_action(
        db_session,
        None,
        "detach_file_from_task",
        {"task_id": task_id, "file_id": file_id},
        "取消关联资料",
    )
    token = client.post(f"/ai/actions/{detach.id}/confirm").json()["confirm_token"]
    assert client.post(f"/ai/actions/{detach.id}/execute", json={"confirm_token": token}).status_code == 200
    assert client.get(f"/tasks/{task_id}/files").json() == []


def test_import_web_resources_requires_confirmation_and_links_video(
    client, db_session
):
    task_id = client.post("/tasks", json={"title": "学 Vue"}).json()["id"]
    action = ai_action_service.create_pending_action(
        db_session,
        None,
        "import_web_resources",
        {
            "resources": [
                {
                    "title": "Vue3 官方入门视频",
                    "url": "https://example.com/vue-video",
                    "resource_type": "video",
                    "notes": "AI 搜索到的视频教程",
                    "task_id": task_id,
                }
            ]
        },
        "导入 Vue 学习资料",
    )

    first = client.post(f"/ai/actions/{action.id}/confirm")
    token = first.json()["confirm_token"]
    assert first.json()["action"]["preview"] == [
        "操作: 导入 1 条联网资料到资料库",
        "资料: Vue3 官方入门视频 | video | https://example.com/vue-video",
        f"任务: #{task_id} 学 Vue",
    ]
    assert client.get("/files").json() == []

    resp = client.post(f"/ai/actions/{action.id}/execute", json={"confirm_token": token})

    assert resp.status_code == 200
    files = client.get("/files").json()
    assert len(files) == 1
    assert files[0]["source_url"] == "https://example.com/vue-video"
    assert files[0]["resource_type"] == "video"
    linked = client.get(f"/tasks/{task_id}/files").json()
    assert linked[0]["id"] == files[0]["id"]


def test_bulk_update_tasks_with_invalid_id_does_not_partially_apply(
    client, db_session
):
    first = client.post("/tasks", json={"title": "批量一"}).json()["id"]
    action = ai_action_service.create_pending_action(
        db_session,
        None,
        "bulk_update_tasks",
        {"task_ids": [first, 999999], "patch": {"status": "进行中", "progress": 40}},
        "批量更新时间线",
    )

    token = client.post(f"/ai/actions/{action.id}/confirm").json()["confirm_token"]
    resp = client.post(f"/ai/actions/{action.id}/execute", json={"confirm_token": token})

    assert resp.status_code == 409
    task = client.get(f"/tasks/{first}").json()
    assert task["status"] == "待办"
    assert task["progress"] == 0


def test_bulk_delete_tasks_requires_confirmation(client, db_session):
    first = client.post("/tasks", json={"title": "删一"}).json()["id"]
    second = client.post("/tasks", json={"title": "删二"}).json()["id"]
    action = ai_action_service.create_pending_action(
        db_session,
        None,
        "bulk_delete_tasks",
        {"task_ids": [first, second]},
        "批量删除任务",
    )

    token = client.post(f"/ai/actions/{action.id}/confirm").json()["confirm_token"]
    resp = client.post(f"/ai/actions/{action.id}/execute", json={"confirm_token": token})

    assert resp.status_code == 200
    assert client.get(f"/tasks/{first}").status_code == 404
    assert client.get(f"/tasks/{second}").status_code == 404


def test_bulk_delete_tasks_with_invalid_id_does_not_partially_apply(
    client, db_session
):
    first = client.post("/tasks", json={"title": "删一"}).json()["id"]
    action = ai_action_service.create_pending_action(
        db_session,
        None,
        "bulk_delete_tasks",
        {"task_ids": [first, 999999]},
        "批量删除任务",
    )

    token = client.post(f"/ai/actions/{action.id}/confirm").json()["confirm_token"]
    resp = client.post(f"/ai/actions/{action.id}/execute", json={"confirm_token": token})

    assert resp.status_code == 409
    assert client.get(f"/tasks/{first}").status_code == 200


def test_bulk_delete_files_with_invalid_id_does_not_partially_apply(
    client, db_session
):
    file_id = ai_tool_service.execute_tool(
        db_session,
        "create_note_file",
        {"title": "资料一", "content": "内容"},
    )["file"]["id"]
    action = ai_action_service.create_pending_action(
        db_session,
        None,
        "bulk_delete_files",
        {"file_ids": [file_id, 999999]},
        "批量删除资料",
    )

    token = client.post(f"/ai/actions/{action.id}/confirm").json()["confirm_token"]
    resp = client.post(f"/ai/actions/{action.id}/execute", json={"confirm_token": token})

    assert resp.status_code == 409
    assert client.get(f"/files/{file_id}").status_code == 200


def test_reject_pending_action_transitions_to_rejected(client, db_session):
    task_id = client.post("/tasks", json={"title": "拒绝用任务"}).json()["id"]
    action = ai_action_service.create_pending_action(
        db_session, None, "delete_task", {"task_id": task_id}, "删除任务"
    )
    action, error = ai_action_service.reject_action(db_session, action.id)
    assert error is None
    assert action.status == "rejected"
    assert action.confirm_token is None
    # rejected 后任务仍未删除（拒绝 = 不执行）
    assert client.get(f"/tasks/{task_id}").status_code == 200


def test_reject_then_confirm_returns_409(client, db_session):
    task_id = client.post("/tasks", json={"title": "拒绝后不能再确认"}).json()["id"]
    action = ai_action_service.create_pending_action(
        db_session, None, "delete_task", {"task_id": task_id}, "删除任务"
    )
    ai_action_service.reject_action(db_session, action.id)
    # rejected 是终态，再次 confirm 应失败
    _action, token, err = ai_action_service.confirm_action(db_session, action.id)
    assert err == "操作不是待确认状态"
    assert token is None


def test_reject_confirmed_action_then_execute_returns_409(client, db_session):
    task_id = client.post("/tasks", json={"title": "一次确认后再拒绝"}).json()["id"]
    action = ai_action_service.create_pending_action(
        db_session, None, "delete_task", {"task_id": task_id}, "删除任务"
    )
    _action, token, _err = ai_action_service.confirm_action(db_session, action.id)
    assert token  # 一次确认成功
    # confirmed 态（未执行）也可拒绝
    action, error = ai_action_service.reject_action(db_session, action.id)
    assert error is None
    assert action.status == "rejected"
    # 拿着旧 token 再 execute 应失败（状态不再是 confirmed）
    ok, message = ai_action_service.execute_action(db_session, action.id, token)
    assert ok is False
    assert "确认" in message


def test_empty_trash_requires_confirmation(client, db_session):
    task_id = client.post("/tasks", json={"title": "回收站任务"}).json()["id"]
    client.delete(f"/tasks/{task_id}")
    action = ai_action_service.create_pending_action(
        db_session,
        None,
        "empty_trash",
        {},
        "清空回收站",
    )

    token = client.post(f"/ai/actions/{action.id}/confirm").json()["confirm_token"]
    resp = client.post(f"/ai/actions/{action.id}/execute", json={"confirm_token": token})

    assert resp.status_code == 200
    assert client.get("/tasks/trash").json() == []


def _confirm_token(db_session, action_id):
    _action, token, _err = ai_action_service.confirm_action(db_session, action_id)
    return token


def test_create_skill_preview_and_execute(db_session):
    from sqlalchemy import select

    payload = {
        "name": "论文工作流",
        "description": "阅读规划",
        "content": "把阅读任务拆成 45 分钟块，先读摘要再读方法。",
        "enabled": True,
    }
    preview = ai_action_service.build_action_preview(db_session, "create_skill", payload)
    assert any("创建助手 skill" in line for line in preview)
    assert any("论文工作流" in line for line in preview)

    action = ai_action_service.create_pending_action(db_session, None, "create_skill", payload, "创建 skill")
    ok, _message = ai_action_service.execute_action(
        db_session, action.id, _confirm_token(db_session, action.id)
    )
    assert ok is True
    from app.models import AISkill

    skill = db_session.execute(select(AISkill).where(AISkill.name == "论文工作流")).scalar_one()
    assert "45 分钟块" in skill.content
    assert skill.enabled is True


def test_create_skill_upsert_updates_existing(db_session):
    from app.models import AISkill

    ai_action_service._execute_create_skill(db_session, {"name": "周报", "content": "v1"})
    ok, _ = ai_action_service._execute_create_skill(db_session, {"name": "周报", "content": "v2"})
    assert ok is True
    skills = db_session.query(AISkill).filter(AISkill.name == "周报").all()
    assert len(skills) == 1
    assert skills[0].content == "v2"


def test_create_mcp_server_preview_and_execute(db_session):
    from sqlalchemy import select

    payload = {
        "name": "文件系统",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "D:/docs"],
        "env": {"API_TOKEN": "secret-value-1234567890"},
        "enabled": True,
    }
    preview = ai_action_service.build_action_preview(db_session, "create_mcp_server", payload)
    assert any("配置 MCP 工具服务器" in line for line in preview)
    assert any("npx" in line for line in preview)
    assert any("API_TOKEN" in line for line in preview)
    # 值不进预览明文
    assert not any("secret-value-1234567890" in line for line in preview)

    action = ai_action_service.create_pending_action(db_session, None, "create_mcp_server", payload, "配置 MCP")
    ok, _message = ai_action_service.execute_action(
        db_session, action.id, _confirm_token(db_session, action.id)
    )
    assert ok is True
    from app.models import MCPServer

    server = db_session.execute(select(MCPServer).where(MCPServer.name == "文件系统")).scalar_one()
    assert server.command == "npx"
    assert server.transport == "stdio"
    # env 库内明文保存
    assert "secret-value-1234567890" in server.env


def test_create_mcp_server_rejects_bad_transport(db_session):
    ok, message = ai_action_service._execute_create_mcp_server(
        db_session, {"name": "bad", "transport": "ftp", "command": "x"}
    )
    assert ok is False
    assert "transport" in message


def test_create_mcp_server_http_shape(db_session):
    from app.models import MCPServer

    payload = {
        "name": "远程",
        "transport": "http",
        "url": "https://mcp.example.com/mcp",
        "headers": {"Authorization": "Bearer xyz"},
    }
    preview = ai_action_service.build_action_preview(db_session, "create_mcp_server", payload)
    assert any("https://mcp.example.com" in line for line in preview)
    ok, _ = ai_action_service._execute_create_mcp_server(db_session, payload)
    assert ok is True
    server = db_session.query(MCPServer).filter(MCPServer.name == "远程").one()
    assert server.url == "https://mcp.example.com/mcp"


def test_daily_capacity_and_working_hours_settings_validated(db_session):
    from app.services import app_setting_service

    assert app_setting_service.daily_capacity_minutes(db_session) == 240  # 未设置回退
    assert app_setting_service.working_hours(db_session) == ("09:00", "18:00")

    app_setting_service.set_setting(db_session, "daily_capacity_minutes", "abc")  # 脏值
    app_setting_service.set_setting(db_session, "working_hours_start", "8点")
    assert app_setting_service.daily_capacity_minutes(db_session) == 240
    assert app_setting_service.working_hours(db_session) == ("09:00", "18:00")

    app_setting_service.set_setting(db_session, "daily_capacity_minutes", "300")
    app_setting_service.set_setting(db_session, "working_hours_start", "10:00")
    app_setting_service.set_setting(db_session, "working_hours_end", "19:30")
    assert app_setting_service.daily_capacity_minutes(db_session) == 300
    assert app_setting_service.working_hours(db_session) == ("10:00", "19:30")


def test_normalize_title_ignores_case_and_punctuation():
    from app.routers.ai_actions import _normalize_title

    assert _normalize_title("写讲稿！") == _normalize_title("写讲稿")
    assert _normalize_title("Write Draft") == _normalize_title("write  draft")
    assert _normalize_title("整理资料（第一版）") == _normalize_title("整理资料第一版")
