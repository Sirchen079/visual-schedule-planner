"""tool_registry 单测：schema 合法性、与 action 类型一致性、功能开关过滤。"""
from app.services import tool_registry
from app.services.ai_action_service import SUPPORTED_ACTION_TYPES


def _validate_schema(schema):
    try:
        from jsonschema import Draft7Validator
    except ImportError:  # jsonschema 非显式依赖时降级为结构校验
        assert isinstance(schema, dict)
        return
    Draft7Validator.check_schema(schema)


def test_builtin_tool_names_are_unique():
    names = [td.name for td in tool_registry.BUILTIN_TOOLS]
    assert len(names) == len(set(names))


def test_every_tool_schema_is_valid_json_schema():
    for td in tool_registry.BUILTIN_TOOLS:
        _validate_schema(td.input_schema)
        assert td.input_schema.get("type") == "object"
        assert "properties" in td.input_schema


def test_safe_and_confirm_partition():
    all_names = {td.name for td in tool_registry.BUILTIN_TOOLS}
    safe = tool_registry.safe_names()
    confirm = tool_registry.confirm_names()
    assert safe.isdisjoint(confirm)
    assert safe | confirm == all_names
    # 阶段 C1/C2 后：32 safe + 25 confirm = 57（含 propose_plan / update_work_plan 两个 safe 收尾工具）
    assert len(safe) == 32
    assert len(confirm) == 25


def test_confirm_tools_map_to_action_type_by_name():
    for td in tool_registry.BUILTIN_TOOLS:
        if td.safety == "confirm":
            assert td.confirm_action_type == td.name


def test_confirm_action_types_match_supported_action_types_minus_history_channels():
    """registry confirm 集 == SUPPORTED_ACTION_TYPES 去掉 attach_file_to_task（safe 直调）
    与 mcp_tool_call（MCP pending 通道）这两个历史通道。防漂移。"""
    history_channels = {"attach_file_to_task", "mcp_tool_call"}
    expected = SUPPORTED_ACTION_TYPES - history_channels
    assert tool_registry.confirm_action_types() == expected


def test_feature_flag_filtering(db_session):
    from app.models import AppSetting
    from app.services import app_setting_service

    # 默认（功能全开）暴露所有 38 个工具
    db_session.add(AppSetting(key="feature_habits_enabled", value="true"))
    db_session.add(AppSetting(key="feature_journal_enabled", value="true"))
    db_session.add(AppSetting(key="feature_goals_enabled", value="true"))
    db_session.add(AppSetting(key="feature_timer_enabled", value="true"))
    db_session.commit()

    all_tools = tool_registry.all_tool_defs(db_session)
    assert len(all_tools) == len(tool_registry.BUILTIN_TOOLS)

    # 关掉习惯功能后，习惯相关工具被过滤
    db_session.query(AppSetting).filter_by(key="feature_habits_enabled").update({"value": "false"})
    db_session.commit()
    names = {td.name for td in tool_registry.all_tool_defs(db_session)}
    assert "list_habits" not in names
    assert "create_habit" not in names
    assert "check_in_habit" not in names
    # 其它功能工具仍在
    assert "list_tasks" in names
    assert "start_timer" in names


def test_provider_tools_shape(db_session):
    from app.models import AppSetting

    db_session.add(AppSetting(key="feature_habits_enabled", value="true"))
    db_session.add(AppSetting(key="feature_journal_enabled", value="true"))
    db_session.add(AppSetting(key="feature_goals_enabled", value="true"))
    db_session.add(AppSetting(key="feature_timer_enabled", value="true"))
    db_session.commit()

    tools = tool_registry.provider_tools(db_session)
    assert tools
    for item in tools:
        assert set(item.keys()) == {"name", "description", "input_schema"}
        assert isinstance(item["input_schema"], dict)


def test_safe_tools_cover_execute_tool_chain():
    """safe_names 必须覆盖 ai_tool_service.execute_tool 里所有 if 分支的 safe 工具。"""
    expected_safe = {
        "list_tasks", "create_task", "list_reminders", "create_reminder",
        "list_files", "list_subtasks", "create_subtask", "create_subtasks",
        "list_day_schedule", "list_month_schedule", "get_time_stats",
        "assign_task_to_day",
        "create_note_file", "attach_file_to_task", "save_attachment_to_library",
        "list_habits", "create_habit", "check_in_habit", "list_journal_entries",
        "write_journal", "list_goals", "create_goal", "update_kr_progress",
        "start_timer", "stop_timer",
        # 阶段 B5 新增 safe 工具
        "toggle_subtask", "restore_from_trash", "mark_notifications_read",
        "get_settings", "generate_report",
        # 阶段 C1/C2 新增 safe 工具（plan 模式收尾 + 工作清单）
        "propose_plan", "update_work_plan",
    }
    assert tool_registry.safe_names() == expected_safe


def test_feature_flags_match_expected_groups():
    flags = tool_registry.feature_flags()
    for name in {"list_habits", "create_habit", "check_in_habit"}:
        assert flags[name] == "feature_habits_enabled"
    for name in {"list_journal_entries", "write_journal"}:
        assert flags[name] == "feature_journal_enabled"
    for name in {"list_goals", "create_goal", "update_kr_progress"}:
        assert flags[name] == "feature_goals_enabled"
    for name in {"start_timer", "stop_timer", "get_time_stats"}:
        assert flags[name] == "feature_timer_enabled"
    # 不受门控的工具为 None
    assert flags["list_tasks"] is None
    assert flags["create_task"] is None
