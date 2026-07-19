"""习惯打卡 + 日记 + 风险预测 + iCal + AI 新工具（第三阶段后端）。"""
from datetime import date, datetime, timedelta
from io import BytesIO


# ---- 习惯打卡 ----

def test_habit_crud_and_check_flow(client):
    habit = client.post("/habits", json={"name": "喝水", "target_count": 2}).json()
    assert habit["today_count"] == 0
    assert habit["done_today"] is False

    client.post(f"/habits/{habit['id']}/check", json={})
    after_one = client.get("/habits").json()[0]
    assert after_one["today_count"] == 1
    assert after_one["done_today"] is False  # 目标是 2 次

    client.post(f"/habits/{habit['id']}/check", json={})
    after_two = client.get("/habits").json()[0]
    assert after_two["today_count"] == 2
    assert after_two["done_today"] is True
    assert after_two["streak"] == 1

    # 撤销一次 → 不再达标
    client.post(f"/habits/{habit['id']}/uncheck", json={})
    after_uncheck = client.get("/habits").json()[0]
    assert after_uncheck["today_count"] == 1
    assert after_uncheck["done_today"] is False

    # 更新与删除
    client.put(f"/habits/{habit['id']}", json={"name": "多喝水"})
    assert client.get("/habits").json()[0]["name"] == "多喝水"
    assert client.delete(f"/habits/{habit['id']}").status_code == 204
    assert client.get("/habits").json() == []


def test_habit_streak_counts_consecutive_days(client, db_session):
    from app.models import Habit, HabitLog

    habit = Habit(name="晨跑", target_count=1)
    db_session.add(habit)
    db_session.commit()
    today = date.today()
    for offset in (0, 1, 2, 4):  # 缺第 3 天 → streak 从昨天连续 2 天 + 今天 = 3
        db_session.add(HabitLog(habit_id=habit.id, date=today - timedelta(days=offset), count=1))
    db_session.commit()

    body = client.get("/habits").json()[0]
    assert body["streak"] == 3

    # 今天未打卡时， streak 算到昨天（2 天）不打断
    db_session.query(HabitLog).filter_by(habit_id=habit.id, date=today).delete()
    db_session.commit()
    body = client.get("/habits").json()[0]
    assert body["streak"] == 2


def test_habit_logs_endpoint(client):
    habit = client.post("/habits", json={"name": "阅读"}).json()
    client.post(f"/habits/{habit['id']}/check", json={})
    logs = client.get(f"/habits/{habit['id']}/logs?days=7").json()
    assert len(logs) == 1
    assert logs[0]["count"] == 1


# ---- 日记 ----

def test_journal_upsert_get_list_delete(client):
    today = date.today().isoformat()
    # 404 起步
    assert client.get(f"/journal/{today}").status_code == 404
    # upsert 创建
    resp = client.put(f"/journal/{today}", json={"content": "第一天 **日记**", "mood": "好"})
    assert resp.status_code == 200
    assert resp.json()["mood"] == "好"
    # upsert 覆盖同一天（不重复）
    client.put(f"/journal/{today}", json={"content": "改写后的日记", "mood": "平"})
    listing = client.get("/journal").json()
    assert len(listing) == 1
    assert listing[0]["preview"].startswith("改写后的日记")
    # 删除
    assert client.delete(f"/journal/{today}").status_code == 204
    assert client.get(f"/journal/{today}").status_code == 404


# ---- 风险预测 ----

