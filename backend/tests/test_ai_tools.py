from app.services import ai_tool_service


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


def test_ai_tool_create_subtasks_pass_estimated_minutes_to_model(db_session):
    """create_subtasks 支持对象形态 {title, estimated_minutes}，且透传给模型可见的 _subtask_dict。"""
    task = ai_tool_service.execute_tool(
        db_session, "create_task", {"title": "带预估的任务"}
    )["task"]

    result = ai_tool_service.execute_tool(
        db_session,
        "create_subtasks",
        {
            "task_id": task["id"],
            "titles": [
                {"title": "写初稿", "estimated_minutes": 45},
                "审校",  # 纯字符串：estimated_minutes 应为 None
            ],
        },
    )

    assert result["ok"] is True
    by_title = {s["title"]: s for s in result["subtasks"]}
    assert by_title["写初稿"]["estimated_minutes"] == 45
    assert by_title["审校"]["estimated_minutes"] is None
    # list_subtasks 也应透出 estimated_minutes（M1：_subtask_dict 不再丢字段）
    listed = ai_tool_service.execute_tool(
        db_session, "list_subtasks", {"task_id": task["id"]}
    )
    listed_by_title = {s["title"]: s for s in listed["subtasks"]}
    assert listed_by_title["写初稿"]["estimated_minutes"] == 45


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


def test_ai_tool_get_time_stats_returns_daily_dates_as_strings(db_session):
    """get_time_stats 返回 ok，且 daily 的 date 均为 ISO 字符串（供模型可读）。"""
    result = ai_tool_service.execute_tool(db_session, "get_time_stats", {})
    assert result["ok"] is True
    stats = result["stats"]
    assert "daily" in stats
    for item in stats["daily"]:
        assert isinstance(item["date"], str)
        assert "T" not in item["date"]  # 纯日期 YYYY-MM-DD
    # days 参数被 clamp 到 1-90
    result_big = ai_tool_service.execute_tool(db_session, "get_time_stats", {"days": 999})
    assert result_big["ok"] is True
    assert len(result_big["stats"]["daily"]) <= 90
