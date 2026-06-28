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
