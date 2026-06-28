from app.services import ai_tool_service
from app.services.ai_client import parse_assistant_plan


def test_ai_tool_create_task(db_session):
    result = ai_tool_service.execute_tool(
        db_session,
        "create_task",
        {
            "title": "写论文初稿",
            "notes": "AI 创建",
            "tags": ["科研"],
        },
    )
    assert result["ok"] is True
    assert result["task"]["title"] == "写论文初稿"


def test_ai_tool_create_subtasks_for_task(db_session):
    task = ai_tool_service.execute_tool(
        db_session,
        "create_task",
        {"title": "阅读论文"},
    )["task"]

    result = ai_tool_service.execute_tool(
        db_session,
        "create_subtasks",
        {
            "task_id": task["id"],
            "titles": ["通读摘要和引言", "整理相关工作", "写阅读笔记"],
        },
    )

    assert result["ok"] is True
    assert [item["title"] for item in result["subtasks"]] == [
        "通读摘要和引言",
        "整理相关工作",
        "写阅读笔记",
    ]
    listed = ai_tool_service.execute_tool(
        db_session,
        "list_subtasks",
        {"task_id": task["id"]},
    )
    assert [item["title"] for item in listed["subtasks"]] == [
        "通读摘要和引言",
        "整理相关工作",
        "写阅读笔记",
    ]


def test_ai_tool_create_task_can_include_subtask_titles(db_session):
    result = ai_tool_service.execute_tool(
        db_session,
        "create_task",
        {
            "title": "完成论文阅读",
            "subtask_titles": ["读摘要", "读方法", "总结问题"],
        },
    )

    assert result["ok"] is True
    assert [item["title"] for item in result["task"]["subtasks"]] == [
        "读摘要",
        "读方法",
        "总结问题",
    ]


def test_ai_tool_create_reminder_creates_task_with_due_date(db_session):
    result = ai_tool_service.execute_tool(
        db_session,
        "create_reminder",
        {
            "title": "下周六提醒我交材料",
            "due_date": "2026-07-04T09:00:00",
            "notes": "用户要求下周六提醒。",
            "tags": ["提醒"],
        },
    )

    assert result["ok"] is True
    assert result["task"]["title"] == "下周六提醒我交材料"
    assert result["task"]["due_date"] == "2026-07-04T09:00:00"
    assert "提醒" in result["task"]["tags"]


def test_ai_tool_list_reminders_returns_tasks_with_due_dates(db_session):
    ai_tool_service.execute_tool(
        db_session,
        "create_task",
        {"title": "普通任务"},
    )
    ai_tool_service.execute_tool(
        db_session,
        "create_reminder",
        {"title": "带提醒任务", "due_date": "2026-07-04T09:00:00"},
    )

    result = ai_tool_service.execute_tool(db_session, "list_reminders", {})

    assert result["ok"] is True
    assert [task["title"] for task in result["reminders"]] == ["带提醒任务"]


def test_ai_tool_rejects_unknown_tool(db_session):
    result = ai_tool_service.execute_tool(db_session, "delete_everything", {})
    assert result["ok"] is False
    assert "不允许" in result["error"]


def test_ai_tool_create_note_file(db_session):
    result = ai_tool_service.execute_tool(
        db_session,
        "create_note_file",
        {
            "title": "会议纪要",
            "content": "导师要求周五前提交。",
        },
    )
    assert result["ok"] is True
    assert result["file"]["original_name"] == "会议纪要.txt"


def test_ai_tool_create_task_can_attach_uploaded_files(db_session):
    file_result = ai_tool_service.execute_tool(
        db_session,
        "create_note_file",
        {
            "title": "论文资料",
            "content": "阅读重点和引用信息。",
        },
    )

    result = ai_tool_service.execute_tool(
        db_session,
        "create_task",
        {
            "title": "整理论文资料",
            "notes": "把资料纳入本周论文任务。",
            "file_ids": [file_result["file"]["id"]],
        },
    )

    assert result["ok"] is True
    assert result["task"]["title"] == "整理论文资料"
    assert [file["id"] for file in result["task"]["files"]] == [file_result["file"]["id"]]


def test_ai_tool_attach_file_to_existing_task_is_safe(db_session):
    task_result = ai_tool_service.execute_tool(
        db_session,
        "create_task",
        {"title": "论文阅读"},
    )
    file_result = ai_tool_service.execute_tool(
        db_session,
        "create_note_file",
        {
            "title": "论文摘要",
            "content": "需要归档到论文阅读任务。",
        },
    )

    result = ai_tool_service.execute_tool(
        db_session,
        "attach_file_to_task",
        {"task_id": task_result["task"]["id"], "file_id": file_result["file"]["id"]},
    )

    assert result["ok"] is True
    assert result["task"]["id"] == task_result["task"]["id"]
    assert [file["id"] for file in result["task"]["files"]] == [file_result["file"]["id"]]


def test_ai_tool_rejects_mutating_existing_objects_without_confirmation(db_session):
    for name, args in {
        "update_task": {"task_id": 1, "title": "覆盖"},
        "update_file_notes": {"file_id": 1, "notes": "覆盖"},
        "detach_file_from_task": {"task_id": 1, "file_id": 1},
    }.items():
        result = ai_tool_service.execute_tool(db_session, name, args)
        assert result["ok"] is False
        assert "待确认" in result["error"]


def test_parse_assistant_plan_accepts_json_block():
    text = """
说明文字
```json
{"reply":"已安排","tools":[{"name":"create_task","args":{"title":"读论文"}}],"dangerous_actions":[]}
```
"""
    plan = parse_assistant_plan(text)
    assert plan["reply"] == "已安排"
    assert plan["tools"][0]["name"] == "create_task"


def test_parse_assistant_plan_falls_back_to_text():
    plan = parse_assistant_plan("普通回复")
    assert plan == {"reply": "普通回复", "tools": [], "dangerous_actions": []}
