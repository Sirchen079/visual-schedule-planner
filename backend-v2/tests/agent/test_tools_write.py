# tests/agent/test_tools_write.py
import json
from zhishi.agent.tools.registry import get_spec


def test_safe_tools_execute_directly(db):
    from zhishi.agent.tools import atomic_write as aw
    result = json.loads(aw.create_task(db, title="工具建任务", priority="high",
                                       tag_names=["AI"]))
    assert result["id"] > 0 and result["title"] == "工具建任务"


def test_confirm_tools_registered_but_not_in_safe_set(db):
    for name in ("update_task", "delete_task", "update_schedule_entry", "empty_trash"):
        spec = get_spec(name)
        assert spec is not None and spec.safety == "confirm"
    assert get_spec("empty_trash").safety == "confirm"
    from zhishi.agent.permissions import classify
    assert classify(db, "empty_trash", {}) == "confirm"


def test_update_work_plan_is_safe_meta_tool(db):
    spec = get_spec("update_work_plan")
    assert spec.safety == "safe"
    from zhishi.agent.tools import atomic_write as aw
    out = json.loads(aw.update_work_plan(db, steps=[{"title": "第一步", "status": "进行中"}]))
    assert out["steps"][0]["title"] == "第一步"


def test_write_inventory_complete():
    """写类工具清单完整性（防止漏注册）。"""
    expected = {"create_task", "create_subtasks", "assign_task_to_day", "create_event",
                "check_in_habit", "write_journal", "update_kr_progress",
                "start_timer", "stop_timer", "update_work_plan",
                "update_task", "delete_task", "update_schedule_entry", "delete_schedule_entry",
                "update_event", "delete_event", "update_habit", "delete_habit",
                "update_goal", "delete_goal", "update_subtask", "delete_subtask",
                "empty_trash", "bulk_delete_tasks", "bulk_delete_files", "import_web_resources"}
    from zhishi.agent.tools.registry import REGISTRY
    assert expected <= {s.name for s in REGISTRY}