def test_risk_scoring_rules(client):
    now = datetime.now()
    # 逾期 2 天 → 50+4
    client.post("/tasks", json={"title": "逾期任务", "due_date": (now - timedelta(days=2)).isoformat()})
    # 明天截止且进度 20% → 30
    client.post(
        "/tasks",
        json={"title": "临近低进度", "due_date": (now + timedelta(days=1)).isoformat(), "progress": 20},
    )
    # 高优先级无截止无排期 → 15
    client.post("/tasks", json={"title": "高优未安排", "priority": "高"})
    # 正常任务不应出现
    client.post("/tasks", json={"title": "普通任务", "due_date": (now + timedelta(days=30)).isoformat()})

    items = client.get("/stats/risk").json()["items"]
    by_title = {i["title"]: i for i in items}
    assert "逾期任务" in by_title
    assert by_title["逾期任务"]["score"] >= 50
    assert any("逾期" in r for r in by_title["逾期任务"]["reasons"])
    assert "临近低进度" in by_title
    assert by_title["临近低进度"]["score"] == 30
    assert "高优未安排" in by_title
    assert "普通任务" not in by_title
    # 按分数降序
    scores = [i["score"] for i in items]
    assert scores == sorted(scores, reverse=True)


# ---- iCal 导入导出 ----

def test_ical_export_contains_vevent(client):
    client.post(
        "/tasks",
        json={
            "title": "导出任务,带逗号",
            "due_date": "2026-07-20T18:00:00",
            "tags": ["工作"],
        },
    )
    resp = client.get("/export/tasks.ics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/calendar")
    body = resp.text
    assert "BEGIN:VCALENDAR" in body
    assert "BEGIN:VEVENT" in body
    assert "SUMMARY:导出任务\\,带逗号" in body
    assert "DTSTART:20260720T180000" in body
    assert "X-ZHISHI-PRIORITY:中" in body
    assert "CATEGORIES:工作" in body


def test_ical_import_creates_tasks(client):
    ics = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:ext-1@test\r\n"
        "SUMMARY:外部会议\r\n"
        "DTSTART:20260725T100000\r\n"
        "DTEND:20260725T110000\r\n"
        "DESCRIPTION:季度复盘\\n带上数据\r\n"
        "END:VEVENT\r\n"
        "BEGIN:VEVENT\r\n"
        "SUMMARY:全日程任务\r\n"
        "DTSTART;VALUE=DATE:20260726\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    resp = client.post(
        "/import/tasks.ics",
        files={"file": ("plan.ics", BytesIO(ics.encode("utf-8")), "text/calendar")},
    )
    assert resp.status_code == 200
    assert resp.json()["created"] == 2

    tasks = client.get("/tasks").json()
    meeting = next(t for t in tasks if t["title"] == "外部会议")
    assert meeting["due_date"].startswith("2026-07-25T11:00")
    assert "季度复盘" in meeting["notes"]
    allday = next(t for t in tasks if t["title"] == "全日程任务")
    assert allday["due_date"] is None or allday["due_date"].startswith("2026-07-26")


def test_ical_import_rejects_empty(client):
    resp = client.post(
        "/import/tasks.ics",
        files={"file": ("empty.ics", BytesIO(b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"), "text/calendar")},
    )
    assert resp.status_code == 400


# ---- AI 新工具 ----

def test_ai_tool_habit_and_journal_flow(db_session):
    from app.services import ai_tool_service

    result = ai_tool_service.execute_tool(
        db_session, "create_habit", {"name": "冥想", "period": "daily"}
    )
    assert result["ok"] is True
    habit_id = result["habit"]["id"]

    result = ai_tool_service.execute_tool(db_session, "check_in_habit", {"habit_id": habit_id})
    assert result["ok"] is True
    assert result["habit"]["today_count"] == 1

    result = ai_tool_service.execute_tool(db_session, "list_habits", {})
    assert any(h["id"] == habit_id for h in result["habits"])

    result = ai_tool_service.execute_tool(
        db_session, "write_journal", {"content": "今天完成了很多事", "mood": "好"}
    )
    assert result["ok"] is True
    result = ai_tool_service.execute_tool(db_session, "list_journal_entries", {})
    assert result["entries"][0]["preview"].startswith("今天完成了很多事")

    # 空内容日记被拒绝
    result = ai_tool_service.execute_tool(db_session, "write_journal", {"content": "  "})
    assert result["ok"] is False
