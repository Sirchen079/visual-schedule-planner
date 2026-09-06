# tests/server/test_schedule_contracts.py
"""re #017(k3)① + #019 minor：schedule 只读端点与 plan reject 的 200 响应必须 typed
（此前 openapi schema 全空 → 前端手写类型漂移）。同时锁定真实载荷关键字段：
response_model 序列化不得丢弃实际返回的字段（如 day 视图 event 条目的 date）。"""
from fastapi.testclient import TestClient
from zhishi.server.app import create_app

TYPED_PATHS = [
    ("/api/schedule/day", "get"),
    ("/api/schedule/range", "get"),
    ("/api/schedule/events/expand", "get"),
    ("/api/schedule/conflicts", "get"),
    ("/api/schedule/free-slots", "get"),
    ("/api/schedule/month", "get"),
]
PLAN_REJECT_PATH = "/ai/conversations/{cid}/plans/{plan_id}/reject"


def test_schedule_endpoints_have_typed_response_schemas(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        spec = c.app.openapi()
        for path, method in TYPED_PATHS:
            schema = spec["paths"][path][method]["responses"]["200"][
                "content"]["application/json"]["schema"]
            assert schema, f"{path} 的 200 响应 schema 仍为空对象"
        reject_schema = spec["paths"][PLAN_REJECT_PATH]["post"][
            "responses"]["200"]["content"]["application/json"]["schema"]
        assert reject_schema, f"{PLAN_REJECT_PATH} 的 200 响应 schema 仍为空对象"


def test_schedule_payload_fields_survive_response_model(tmp_path):
    """typed 化后真实载荷不得变形：day 的 event 条目保留 date、task 条目保留 task_id；
    range 按日期键控；expand 展开 RRULE（含单双周）；conflicts 携带冲突对；free-slots 三字段。"""
    with TestClient(create_app(data_dir=tmp_path)) as c:
        tid = c.post("/api/tasks", json={"title": "重构知时", "estimated_minutes": 60}).json()["id"]
        c.post("/api/schedule/entries", json={"task_id": tid, "date": "2026-09-07",
                                              "start_time": "10:00", "end_time": "11:00"})
        c.post("/api/schedule/events", json={"title": "高数", "date": "2026-09-07",
                                             "start_time": "10:30", "end_time": "12:00",
                                             "location": "A101", "category": "课表",
                                             "recur_rrule": "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO"})

        day = c.get("/api/schedule/day", params={"date": "2026-09-07"}).json()
        assert day["date"] == "2026-09-07" and len(day["items"]) == 2
        by_kind = {i["kind"]: i for i in day["items"]}
        assert by_kind["event"]["event_id"] and by_kind["event"]["date"] == "2026-09-07"
        assert by_kind["event"]["location"] == "A101" and by_kind["event"]["category"] == "课表"
        assert by_kind["task"]["task_id"] == tid and by_kind["task"]["title"] == "重构知时"

        rng = c.get("/api/schedule/range", params={"start": "2026-09-07", "days": 2}).json()
        assert set(rng) == {"2026-09-07", "2026-09-08"}
        assert rng["2026-09-07"]["estimated_minutes"] == 60
        assert rng["2026-09-07"]["items"][0]["task_id"] == tid
        assert rng["2026-09-08"] == {"items": [], "estimated_minutes": 0}

        expand = c.get("/api/schedule/events/expand",
                       params={"start": "2026-09-07", "end": "2026-10-05"}).json()
        dates = [e["date"] for e in expand]
        assert dates[0] == "2026-09-07" and "2026-09-21" in dates   # 双周展开（INTERVAL=2）
        assert all({"event_id", "title", "date", "start_time", "end_time",
                    "location", "category"} <= set(e) for e in expand)

        conflicts = c.get("/api/schedule/conflicts",
                          params={"start": "2026-09-07", "end": "2026-09-07"}).json()
        assert len(conflicts) == 1
        assert conflicts[0]["date"] == "2026-09-07" and len(conflicts[0]["items"]) == 2

        slots = c.get("/api/schedule/free-slots",
                      params={"date": "2026-09-07", "min_minutes": 30}).json()
        assert all({"start", "end", "minutes"} == set(s) for s in slots)


def test_month_view_counts_events_and_tasks(tmp_path):
    """re #020 事项3：month 视图在 task_count 之外增加 event_count
    （当日独立日程 RRULE 展开计数）。双周课的月份 event_count 隔周 +1。"""
    with TestClient(create_app(data_dir=tmp_path)) as c:
        tid = c.post("/api/tasks", json={"title": "周任务"}).json()["id"]
        c.post("/api/schedule/entries", json={"task_id": tid, "date": "2026-09-07"})
        c.post("/api/schedule/events", json={"title": "双周课", "date": "2026-09-07",
                                             "start_time": "08:00", "end_time": "09:40",
                                             "recur_rrule": "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO;UNTIL=20261231"})

        month = c.get("/api/schedule/month", params={"year": 2026, "month": 9}).json()
        by_date = {d["date"]: d for d in month}
        # 9 月共 30 天全覆盖，条目三字段齐备
        assert len(month) == 30
        assert all(set(d) == {"date", "task_count", "event_count"} for d in month)
        # task_count 保留原语义
        assert by_date["2026-09-07"]["task_count"] == 1
        assert by_date["2026-09-14"]["task_count"] == 0
        # 双周课：7/21 日的周一 +1，14/28 日为 0（隔周 +1）
        assert by_date["2026-09-07"]["event_count"] == 1
        assert by_date["2026-09-14"]["event_count"] == 0
        assert by_date["2026-09-21"]["event_count"] == 1
        assert by_date["2026-09-28"]["event_count"] == 0


def test_expand_and_day_views_carry_repeat_note(tmp_path):
    """re #020 事项2：events/expand 与 day 视图 typed model 带 repeat_note（可空）。"""
    with TestClient(create_app(data_dir=tmp_path)) as c:
        c.post("/api/schedule/events", json={"title": "单周课", "date": "2026-09-07",
                                             "start_time": "08:00", "end_time": "09:40",
                                             "recur_rrule": "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO",
                                             "repeat_note": "单周课（第1-16周）"})
        c.post("/api/schedule/events", json={"title": "无规则日程", "date": "2026-09-08"})

        expand = c.get("/api/schedule/events/expand",
                       params={"start": "2026-09-07", "end": "2026-09-08"}).json()
        by_title = {e["title"]: e for e in expand}
        assert by_title["单周课"]["repeat_note"] == "单周课（第1-16周）"
        assert by_title["无规则日程"]["repeat_note"] is None

        day = c.get("/api/schedule/day", params={"date": "2026-09-07"}).json()
        ev = next(i for i in day["items"] if i["kind"] == "event")
        assert ev["repeat_note"] == "单周课（第1-16周）"
