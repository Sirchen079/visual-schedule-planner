"""AI 报告（日报/周报/晨报）：数据收集/提示词/生成落库/幂等/规则降级。全程离线。"""
import json
from datetime import date, datetime, timedelta

import pytest
from pydantic_ai.models.test import TestModel

from zhishi.domain import reports
from zhishi.domain.models import AIConfig, AIReport, Task


def make_cfg(db, enabled=True) -> AIConfig:
    cfg = AIConfig(name="t", provider_kind="openai_compat", model="test-model",
                   base_url="http://x", enabled=enabled)
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg


def seed_tasks(db) -> None:
    now = datetime.now()
    db.add(Task(title="昨日完成任务", status="done", completed_at=now - timedelta(days=1),
                due_date=now - timedelta(days=1)))
    db.add(Task(title="逾期任务甲", due_date=now - timedelta(days=2)))
    db.add(Task(title="今日截止任务", due_date=now))
    db.commit()


def patch_test_model(monkeypatch) -> None:
    monkeypatch.setattr(reports, "build_model",
                        lambda cfg, api_key=None: TestModel(call_tools=[]))


def test_collect_data_daily_window_and_keys(db):
    seed_tasks(db)
    target = date.today()
    data = reports.collect_data(db, "daily", target)
    assert data["report_type"] == "daily"
    assert data["period"]["start"] == target.isoformat()
    assert data["period"]["end"] == target.isoformat()
    for key in ("summary", "trend", "by_tag", "insights", "focus", "overdue", "due_in_period"):
        assert key in data
    assert any("逾期任务甲" in t for t in data["overdue"])
    assert any("今日截止任务" in t for t in data["due_in_period"])


def test_collect_data_weekly_window_is_iso_week(db):
    target = date.today()
    data = reports.collect_data(db, "weekly", target)
    start = target - timedelta(days=target.weekday())
    assert data["period"]["start"] == start.isoformat()
    assert data["period"]["end"] == (start + timedelta(days=6)).isoformat()


def test_collect_data_task_list_capped_at_20(db):
    now = datetime.now()
    for i in range(30):
        db.add(Task(title=f"逾期{i:02d}", due_date=now - timedelta(days=1)))
    db.commit()
    data = reports.collect_data(db, "daily", date.today())
    assert len(data["overdue"]) <= reports.TASK_LIMIT


def test_build_prompts_contract():
    data = {"report_type": "daily", "summary": {}}
    system, user = reports.build_prompts(None, "daily", data)
    assert "幕僚" in system and "日报" in system
    assert "回顾" in system and "只基于给定数据" in system
    assert json.loads(user) == data
    system_w, _ = reports.build_prompts(None, "weekly", data)
    assert "周报" in system_w


def test_generate_daily_report_persists(db, monkeypatch):
    seed_tasks(db)
    cfg = make_cfg(db)
    patch_test_model(monkeypatch)
    row = reports.generate(db, cfg, "daily", date.today())
    assert isinstance(row, AIReport)
    assert row.report_type == "daily"
    assert row.content.strip() != ""
    assert row.model_name == "test-model"
    assert row.period_start == row.period_end == date.today()
    assert db.get(AIReport, row.id) is not None


def test_generate_weekly_report_period(db, monkeypatch):
    make_cfg(db)
    patch_test_model(monkeypatch)
    target = date.today()
    row = reports.generate(db, db.query(AIConfig).first(), "weekly", target)
    start = target - timedelta(days=target.weekday())
    assert row.period_start == start
    assert row.period_end == start + timedelta(days=6)


def test_generate_model_failure_raises_no_row(db, monkeypatch):
    make_cfg(db)

    def boom(cfg, api_key=None):
        raise RuntimeError("网络错误")

    monkeypatch.setattr(reports, "build_model", boom)
    with pytest.raises(Exception, match="网络错误"):
        reports.generate(db, db.query(AIConfig).first(), "daily", date.today())
    assert db.query(AIReport).count() == 0


def test_generate_rejects_unknown_type(db, monkeypatch):
    make_cfg(db)
    patch_test_model(monkeypatch)
    with pytest.raises(ValueError, match="report_type"):
        reports.generate(db, db.query(AIConfig).first(), "monthly", date.today())


def test_briefing_rule_fallback_without_config(db):
    seed_tasks(db)
    row = reports.generate_briefing(db, None, date.today())
    assert row.report_type == "briefing"
    assert row.model_name == "rule"
    assert "逾期" in row.content or "今日截止" in row.content


def test_briefing_ai_generate_and_same_day_idempotent(db, monkeypatch):
    seed_tasks(db)
    make_cfg(db)
    patch_test_model(monkeypatch)
    first = reports.get_or_create_briefing(db, db.query(AIConfig).first(), date.today())
    assert first.model_name == "test-model"
    second = reports.get_or_create_briefing(db, db.query(AIConfig).first(), date.today())
    assert second.id == first.id
    assert db.query(AIReport).filter_by(report_type="briefing").count() == 1


def test_briefing_ai_failure_falls_back_to_rule(db, monkeypatch):
    seed_tasks(db)
    make_cfg(db)

    def boom(cfg, api_key=None):
        raise RuntimeError("网关 502")

    monkeypatch.setattr(reports, "build_model", boom)
    row = reports.get_or_create_briefing(db, db.query(AIConfig).first(), date.today())
    assert row.model_name == "rule"
    assert row.content.strip() != ""


def test_build_rule_briefing_mentions_sections(db):
    seed_tasks(db)
    data = reports.collect_data(db, "briefing", date.today())
    text = reports.build_rule_briefing(data)
    assert 0 < len(text) <= 500
    assert ("逾期" in text) or ("今日" in text)
