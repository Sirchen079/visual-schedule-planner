"""功能开关：默认值、AI 工具门控、上下文裁剪。"""
from app.services import ai_tool_service, app_setting_service


def test_feature_flags_default_enabled(db_session):
    for key in (
        "feature_habits_enabled",
        "feature_journal_enabled",
        "feature_goals_enabled",
        "feature_timer_enabled",
    ):
        assert app_setting_service.feature_enabled(db_session, key) is True


def test_disabled_feature_blocks_ai_tools(db_session):
    app_setting_service.set_setting(db_session, "feature_habits_enabled", "false")
    result = ai_tool_service.execute_tool(db_session, "list_habits", {})
    assert result["ok"] is False
    assert "关闭" in result["error"]

    app_setting_service.set_setting(db_session, "feature_timer_enabled", "false")
    result = ai_tool_service.execute_tool(db_session, "start_timer", {"task_id": 1})
    assert result["ok"] is False

    # 其他功能不受影响；重新开启恢复
    app_setting_service.set_setting(db_session, "feature_habits_enabled", "true")
    result = ai_tool_service.execute_tool(db_session, "list_habits", {})
    assert result["ok"] is True


def test_disabled_feature_pruned_from_context(db_session):
    from app.services import ai_prompt_service

    app_setting_service.set_setting(db_session, "feature_habits_enabled", "false")
    app_setting_service.set_setting(db_session, "feature_journal_enabled", "false")
    app_setting_service.set_setting(db_session, "feature_timer_enabled", "false")
    ctx = ai_prompt_service.build_local_context(db_session)
    assert "今日习惯打卡：\n无" in ctx
    assert "最近日记：\n无" in ctx
    assert "番茄钟功能已关闭" in ctx
