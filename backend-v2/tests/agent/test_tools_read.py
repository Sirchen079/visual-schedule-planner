# tests/agent/test_tools_read.py
from zhishi.agent.tools.registry import REGISTRY, get_spec, readonly_names
from zhishi.agent.tools import atomic_read


def test_registry_shape():
    names = {s.name for s in REGISTRY}
    assert {"get_current_time", "list_tasks", "list_day_schedule", "find_free_slots"} <= names
    dup = len(names) != len(REGISTRY)
    assert not dup, "工具名重复"


def test_every_spec_has_description_and_fn():
    for s in REGISTRY:
        assert s.description and len(s.description) > 10
        assert callable(s.fn)


def test_get_current_time(db):
    import json
    result = atomic_read.get_current_time(db)
    data = json.loads(result)
    assert {"now", "date", "weekday", "timezone_note"} <= set(data)


def test_list_tasks_tool(db):
    from zhishi.domain.tasks import service as ts
    from zhishi.domain.tasks.schemas import TaskCreate
    ts.create_task(db, TaskCreate(title="可查任务"))
    result = atomic_read.list_tasks(db, query="可查")
    assert "可查任务" in result
