"""阶段 B5：工具覆盖度补齐测试。

每个新工具组覆盖：
- safe 工具：execute_tool 直接派发，断言行为正确。
- confirm 工具：经 ai_action_service 两段确认后执行，断言数据库变化。
"""
import pytest

from app.services import ai_action_service, ai_tool_service, tool_registry


# ---- safe 工具：execute_tool 直接派发 ----


def test_b5_toggle_subtask_flips_done(client, db_session):
    """toggle_subtask：翻转子任务完成状态。"""
    task = client.post("/tasks", json={"title": "B5 toggle 父任务"}).json()
    sub = client.post(f"/tasks/{task['id']}/subtasks", json={"title": "子1"}).json()
    assert sub["done"] is False

    r1 = ai_tool_service.execute_tool(db_session, "toggle_subtask", {"task_id": task["id"], "subtask_id": sub["id"]})
    assert r1["ok"] is True
    assert r1["done"] is True

    r2 = ai_tool_service.execute_tool(db_session, "toggle_subtask", {"task_id": task["id"], "subtask_id": sub["id"]})
    assert r2["done"] is False


def test_b5_toggle_subtask_missing(client, db_session):
    """toggle_subtask：子任务不存在 → 报错。"""
    task = client.post("/tasks", json={"title": "B5 缺子任务"}).json()
    r = ai_tool_service.execute_tool(db_session, "toggle_subtask", {"task_id": task["id"], "subtask_id": 99999})
    assert r["ok"] is False
    assert "不存在" in r["error"]


def test_b5_restore_task_from_trash(client, db_session):
    """restore_from_trash：任务从回收站恢复。"""
    task = client.post("/tasks", json={"title": "B5 待恢复"}).json()
    client.delete(f"/tasks/{task['id']}")  # 软删
    r = ai_tool_service.execute_tool(db_session, "restore_from_trash", {"item_type": "task", "item_id": task["id"]})
    assert r["ok"] is True
    assert r["task"]["title"] == "B5 待恢复"


def test_b5_restore_file_from_trash(client, db_session):
    """restore_from_trash：资料从回收站恢复。"""
    # 造一个文件再软删
    from app.services import file_service
    from app.models import File
    f = File(original_name="b5.txt", storage_path="x", size=1, mime_type="text/plain", notes="", resource_type="file")
    db_session.add(f)
    db_session.commit()
    file_service.soft_delete_file(db_session, f.id)

    r = ai_tool_service.execute_tool(db_session, "restore_from_trash", {"item_type": "file", "item_id": f.id})
    assert r["ok"] is True


def test_b5_restore_invalid_type(client, db_session):
    """restore_from_trash：非法 item_type → 报错。"""
    r = ai_tool_service.execute_tool(db_session, "restore_from_trash", {"item_type": "xxx", "item_id": 1})
    assert r["ok"] is False


def test_b5_mark_all_notifications_read(client, db_session):
    """mark_notifications_read：不传 id → 全部已读。"""
    from app.services import notification_service
    # 先造几条通知
    notification_service.mark_all_read(db_session)  # 清空基线
    r = ai_tool_service.execute_tool(db_session, "mark_notifications_read", {})
    assert r["ok"] is True
    assert "marked_count" in r


def test_b5_get_settings_returns_dict(client, db_session):
    """get_settings：返回设置字典。"""
    r = ai_tool_service.execute_tool(db_session, "get_settings", {})
    assert r["ok"] is True
    assert isinstance(r["settings"], dict)


def test_b5_generate_report_collects_data(client, db_session):
    """generate_report：返回日报数据（同步收集，不触发异步 provider）。"""
    r = ai_tool_service.execute_tool(db_session, "generate_report", {"kind": "daily"})
    assert r["ok"] is True
    assert r["kind"] == "daily"
    assert "report_data" in r


# ---- confirm 工具：经两段确认后执行 ----


def test_b5_update_habit_via_confirm(client, db_session):
    """update_habit：确认后改习惯名。"""
    from app.models import AIConversation, Habit
    conv = AIConversation(title="t")
    db_session.add(conv)
    db_session.commit()
    habit = client.post("/habits", json={"name": "原习惯", "period": "daily", "target_count": 1}).json()

    action = ai_action_service.create_pending_action(
        db_session, conv.id, "update_habit",
        {"habit_id": habit["id"], "patch": {"name": "新习惯名"}},
        "改习惯",
    )
    token = client.post(f"/ai/actions/{action.id}/confirm").json()["confirm_token"]
    ok, msg = ai_action_service.execute_action(db_session, action.id, token)
    assert ok is True
    h = db_session.get(Habit, habit["id"])
    assert h.name == "新习惯名"


def test_b5_delete_habit_via_confirm(client, db_session):
    """delete_habit：确认后软删。"""
    from app.models import AIConversation, Habit
    conv = AIConversation(title="t")
    db_session.add(conv)
    db_session.commit()
    habit = client.post("/habits", json={"name": "待删习惯", "period": "daily", "target_count": 1}).json()

    action = ai_action_service.create_pending_action(
        db_session, conv.id, "delete_habit", {"habit_id": habit["id"]}, "删习惯",
    )
    token = client.post(f"/ai/actions/{action.id}/confirm").json()["confirm_token"]
    ok, _ = ai_action_service.execute_action(db_session, action.id, token)
    assert ok is True
    h = db_session.get(Habit, habit["id"])
    assert h.deleted_at is not None


