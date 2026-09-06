"""接口响应模型测试：OpenAPI 声明明确类型，序列化保留领域服务返回的字段。"""
from datetime import date, datetime

from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel
from zhishi.server.app import create_app

# (path, method, status)——四域全部返回 JSON body 的读写端点
TYPED_PATHS = [
    # goals
    ("/api/goals", "post", 201),
    ("/api/goals", "get", 200),
    ("/api/goals/{goal_id}", "get", 200),
    ("/api/goals/{goal_id}", "patch", 200),
    ("/api/goals/{goal_id}/key-results", "post", 201),
    ("/api/goals/key-results/{kr_id}", "patch", 200),
    ("/api/goals/{goal_id}/progress", "get", 200),
    # habits
    ("/api/habits", "post", 201),
    ("/api/habits", "get", 200),
    ("/api/habits/{habit_id}/check-in", "post", 200),
    ("/api/habits/{habit_id}/uncheck", "post", 200),
    ("/api/habits/{habit_id}/logs", "get", 200),
    # journal
    ("/api/journal", "get", 200),
    ("/api/journal/today", "get", 200),
    ("/api/journal/{day}", "get", 200),
    ("/api/journal/{day}", "put", 200),
    # files
    ("/api/files", "post", 201),
    ("/api/files", "get", 200),
    ("/api/files/links", "post", 201),
    ("/api/files/trash", "get", 200),
    ("/api/files/tasks/{task_id}", "get", 200),
    ("/api/files/{file_id}", "get", 200),
    ("/api/files/{file_id}", "patch", 200),
    ("/api/files/{file_id}/restore", "post", 200),
    ("/api/files/{file_id}/attach/{task_id}", "post", 200),
    ("/api/files/{file_id}/detach/{task_id}", "post", 200),
    # (k3)：subtask 写端点 + EventDetail 端点（前端等此收敛手写类型）
    ("/api/tasks/{task_id}/subtasks", "post", 201),
    ("/api/tasks/{task_id}/subtasks/{subtask_id}", "patch", 200),
    ("/api/schedule/events/{event_id}", "get", 200),
    ("/api/schedule/events/{event_id}", "patch", 200),
]


