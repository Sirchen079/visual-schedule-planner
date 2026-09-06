# tests/server/test_schedule_entries_list.py
"""re #B5：schedule entries 读取面——GET /api/schedule/entries 列表端点。
task_id / date_from / date_to 过滤，默认近 30 天窗口；条目形状与 POST/PATCH
返回一致，entry_id 不再创建即失联。"""
from datetime import date, timedelta
from fastapi.testclient import TestClient
from zhishi.server.app import create_app

ENTRY_FIELDS = {"id", "task_id", "date", "start_time", "end_time", "source", "note"}


def test_list_entries_default_window_and_filters(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        t1 = c.post("/api/tasks", json={"title": "任务一"}).json()["id"]
        t2 = c.post("/api/tasks", json={"title": "任务二"}).json()["id"]
        today = date.today()
        e1 = c.post("/api/schedule/entries",
                    json={"task_id": t1, "date": today.isoformat(),
                          "start_time": "10:00"}).json()
        e2 = c.post("/api/schedule/entries",
                    json={"task_id": t2, "date": (today - timedelta(days=3)).isoformat()}).json()
        c.post("/api/schedule/entries",
               json={"task_id": t1, "date": "2020-01-01"})   # 窗口外

        # 默认近 30 天：含近端两条，不含 2020 年
        rows = c.get("/api/schedule/entries").json()
        assert {r["id"] for r in rows} == {e1["id"], e2["id"]}
        assert all(set(r) == ENTRY_FIELDS for r in rows)
        assert rows[0]["date"] <= rows[-1]["date"]           # 按日期排序

        # task_id 过滤
        rows = c.get("/api/schedule/entries", params={"task_id": t1}).json()
        assert {r["id"] for r in rows} == {e1["id"]}

        # 显式日期窗：能取回 2020 年那条
        rows = c.get("/api/schedule/entries",
                     params={"date_from": "2020-01-01", "date_to": today.isoformat()}).json()
        assert len(rows) == 3

        # 只给一端：按 30 天窗推算，不 422
        assert c.get("/api/schedule/entries",
                     params={"date_from": "2020-01-01"}).status_code == 200
        assert c.get("/api/schedule/entries",
                     params={"date_to": "2020-01-05"}).json()[0]["date"] == "2020-01-01"


def test_list_entries_documented_in_openapi(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        spec = c.app.openapi()
        op = spec["paths"]["/api/schedule/entries"]["get"]
        schema = op["responses"]["200"]["content"]["application/json"]["schema"]
        assert "$ref" in str(schema) and "ScheduleEntryOut" in str(schema)