def test_b5_update_goal_via_confirm(client, db_session):
    """update_goal：确认后改目标标题。"""
    from app.models import AIConversation, Goal
    conv = AIConversation(title="t")
    db_session.add(conv)
    db_session.commit()
    goal = client.post("/goals", json={"title": "原目标"}).json()

    action = ai_action_service.create_pending_action(
        db_session, conv.id, "update_goal",
        {"goal_id": goal["id"], "patch": {"title": "新目标"}},
        "改目标",
    )
    token = client.post(f"/ai/actions/{action.id}/confirm").json()["confirm_token"]
    ok, _ = ai_action_service.execute_action(db_session, action.id, token)
    assert ok is True
    g = db_session.get(Goal, goal["id"])
    assert g.title == "新目标"


def test_b5_delete_goal_via_confirm(client, db_session):
    """delete_goal：确认后软删。"""
    from app.models import AIConversation, Goal
    conv = AIConversation(title="t")
    db_session.add(conv)
    db_session.commit()
    goal = client.post("/goals", json={"title": "待删目标"}).json()

    action = ai_action_service.create_pending_action(
        db_session, conv.id, "delete_goal", {"goal_id": goal["id"]}, "删目标",
    )
    token = client.post(f"/ai/actions/{action.id}/confirm").json()["confirm_token"]
    ok, _ = ai_action_service.execute_action(db_session, action.id, token)
    assert ok is True
    g = db_session.get(Goal, goal["id"])
    assert g.deleted_at is not None


def test_b5_update_reminder_via_confirm(client, db_session):
    """update_reminder：确认后改提醒（=任务）标题。"""
    from app.models import AIConversation, Task
    conv = AIConversation(title="t")
    db_session.add(conv)
    db_session.commit()
    task = client.post("/tasks", json={"title": "原提醒", "due_date": "2026-08-01T09:00:00"}).json()

    action = ai_action_service.create_pending_action(
        db_session, conv.id, "update_reminder",
        {"task_id": task["id"], "patch": {"title": "新提醒标题"}},
        "改提醒",
    )
    token = client.post(f"/ai/actions/{action.id}/confirm").json()["confirm_token"]
    ok, _ = ai_action_service.execute_action(db_session, action.id, token)
    assert ok is True
    t = db_session.get(Task, task["id"])
    assert t.title == "新提醒标题"


def test_b5_update_subtask_via_confirm(client, db_session):
    """update_subtask：确认后改子任务标题。"""
    from app.models import AIConversation, Subtask
    conv = AIConversation(title="t")
    db_session.add(conv)
    db_session.commit()
    task = client.post("/tasks", json={"title": "B5 子任务父"}).json()
    sub = client.post(f"/tasks/{task['id']}/subtasks", json={"title": "原子"}).json()

    action = ai_action_service.create_pending_action(
        db_session, conv.id, "update_subtask",
        {"task_id": task["id"], "subtask_id": sub["id"], "patch": {"title": "新子标题"}},
        "改子任务",
    )
    token = client.post(f"/ai/actions/{action.id}/confirm").json()["confirm_token"]
    ok, _ = ai_action_service.execute_action(db_session, action.id, token)
    assert ok is True
    s = db_session.get(Subtask, sub["id"])
    assert s.title == "新子标题"


def test_b5_delete_subtask_via_confirm(client, db_session):
    """delete_subtask：确认后删子任务。"""
    from app.models import AIConversation, Subtask
    conv = AIConversation(title="t")
    db_session.add(conv)
    db_session.commit()
    task = client.post("/tasks", json={"title": "B5 删子父"}).json()
    sub = client.post(f"/tasks/{task['id']}/subtasks", json={"title": "待删子"}).json()

    action = ai_action_service.create_pending_action(
        db_session, conv.id, "delete_subtask",
        {"task_id": task["id"], "subtask_id": sub["id"]},
        "删子任务",
    )
    token = client.post(f"/ai/actions/{action.id}/confirm").json()["confirm_token"]
    ok, _ = ai_action_service.execute_action(db_session, action.id, token)
    assert ok is True
    assert db_session.get(Subtask, sub["id"]) is None


def test_b5_update_setting_via_confirm(client, db_session):
    """update_setting：确认后改设置项。"""
    from app.models import AIConversation
    from app.services import app_setting_service
    conv = AIConversation(title="t")
    db_session.add(conv)
    db_session.commit()

    action = ai_action_service.create_pending_action(
        db_session, conv.id, "update_setting",
        {"key": "b5_test_setting", "value": "hello"},
        "改设置",
    )
    token = client.post(f"/ai/actions/{action.id}/confirm").json()["confirm_token"]
    ok, _ = ai_action_service.execute_action(db_session, action.id, token)
    assert ok is True
    settings = app_setting_service.list_settings(db_session)
    assert settings.get("b5_test_setting") == "hello"


def test_b5_new_tools_registered_with_correct_safety():
    """新工具全部注册且安全等级正确。"""
    safe = tool_registry.safe_names()
    confirm = tool_registry.confirm_names()
    # safe 新增
    for n in ("toggle_subtask", "restore_from_trash", "mark_notifications_read", "get_settings", "generate_report"):
        assert n in safe, f"{n} 应为 safe"
    # confirm 新增
    for n in ("update_habit", "delete_habit", "update_goal", "delete_goal",
              "update_reminder", "delete_reminder", "update_subtask", "delete_subtask", "update_setting"):
        assert n in confirm, f"{n} 应为 confirm"
