"""子任务在 REST 读取面可见（写后无读修复）。
GET /api/tasks 与 GET /api/tasks/{id} 的响应带 subtasks
（SubtaskRead：id/title/done/estimated_minutes/completed_at）；
列表端点 selectinload 一次预载，读取查询数不随任务数线性增长。"""
from fastapi.testclient import TestClient
from sqlalchemy import event
from zhishi.server.app import create_app

SUBTASK_FIELDS = {"id", "title", "done", "estimated_minutes", "completed_at"}


def test_task_reads_carry_subtasks(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        tid = c.post("/api/tasks", json={"title": "重构知时"}).json()["id"]
        empty_tid = c.post("/api/tasks", json={"title": "无子任务"}).json()["id"]
        s1 = c.post(f"/api/tasks/{tid}/subtasks",
                    json={"title": "写计划", "estimated_minutes": 30}).json()
        c.patch(f"/api/tasks/{tid}/subtasks/{s1['id']}", json={"done": True})
        c.post(f"/api/tasks/{tid}/subtasks", json={"title": "写实现"})

        task = c.get(f"/api/tasks/{tid}").json()
        assert len(task["subtasks"]) == 2
        assert all(set(s) == SUBTASK_FIELDS for s in task["subtasks"])
        done = next(s for s in task["subtasks"] if s["done"])
        assert done["title"] == "写计划" and done["estimated_minutes"] == 30
        assert done["completed_at"] is not None

        assert c.get(f"/api/tasks/{empty_tid}").json()["subtasks"] == []

        lst = {t["id"]: t for t in c.get("/api/tasks").json()}
        assert len(lst[tid]["subtasks"]) == 2
        assert lst[empty_tid]["subtasks"] == []

        # 回收站列表同样带出
        c.delete(f"/api/tasks/{tid}")
        trash = {t["id"]: t for t in c.get("/api/tasks/trash").json()}
        assert len(trash[tid]["subtasks"]) == 2


def test_task_read_documents_subtasks_in_openapi(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        schemas = c.app.openapi()["components"]["schemas"]
        assert "SubtaskRead" in schemas
        props = schemas["TaskRead"]["properties"]
        assert "subtasks" in props
        assert "SubtaskRead" in str(props["subtasks"])


def test_task_list_subqueries_are_preloaded(tmp_path):
    """selectinload 预载哨兵：3 任务 × 2 子任务时列表读取的 select 数有界
    （tasks + tags + subtasks 三发），不随任务数线性增长（N+1 回归）。"""
    with TestClient(create_app(data_dir=tmp_path)) as c:
        for i in range(3):
            tid = c.post("/api/tasks", json={"title": f"任务{i}"}).json()["id"]
            for j in range(2):
                c.post(f"/api/tasks/{tid}/subtasks", json={"title": f"子{j}"})

        engine = c.app.state.engine
        statements: list[str] = []

        def _capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement.lstrip().lower())

        event.listen(engine, "before_cursor_execute", _capture)
        try:
            r = c.get("/api/tasks")
            assert r.status_code == 200
        finally:
            event.remove(engine, "before_cursor_execute", _capture)
        selects = [s for s in statements if s.startswith("select")]
        assert len(selects) <= 3, f"列表查询数随任务数增长（N+1）: {selects}"
