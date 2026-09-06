from datetime import date
from fastapi.testclient import TestClient
from zhishi.server.app import create_app


def test_full_journey(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        # 任务 → 子任务 → 完成
        r = c.post("/api/tasks", json={"title": "重构知时", "priority": "high"})
        assert r.status_code == 201
        tid = r.json()["id"]
        r = c.post(f"/api/tasks/{tid}/subtasks", json={"title": "写计划"})
        sid = r.json()["id"]
        r = c.patch(f"/api/tasks/{tid}/subtasks/{sid}", json={"done": True})
        assert r.status_code == 200

        # 排期 + 独立日程 + 冲突 + 空闲
        r = c.post("/api/schedule/entries", json={"task_id": tid, "date": "2026-09-07",
                                                  "start_time": "10:00", "end_time": "11:00"})
        assert r.status_code == 201
        r = c.post("/api/schedule/events", json={"title": "高数", "date": "2026-09-07",
                                                 "start_time": "10:30", "end_time": "12:00",
                                                 "recur_rrule": "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO"})
        eid = r.json()["id"]
        r = c.get("/api/schedule/day", params={"date": "2026-09-07"})
        assert len(r.json()["items"]) == 2
        r = c.get("/api/schedule/conflicts", params={"start": "2026-09-07", "end": "2026-09-07"})
        assert len(r.json()) == 1
        r = c.get("/api/schedule/free-slots", params={"date": "2026-09-07", "min_minutes": 30})
        assert r.status_code == 200

        # 目标 / 习惯 / 日记 / 番茄钟 / 统计 / 设置 / 通知
        assert c.post("/api/goals", json={"title": "G"}).status_code == 201
        assert c.post("/api/habits", json={"name": "跑步"}).status_code == 201
        assert c.put("/api/journal/2026-09-03", json={"content": "x"}).status_code == 200
        assert c.post("/api/focus/start", json={"task_title": "写作"}).status_code == 201
        # 唯一任务已因子任务全完成而自动闭环（任务12 语义），故统计锚 done 而非 todo
        assert c.get("/api/stats/summary").json()["done"] >= 1
        assert c.put("/api/settings", json={"settings": {"working_hours_start": "08:30"}}).status_code == 200
        assert c.get("/api/notifications/unread").json()["count"] == 0

        # ICS 导出导入闭环
        ics_text = c.get("/api/ical/export").text
        assert "BEGIN:VCALENDAR" in ics_text
        r = c.post("/api/ical/import", files={"file": ("t.ics", ics_text, "text/calendar")})
        assert r.status_code == 200 and r.json()["created"] >= 1
