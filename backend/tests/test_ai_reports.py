"""AI 日报/周报：数据收集、prompt 构造、生成与 CRUD 端点。"""
from datetime import date, datetime

from sqlalchemy import inspect

from app.models import AIConfig, AIReport, Task
from app.services import ai_report_service


# ---- helpers ----
def _task(db_session, title, *, status="待办", due=None, updated=None, created=None,
          progress=0, priority="中"):
    now = datetime.now()
    t = Task(
        title=title, status=status, priority=priority, progress=progress,
        due_date=due, created_at=created or now, updated_at=updated or now,
    )
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t


# ---- Task 1: 模型 ----
def test_ai_report_table_exists(db_session):
    tables = set(inspect(db_session.bind).get_table_names())
    assert "ai_reports" in tables


# ---- Task 3: collect_report_data ----
def test_collect_daily_report_data(db_session):
    today = date(2026, 7, 15)
    _task(db_session, "完成A", status="完成", updated=datetime(2026, 7, 15, 12))
    _task(db_session, "进行B", status="进行中", updated=datetime(2026, 7, 15, 9))
    _task(db_session, "今日截止C", due=datetime(2026, 7, 15, 18))
    _task(db_session, "逾期D", due=datetime(2026, 7, 14, 9))
    _task(db_session, "明日E", due=datetime(2026, 7, 16, 9))

    data = ai_report_service.collect_report_data(db_session, "daily", today)
    assert data["report_type"] == "daily"
    assert data["period_start"] == today
    assert data["period_end"] == today
    assert data["next_label"] == "明日"
    assert [t["title"] for t in data["completed"]] == ["完成A"]
    assert [t["title"] for t in data["in_progress"]] == ["进行B"]
    assert [t["title"] for t in data["due_in_window"]] == ["今日截止C"]
    assert [t["title"] for t in data["overdue"]] == ["逾期D"]
    assert [t["title"] for t in data["next"]] == ["明日E"]


def test_collect_weekly_report_data(db_session):
    # 2026-07-15 是周三 → 本周周一 7/13 ~ 周日 7/19；下周 7/20 ~ 7/26
    wed = date(2026, 7, 15)
    _task(db_session, "本周完成", status="完成", updated=datetime(2026, 7, 14, 10))
    _task(db_session, "本周截止", due=datetime(2026, 7, 16, 9))
    _task(db_session, "上周逾期", due=datetime(2026, 7, 10, 9))
    _task(db_session, "下周截止", due=datetime(2026, 7, 22, 9))

    data = ai_report_service.collect_report_data(db_session, "weekly", wed)
    assert data["period_start"] == date(2026, 7, 13)
    assert data["period_end"] == date(2026, 7, 19)
    assert data["next_label"] == "下周"
    assert [t["title"] for t in data["completed"]] == ["本周完成"]
    assert [t["title"] for t in data["due_in_window"]] == ["本周截止"]
    assert [t["title"] for t in data["overdue"]] == ["上周逾期"]
    assert [t["title"] for t in data["next"]] == ["下周截止"]


def test_build_report_prompt_includes_window():
    data = {
        "report_type": "daily",
        "period_start": date(2026, 7, 15),
        "period_end": date(2026, 7, 15),
        "next_label": "明日",
        "next_range": ["2026-07-16", "2026-07-16"],
        "completed": [],
        "in_progress": [],
        "due_in_window": [],
        "overdue": [],
        "new_in_window": [],
        "next": [],
        "summary": {"total": 0},
    }
    system, user = ai_report_service.build_report_prompt(None, "daily", data)
    assert "报告" in system
    assert "2026-07-15" in user


# ---- Task 4: 端点 ----
def test_generate_report_requires_enabled_config(client):
    resp = client.post("/ai/reports/generate", json={"report_type": "daily"})
    assert resp.status_code == 400


def test_generate_report_via_endpoint(db_session, client, monkeypatch):
    cfg = AIConfig(
        provider="openai_chat", model="gpt-test", api_key="sk-x",
        enabled=True, name="t", assistant_name="知时助手",
    )
    db_session.add(cfg)
    db_session.commit()

    async def fake_call(req):
        return {"choices": [{"message": {"content": "# 今日回顾\n完成了 A"}}]}

    monkeypatch.setattr("app.services.ai_client.call_provider", fake_call)
    resp = client.post("/ai/reports/generate", json={"report_type": "daily"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["report_type"] == "daily"
    assert body["id"] > 0
    assert "回顾" in body["content"]


def test_list_get_delete_report(db_session, client):
    r = AIReport(
        report_type="daily", period_start=date(2026, 7, 15),
        period_end=date(2026, 7, 15), title="日报", content="内容", model_name="m",
    )
    db_session.add(r)
    db_session.commit()
    db_session.refresh(r)

    lst = client.get("/ai/reports").json()
    assert len(lst) == 1 and lst[0]["id"] == r.id

    one = client.get(f"/ai/reports/{r.id}").json()
    assert one["content"] == "内容"

    assert client.delete(f"/ai/reports/{r.id}").status_code == 204
    assert client.get(f"/ai/reports/{r.id}").status_code == 404


def test_collect_report_data_trims_buckets(db_session):
    today = date(2026, 7, 15)
    for i in range(5):
        _task(db_session, f"逾期{i}", due=datetime(2026, 7, 10, 9))
    data = ai_report_service.collect_report_data(db_session, "daily", today, task_limit=2)
    assert len(data["overdue"]) == 2
    assert data["omitted"]["overdue"] == 3
    # summary 仍保留真实总数
    assert data["summary"]["overdue"] == 5


def test_build_report_prompt_notes_omitted():
    data = {
        "report_type": "daily",
        "period_start": date(2026, 7, 15),
        "period_end": date(2026, 7, 15),
        "next_label": "明日",
        "next_range": ["2026-07-16", "2026-07-16"],
        "completed": [],
        "in_progress": [],
        "due_in_window": [],
        "overdue": [],
        "new_in_window": [],
        "next": [],
        "omitted": {"overdue": 3},
        "summary": {"total": 0, "overdue": 3},
    }
    _, user = ai_report_service.build_report_prompt(None, "daily", data)
    assert "另有 3 项未展示" in user