def test_four_domains_have_typed_response_schemas(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        spec = c.app.openapi()
        for path, method, status in TYPED_PATHS:
            schema = spec["paths"][path][method]["responses"][str(status)][
                "content"]["application/json"]["schema"]
            assert schema, f"{method.upper()} {path} 的 {status} 响应 schema 仍为空对象"
        # 嵌套模型以组件形式存在（openapi 从空 schema 变 $ref）
        schemas = spec["components"]["schemas"]
        for name in ("GoalOut", "KeyResultOut", "GoalProgressItemOut",
                     "HabitOut", "HabitStatusOut", "CheckInOut", "HabitLogOut",
                     "JournalEntryOut", "FileOut"):
            assert name in schemas, f"组件 {name} 缺失"


def test_goal_payload_fields_survive_response_model(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        g = c.post("/api/goals", json={"title": "学期目标", "start_date": "2026-09-01"}).json()
        assert set(g) == {"id", "title", "notes", "status", "start_date", "end_date",
                          "key_results", "deleted_at"}   # deleted_at 回收站语义
        assert g["start_date"] == "2026-09-01" and g["key_results"] == []
        kr = c.post(f"/api/goals/{g['id']}/key-results",
                    json={"title": "读完12本书", "kind": "manual",
                          "target_value": 12, "unit": "本"}).json()
        assert set(kr) == {"id", "goal_id", "title", "kind", "target_value",
                           "current_value", "unit", "link"}
        got = c.get(f"/api/goals/{g['id']}").json()
        assert [k["id"] for k in got["key_results"]] == [kr["id"]]
        kr2 = c.patch(f"/api/goals/key-results/{kr['id']}",
                      json={"current_value": 5}).json()
        assert kr2["current_value"] == 5
        prog = c.get(f"/api/goals/{g['id']}/progress").json()
        assert set(prog[0]) == {"kr_id", "title", "kind", "target_value",
                                "current_value", "unit", "progress"}
        assert prog[0]["progress"] == 42  # round(5/12*100)


def test_habit_payload_fields_survive_response_model(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        h = c.post("/api/habits", json={"name": "跑步"}).json()
        assert set(h) == {"id", "name", "notes", "period", "target_count", "color"}
        lst = c.get("/api/habits").json()
        assert set(lst[0]) == {"id", "name", "notes", "period", "target_count",
                               "color", "status"}
        assert set(lst[0]["status"]) == {"today_count", "period_count", "streak",
                                         "done_today"}
        log = c.post(f"/api/habits/{h['id']}/check-in", json={}).json()
        assert set(log) == {"id", "habit_id", "date", "count"}
        assert c.post(f"/api/habits/{h['id']}/uncheck",
                      json={"date": log["date"]}).json() == {"ok": True}
        assert c.post(f"/api/habits/{h['id']}/check-in", json={}).json()["count"] == 1
        logs = c.get(f"/api/habits/{h['id']}/logs").json()
        assert set(logs[0]) == {"date", "count"}


def test_journal_payload_fields_survive_response_model(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        assert c.get("/api/journal/today").json() is None   # 空日 today 仍为 null
        e = c.put("/api/journal/2026-09-03", json={"content": "x", "mood": "calm"}).json()
        assert set(e) == {"id", "date", "content", "mood", "created_at", "updated_at"}
        assert e["date"] == "2026-09-03" and e["mood"] == "calm"
        assert c.get("/api/journal/{day}".format(day="2026-09-03")).json()["id"] == e["id"]
        assert [i["id"] for i in c.get("/api/journal").json()] == [e["id"]]


def test_file_payload_fields_survive_response_model(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        tid = c.post("/api/tasks", json={"title": "挂文件的任务"}).json()["id"]
        f = c.post("/api/files",
                   files={"file": ("a.txt", b"hello", "text/plain")}).json()
        assert set(f) == {"id", "original_name", "storage_path", "size", "mime_type",
                          "notes", "source_url", "resource_type", "parse_status",
                          "uploaded_at"}
        assert f["original_name"] == "a.txt" and f["resource_type"] == "file"
        link = c.post("/api/files/links",
                      json={"title": "文档", "url": "https://example.com/x"}).json()
        assert set(link) == set(f) and link["resource_type"] == "link"
        assert c.get(f"/api/files/{f['id']}").json()["id"] == f["id"]
        patched = c.patch(f"/api/files/{f['id']}", json={"notes": "n"}).json()
        assert patched["notes"] == "n"
        assert c.post(f"/api/files/{f['id']}/attach/{tid}").json() == {"ok": True}
        assert [i["id"] for i in c.get(f"/api/files/tasks/{tid}").json()] == [f["id"]]
        assert c.post(f"/api/files/{f['id']}/detach/{tid}").json() == {"ok": True}
        assert [i["id"] for i in c.get("/api/files").json()] == sorted(
            [f["id"], link["id"]], reverse=True)
        assert c.delete(f"/api/files/{f['id']}").status_code == 204
        assert [i["id"] for i in c.get("/api/files/trash").json()] == [f["id"]]
        assert c.post(f"/api/files/{f['id']}/restore").json()["id"] == f["id"]


def test_subtask_write_and_event_detail_payload(tmp_path):
    """subtask 写端点与 EventDetail typed 化——载荷守恒 + repeat_note 透出。"""
    with TestClient(create_app(data_dir=tmp_path)) as c:
        tid = c.post("/api/tasks", json={"title": "载体"}).json()["id"]
        r = c.post(f"/api/tasks/{tid}/subtasks", json={"title": "步骤A"})
        assert r.status_code == 201
        body = r.json()
        assert {"id", "task_id", "title", "done", "completed_at", "estimated_minutes"} <= set(body)
        sid = body["id"]
        patched = c.patch(f"/api/tasks/{tid}/subtasks/{sid}", json={"done": True}).json()
        assert patched["done"] is True and patched["task_id"] == tid

        ev = c.post("/api/schedule/events", json={
            "title": "双周课", "date": "2026-09-14", "start_time": "10:00",
            "end_time": "11:40", "recur_rrule": "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO",
            "notes": "注"}).json()
        detail = c.get(f"/api/schedule/events/{ev['id']}").json()
        assert {"id", "title", "date", "start_time", "end_time", "location",
                "category", "recur_rrule", "notes", "repeat_note"} <= set(detail)
        patched_ev = c.patch(f"/api/schedule/events/{ev['id']}",
                             json={"location": "教一"}).json()
        assert patched_ev["location"] == "教一" and "repeat_note" in patched_ev


# ---- (k3)：五域 typed 化（ai reports/configs/skills + notifications/focus） ----

K3_PATHS = [
    # /ai/reports 全系列（briefing/today 同形 ReportOut 一并覆盖）
    ("/ai/reports", "get", 200),
    ("/ai/reports/{report_type}", "post", 200),
    ("/ai/reports/{report_id}", "get", 200),
    ("/ai/briefing/today", "get", 200),
    # /ai/configs 列表/创建
    ("/ai/configs", "get", 200),
    ("/ai/configs", "post", 201),
    # /ai/skills 列表/创建/enable
    ("/ai/skills", "get", 200),
    ("/ai/skills", "post", 201),
    ("/ai/skills/{sid}/enable", "post", 200),
    # /api/notifications 全系列
    ("/api/notifications", "get", 200),
    ("/api/notifications/unread", "get", 200),
    ("/api/notifications/{notification_id}/read", "post", 200),
    ("/api/notifications/read-all", "post", 200),
    # /api/focus 全系列
    ("/api/focus/start", "post", 201),
    ("/api/focus/stop", "post", 200),
    ("/api/focus/current", "get", 200),
    ("/api/focus/logs", "get", 200),
    ("/api/focus/stats", "get", 200),
]


def _k3_quiet_scheduler(monkeypatch):
    """掐掉后台晨报/自动档补写（晨报竞态一族根治，同 test_reports_route）。"""
    from zhishi.domain import reports as reports_mod
    monkeypatch.setattr(reports_mod, "run_briefing_job", lambda *a, **k: None)
    monkeypatch.setattr(reports_mod, "should_run_briefing_now", lambda db, now=None: False)
    import zhishi.domain.autopilot as autopilot_mod
    monkeypatch.setattr(autopilot_mod, "run_autopilot", lambda *a, **k: None)


def test_k3_five_domains_have_typed_response_schemas(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        spec = c.app.openapi()
        for path, method, status in K3_PATHS:
            schema = spec["paths"][path][method]["responses"][str(status)][
                "content"]["application/json"]["schema"]
            assert schema, f"{method.upper()} {path} 的 {status} 响应 schema 仍为空对象"
        schemas = spec["components"]["schemas"]
        for name in ("ReportOut", "ConfigOut", "CreatedOut", "SkillOut",
                     "NotificationOut", "UnreadOut", "TimeLogOut", "FocusStopMissOut",
                     "FocusStatsOut", "ByDayItem", "ByTaskItem"):
            assert name in schemas, f"组件 {name} 缺失"
        # focus stop 是二选一：log | 无进行中回 {"ok": false, "stopped": null}（探针实形）
        stop_schema = spec["paths"]["/api/focus/stop"]["post"]["responses"]["200"][
            "content"]["application/json"]["schema"]
        refs = [alt.get("$ref", "") for alt in stop_schema["anyOf"]]
        assert "#/components/schemas/TimeLogOut" in refs
        assert "#/components/schemas/FocusStopMissOut" in refs


def test_report_payload_fields_survive_response_model(tmp_path, monkeypatch):
    """/ai/reports 全系列：service 播种（规则晨报无需配置）+ 生成（TestModel 离线）。"""
    _k3_quiet_scheduler(monkeypatch)
    with TestClient(create_app(data_dir=tmp_path)) as c:
        with c.app.state.session_factory() as db:
            from zhishi.domain import reports as reports_mod
            seeded = reports_mod.get_or_create_briefing(db, None, date.today())
        today = date.today().isoformat()
        detail = c.get(f"/ai/reports/{seeded.id}")
        assert detail.status_code == 200
        detail = detail.json()
        assert set(detail) == {"id", "report_type", "period_start", "period_end",
                               "title", "content", "model_name", "created_at"}
        assert detail["report_type"] == "briefing"
        assert detail["period_start"] == today and detail["period_end"] == today
        assert detail["model_name"] == "rule"   # 无配置 → 规则降级
        assert isinstance(detail["created_at"], str) and "T" in detail["created_at"]

        rows = c.get("/ai/reports", params={"report_type": "briefing"}).json()
        assert [r["id"] for r in rows] == [seeded.id] and set(rows[0]) == set(detail)
        assert c.get("/ai/reports", params={"report_type": "weekly"}).json() == []
        briefing = c.get("/ai/briefing/today").json()
        assert briefing["id"] == seeded.id and set(briefing) == set(detail)

        # 生成端点：启配置 + TestModel 离线，回包同 ReportOut 形
        from zhishi.domain.models import AIConfig
        with c.app.state.session_factory() as db:
            db.add(AIConfig(name="t", provider_kind="openai_compat",
                            model="test-model", base_url="http://x", enabled=True))
            db.commit()
        monkeypatch.setattr(reports_mod, "build_model",
                            lambda cfg, api_key=None: TestModel(call_tools=[]))
        made = c.post("/ai/reports/daily", json={})
        assert made.status_code == 200
        made = made.json()
        assert set(made) == set(detail) and made["report_type"] == "daily"
        assert made["period_start"] == today and made["model_name"] == "test-model"
        assert c.delete(f"/ai/reports/{made['id']}").status_code == 204


def test_ai_configs_and_skills_payload_fields_survive_response_model(tmp_path):
    """/ai/configs 与 /ai/skills：创建 {id}、列表实形、enable {"ok": true} 守恒。"""
    with TestClient(create_app(data_dir=tmp_path)) as c:
        created = c.post("/ai/configs", json={"name": "本地", "model": "test-model"})
        assert created.status_code == 201
        created = created.json()
        assert set(created) == {"id"} and isinstance(created["id"], int)
        rows = c.get("/ai/configs").json()
        assert set(rows[0]) == {"id", "name", "provider_kind", "model",
                                "base_url", "enabled", "context_window", "max_output_tokens",
                                "input_modalities", "has_api_key", "request_limit", "price_input", "price_output", "reasoning_effort"}
        assert rows[0]["name"] == "本地" and rows[0]["enabled"] is False
        assert rows[0]["base_url"] is None
        assert c.post(f"/ai/configs/{created['id']}/enable").json()["ok"] is True

        skills = c.get("/ai/skills").json()
        assert skills and set(skills[0]) == {"id", "name", "description",
                                             "enabled", "is_builtin"}
        assert skills[0]["is_builtin"] is True   # 启动 seed_builtin_skills 内置
        sk = c.post("/ai/skills", json={"name": "我的技能", "description": "自建"})
        assert sk.status_code == 201
        sk = sk.json()
        assert set(sk) == {"id"}
        assert c.post(f"/ai/skills/{sk['id']}/enable").json() == {"ok": True}
        assert c.get("/ai/skills").json()[-1]["enabled"] is True
        assert c.delete(f"/ai/skills/{sk['id']}").status_code == 204


def test_notifications_payload_fields_survive_response_model(tmp_path):
    """/api/notifications 全系列：service 播种（到点提醒幂等落库）后经端点取实形。"""
    from zhishi.domain import notifications as notif_service
    from zhishi.domain.models import Task
    with TestClient(create_app(data_dir=tmp_path)) as c:
        due = datetime(2026, 9, 1, 8, 0)   # 远离扫描窗口，后台 reminder-scan 不干扰
        with c.app.state.session_factory() as db:
            db.add(Task(title="交作业", due_date=due, remind_offsets="[0]",
                        status="todo"))
            db.commit()
            assert notif_service.record_due_reminders(db, now=due) == 1
        rows = c.get("/api/notifications").json()
        assert len(rows) == 1
        assert set(rows[0]) == {"id", "task_id", "kind", "title", "body",
                                "remind_at", "read_at", "target_path"}
        assert rows[0]["target_path"] == f"/board?task={rows[0]['task_id']}"
        assert rows[0]["task_id"] is not None and rows[0]["read_at"] is None
        assert rows[0]["kind"] == "reminder" and "交作业" in rows[0]["title"]
        assert c.get("/api/notifications/unread").json() == {"count": 1}
        assert c.post(f"/api/notifications/{rows[0]['id']}/read").json() == {"ok": True}
        assert c.get("/api/notifications/unread").json() == {"count": 0}
        assert c.post("/api/notifications/read-all").json() == {"ok": True}


def test_focus_payload_fields_survive_response_model(tmp_path):
    """/api/focus 全系列：service 播种计时；current 无运行中 → null；stop 落空回
    {"ok": false, "stopped": null}（与 TimeLogOut 组成 union，探针实形）。"""
    from zhishi.domain.focus import service as focus_service
    from zhishi.domain.focus.schemas import TimerStart
    with TestClient(create_app(data_dir=tmp_path)) as c:
        assert c.get("/api/focus/current").json() is None
        with c.app.state.session_factory() as db:
            focus_service.start_timer(db, TimerStart(task_title="写作"))
            assert focus_service.stop_timer(db, None) is not None

        run = c.post("/api/focus/start", json={"task_title": "阅读", "kind": "break"})
        assert run.status_code == 201
        run = run.json()
        cur = c.get("/api/focus/current").json()
        assert cur["id"] == run["id"]   # 再 start 顶替 current 指向最新一条
        expected = {"id", "task_id", "task_title", "kind", "started_at",
                    "ended_at", "minutes"}
        assert set(cur) == expected
        assert cur["task_id"] is None and cur["ended_at"] is None
        assert cur["kind"] == "break" and cur["task_title"] == "阅读"

        stopped = c.post("/api/focus/stop", json={}).json()
        assert set(stopped) == expected and stopped["ended_at"] is not None
        assert c.post("/api/focus/stop", json={}).json() == {"ok": False, "stopped": None}

        logs = c.get("/api/focus/logs").json()
        assert [l["id"] for l in logs] == sorted((l["id"] for l in logs), reverse=True)
        assert len(logs) == 2 and all(set(l) == expected for l in logs)

        stats = c.get("/api/focus/stats").json()
        assert set(stats) == {"by_day", "by_task", "total_minutes"}
        assert len(stats["by_day"]) == 7   # 缺省 days=7 逐日补零
        assert set(stats["by_day"][0]) == {"date", "minutes"}
        assert {t["task_title"] for t in stats["by_task"]} == {"写作", "阅读"}
        assert all(set(t) == {"task_title", "minutes"} for t in stats["by_task"])
        assert stats["total_minutes"] == 0   # 秒级启停不计分钟


# ---- 最后 18 个空 schema 端点 typed 化 + 全量总回归（防再漏） ----

FINAL_PATHS = [
    ("/api/tasks/tags", "get", 200),
    ("/api/schedule/events", "post", 201),
    ("/api/stats/summary", "get", 200),
    ("/api/stats/daily", "get", 200),
    ("/api/stats/by-tag", "get", 200),
    ("/api/stats/by-priority", "get", 200),
    ("/api/stats/risk", "get", 200),
    ("/api/settings", "get", 200),
    ("/api/settings", "put", 200),
    ("/api/ical/import", "post", 200),
    ("/ai/attachments", "post", 201),
    ("/ai/conversations", "get", 200),
    ("/ai/conversations/{cid}", "get", 200),
    ("/ai/runs/{run_id}/cancel", "post", 200),
    ("/ai/mcp/servers", "post", 201),
    ("/ai/mcp/servers/{sid}/test", "post", 200),
    ("/ai/mcp/servers/{sid}/tools", "get", 200),
]


def test_final_18_endpoints_have_typed_response_schemas(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        spec = c.app.openapi()
        for path, method, status in FINAL_PATHS:
            schema = spec["paths"][path][method]["responses"][str(status)][
                "content"]["application/json"]["schema"]
            assert schema, f"{method.upper()} {path} 的 {status} 响应 schema 仍为空对象"
        schemas = spec["components"]["schemas"]
        for name in ("TagOut", "EventDetailOut", "StatsSummary", "StatsDailyPoint",
                     "StatsTagItem", "StatsPriorityItem", "RiskItem",
                     "IcalImportOut", "AttachmentOut", "ConversationOut", "MessageOut",
                     "CancelOut", "CreatedOut", "MCPTestOut", "MCPToolOut"):
            assert name in schemas, f"组件 {name} 缺失"
        # ical export 是 text/calendar 流：不再误标 application/json 空 schema
        export_content = spec["paths"]["/api/ical/export"]["get"]["responses"]["200"][
            "content"]
        assert set(export_content) == {"text/calendar"}
        assert export_content["text/calendar"]["schema"], "export 需给出字符串 schema"


def test_openapi_no_empty_json_schema_anywhere(tmp_path):
    """收尾总回归：openapi 全 paths 扫描，任何 application/json 响应 schema
    不得为空对象（text/event-stream 等非 JSON 流式媒体类型不在此列）。防再漏。"""
    with TestClient(create_app(data_dir=tmp_path)) as c:
        spec = c.app.openapi()
        empties = []
        for path, item in spec["paths"].items():
            for method, op in item.items():
                if method not in ("get", "post", "put", "patch", "delete"):
                    continue
                if not isinstance(op, dict):
                    continue
                for st, resp in (op.get("responses") or {}).items():
                    js = ((resp or {}).get("content") or {}).get("application/json")
                    if js is not None and js.get("schema") == {}:
                        empties.append(f"{method.upper()} {path} -> {st}")
        assert empties == [], f"application/json 空 schema 残留: {empties}"


def test_tags_stats_settings_payload_fields_survive_response_model(tmp_path):
    """/api/tasks/tags + /api/stats 全系列 + /api/settings：实形守恒。"""
    with TestClient(create_app(data_dir=tmp_path)) as c:
        c.post("/api/tasks", json={"title": "统计载体", "tag_names": ["工作"]})
        tags = c.get("/api/tasks/tags").json()
        assert tags and set(tags[0]) == {"id", "name", "color"}
        assert tags[0]["name"] == "工作"

        s = c.get("/api/stats/summary").json()
        assert set(s) == {"todo", "doing", "done", "overdue", "due_today", "due_7d"}
        assert s["todo"] == 1 and s["done"] == 0
        d = c.get("/api/stats/daily").json()
        assert len(d) == 14 and set(d[0]) == {"date", "completed", "created"}
        assert all(isinstance(x["created"], int) for x in d)
        bt = c.get("/api/stats/by-tag").json()
        assert bt and set(bt[0]) == {"tag", "total", "done"}
        assert bt[0]["tag"] == "工作" and bt[0]["total"] == 1 and bt[0]["done"] == 0
        bp = c.get("/api/stats/by-priority").json()
        assert [x["priority"] for x in bp] == ["high", "medium", "low"]
        assert all(set(x) == {"priority", "todo", "doing", "done"} for x in bp)
        c.post("/api/tasks", json={"title": "无截止的高优", "priority": "high"})
        risk = c.get("/api/stats/risk").json()
        assert risk and all(set(x) == {"task_id", "title", "score", "due_date"}
                            for x in risk)
        hit = next(x for x in risk if x["title"] == "无截止的高优")
        assert hit["score"] == 15 and hit["due_date"] is None

        got = c.get("/api/settings").json()
        assert got["working_hours_start"] == "09:00"
        assert all(isinstance(k, str) and isinstance(v, str) for k, v in got.items())
        put = c.put("/api/settings", json={"settings": {"working_hours_start": "08:30"}})
        assert put.status_code == 200
        assert put.json()["working_hours_start"] == "08:30"
        assert c.get("/api/settings").json()["working_hours_start"] == "08:30"


def test_event_create_and_ical_import_payload_conserved(tmp_path):
    """POST /api/schedule/events（EventDetailOut 直挂）与 /api/ical/import 实形守恒。"""
    with TestClient(create_app(data_dir=tmp_path)) as c:
        ev = c.post("/api/schedule/events", json={
            "title": "例会", "date": "2026-09-14", "start_time": "10:00"}).json()
        assert set(ev) == {"id", "title", "date", "start_time", "end_time", "location",
                               "category", "recur_rrule", "notes", "repeat_note", "remind_offsets", "reminder_time"}
        assert ev["end_time"] is None and ev["repeat_note"] is None

        ics = c.get("/api/ical/export").text
        assert "BEGIN:VCALENDAR" in ics
        r = c.post("/api/ical/import", files={"file": ("t.ics", ics, "text/calendar")})
        assert r.status_code == 200
        assert set(r.json()) == {"created"} and r.json()["created"] >= 1


def test_ai_misc_endpoints_payload_fields_survive_response_model(tmp_path, monkeypatch):
    """/ai/attachments、conversations 列表/详情、runs cancel、mcp create/test/tools 守恒。"""
    with TestClient(create_app(data_dir=tmp_path)) as c:
        up = c.post("/ai/attachments", files={"file": ("a.txt", b"hello", "text/plain")})
        assert up.status_code == 201
        assert set(up.json()) == {"file_id", "name", "kind", "parse_status"}
        assert up.json()["name"] == "a.txt"

        from zhishi.domain.models import AIConversation, AIMessage
        with c.app.state.session_factory() as db:
            conv = AIConversation(title="会话A")
            db.add(conv); db.commit(); db.refresh(conv)
            db.add(AIMessage(conversation_id=conv.id, role="user",
                             display_json='{"text": "你好"}', history_json="[]"))
            db.commit()
            cid = conv.id
        rows = c.get("/ai/conversations").json()
        assert rows and set(rows[0]) == {"id", "title", "updated_at"}
        assert rows[0]["id"] == cid and rows[0]["title"] == "会话A"
        msgs = c.get(f"/ai/conversations/{cid}").json()
        assert len(msgs) == 1 and set(msgs[0]) == {"id", "role", "display", "created_at"}
        assert msgs[0]["role"] == "user" and msgs[0]["display"] == {"text": "你好"}

        assert c.post("/ai/runs/absent-run/cancel").json() == {"ok": False}

        class _Tok:
            def __init__(self):
                self.cancelled = False

            def cancel(self):
                self.cancelled = True
        tok = _Tok()
        c.app.state.cancel_tokens["rid1"] = tok
        assert c.post("/ai/runs/rid1/cancel").json() == {"ok": True}
        assert tok.cancelled is True

        made = c.post("/ai/mcp/servers",
                      json={"name": "srv", "transport": "http", "url": "http://x"})
        assert made.status_code == 201 and set(made.json()) == {"id"}
        sid = made.json()["id"]

        import zhishi.adapters.mcp_client as mcp_client

        async def _ok_tools(row, timeout=None, use_cache=True):
            return [{"name": "t1", "description": "d", "input_schema": {},
                    "read_only": True}]

        monkeypatch.setattr(mcp_client, "list_tools", _ok_tools)
        ok = c.post(f"/ai/mcp/servers/{sid}/test")
        assert ok.status_code == 200
        assert ok.json() == {"ok": True, "tool_count": 1,
                             "tools": [{"name": "t1", "description": "d"}]}
        tools = c.get(f"/ai/mcp/servers/{sid}/tools").json()
        assert tools == [{"name": "t1", "description": "d", "input_schema": {},
                          "read_only": True}]

        async def _boom(row, timeout=None, use_cache=True):
            raise RuntimeError("连不上")
        monkeypatch.setattr(mcp_client, "list_tools", _boom)
        bad = c.post(f"/ai/mcp/servers/{sid}/test")
        assert bad.status_code == 200
        assert bad.json() == {"ok": False, "tool_count": 0, "error": "连不上"}
