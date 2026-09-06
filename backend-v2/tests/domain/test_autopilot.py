"""秘书自动档：确定性排程（负载最轻/日上限/总量上限）+ 高优拆解 + 幂等 + 开关。"""
import json
from datetime import date, datetime, timedelta

from freezegun import freeze_time
from pydantic_ai.messages import ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from zhishi.domain import autopilot, settingsvc
from zhishi.domain.models import AIConfig, AIReport, Subtask, Task, TaskScheduleEntry
from zhishi.domain.schedule import service as schedule_svc


def enable(db, on=True):
    settingsvc.set_setting(db, "feature_autopilot_enabled", "true" if on else "false")


def make_cfg(db) -> AIConfig:
    cfg = AIConfig(name="t", provider_kind="openai_compat", model="mock-model",
                   base_url="http://x", enabled=True)
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg


def test_disabled_by_default_returns_disabled(db):
    out = autopilot.run_autopilot(db, None, date.today())
    assert out == {"ran": False, "reason": "disabled"}
    assert db.query(AIReport).count() == 0
    assert db.query(TaskScheduleEntry).count() == 0


def test_gate_requires_after_0800(db):
    enable(db)
    today = date.today().isoformat()   # 动态日期：与 run_autopilot 的 date.today 同源，防跨日错位
    with freeze_time(f"{today} 07:55:00"):
        assert autopilot.should_run_now(db) is False
    with freeze_time(f"{today} 08:05:00"):
        assert autopilot.should_run_now(db) is True
    autopilot.run_autopilot(db, None, date.today())
    with freeze_time(f"{today} 08:10:00"):
        assert autopilot.should_run_now(db) is False   # 今日已跑


@freeze_time("2026-09-04 08:05:00")
def test_full_run_schedules_to_lightest_day_and_breaks_down(db, monkeypatch):
    now = datetime.now()
    db.add(Task(title="三日内任务", due_date=now + timedelta(days=3), priority="medium"))
    db.add(Task(title="高优拆解任务", due_date=now + timedelta(days=1), priority="high"))
    db.add(Task(title="已有排期任务", due_date=now + timedelta(days=3)))
    db.commit()
    seeded = db.query(Task).filter_by(title="已有排期任务").first()
    schedule_svc.assign_task_to_day(db, seeded.id, now.date())   # 今天已有 1 条负载

    monkeypatch.setattr(autopilot, "build_model", lambda cfg, api_key=None: TestModel(
        custom_output_text=json.dumps(["子任务一", "子任务二", "子任务三"], ensure_ascii=False)))
    enable(db)
    out = autopilot.run_autopilot(db, make_cfg(db), date.today())

    assert out["ran"] is True
    assert {a["kind"] for a in out["actions"]} == {"assign", "breakdown"}

    # 排程（负载=预估时长，平局取最早）：今天 0 分钟 → 高优任务落今天（第 2 个名额）；
    # 三日内任务落时今天已满 2 条 → 顺延到负载最轻的明天（且不晚于各自截止）
    t1 = db.query(Task).filter_by(title="高优拆解任务").first()
    e1 = db.query(TaskScheduleEntry).filter_by(task_id=t1.id).one()
    assert e1.source == "ai"
    assert e1.date == date.today()
    t2 = db.query(Task).filter_by(title="三日内任务").first()
    e2 = db.query(TaskScheduleEntry).filter_by(task_id=t2.id).one()
    assert e2.date == date.today() + timedelta(days=1)

    # 拆解：高优、临近截止、无子任务 → 模型拆 3 条
    subs = db.query(Subtask).filter_by(task_id=t1.id).all()
    assert [s.title for s in subs] == ["子任务一", "子任务二", "子任务三"]

    # ai_reports 落摘要
    row = db.query(AIReport).filter_by(report_type="autopilot").one()
    assert row.period_start == date.today()
    assert "排程" in row.content


@freeze_time("2026-09-04 08:05:00")
def test_same_day_rerun_is_idempotent(db, monkeypatch):
    monkeypatch.setattr(autopilot, "build_model", lambda cfg, api_key=None: TestModel(
        custom_output_text=json.dumps(["a", "b", "c"])))
    enable(db)
    cfg = make_cfg(db)
    autopilot.run_autopilot(db, cfg, date.today())
    n_entries = db.query(TaskScheduleEntry).count()
    n_subs = db.query(Subtask).count()

    out = autopilot.run_autopilot(db, cfg, date.today())
    assert out["ran"] is False and out["reason"] == "already_ran"
    assert db.query(TaskScheduleEntry).count() == n_entries
    assert db.query(Subtask).count() == n_subs


@freeze_time("2026-09-04 08:05:00")
def test_day_cap_two_stops_full_day(db):
    now = datetime.now()
    for i in range(2):
        db.add(Task(title=f"占位{i}", due_date=now + timedelta(days=1)))
    db.commit()
    for t in db.query(Task).filter(Task.title.like("占位%")).all():
        schedule_svc.assign_task_to_day(db, t.id, now.date())   # 今天塞满 2 条
    db.add(Task(title="新任务", due_date=now + timedelta(days=3)))
    db.commit()

    enable(db)
    autopilot.run_autopilot(db, None, date.today())
    t = db.query(Task).filter_by(title="新任务").first()
    e = db.query(TaskScheduleEntry).filter_by(task_id=t.id).one()
    assert e.date == date.today() + timedelta(days=1)   # 今天满员 → 顺延到负载最轻的明天


@freeze_time("2026-09-04 08:05:00")
def test_max_assignments_limit(db):
    now = datetime.now()
    for i in range(12):   # 12 个未排期任务；截止 +6d → 7 天 × 日上限 2 容量足够 → 总量上限 10 生效
        db.add(Task(title=f"批量{i:02d}", due_date=now + timedelta(days=6)))
    db.commit()

    enable(db)
    out = autopilot.run_autopilot(db, None, date.today())
    assigned = [a for a in out["actions"] if a["kind"] == "assign"]
    assert len(assigned) == autopilot.MAX_ASSIGNMENTS == 10
    assert db.query(TaskScheduleEntry).filter_by(source="ai").count() == 10


@freeze_time("2026-09-04 08:05:00")
def test_breakdown_model_failure_skips_and_continues(db, monkeypatch):
    now = datetime.now()
    db.add(Task(title="任务甲", due_date=now + timedelta(days=1), priority="high"))
    db.add(Task(title="任务乙", due_date=now + timedelta(days=2), priority="high"))
    db.commit()

    def fake_build(cfg, api_key=None):
        def respond(messages, info):
            text = "".join(p.content for p in messages[-1].parts
                           if isinstance(p, UserPromptPart))
            if "任务甲" in text:
                raise RuntimeError("模拟模型失败")
            payload = json.dumps(["乙-1", "乙-2", "乙-3"], ensure_ascii=False)
            return ModelResponse(parts=[TextPart(content=payload)])
        return FunctionModel(function=respond)

    monkeypatch.setattr(autopilot, "build_model", fake_build)
    enable(db)
    out = autopilot.run_autopilot(db, make_cfg(db), date.today())

    assert out["ran"] is True   # 单任务拆解失败不中断整体
    jia = db.query(Task).filter_by(title="任务甲").first()
    yi = db.query(Task).filter_by(title="任务乙").first()
    assert db.query(Subtask).filter_by(task_id=jia.id).count() == 0
    assert db.query(Subtask).filter_by(task_id=yi.id).count() == 3
    breakdowns = [a for a in out["actions"] if a["kind"] == "breakdown"]
    assert [b["task_id"] for b in breakdowns] == [yi.id]


@freeze_time("2026-09-04 08:05:00")
def test_breakdown_needs_no_model_when_config_none(db):
    now = datetime.now()
    db.add(Task(title="高优无模型", due_date=now + timedelta(days=1), priority="high"))
    db.commit()
    enable(db)
    out = autopilot.run_autopilot(db, None, date.today())
    assert out["ran"] is True
    assert all(a["kind"] == "assign" for a in out["actions"])   # 无模型只排程不拆解
    row = db.query(AIReport).filter_by(report_type="autopilot").one()
    assert row.model_name == "rule"


def test_project_tasks_are_not_scheduled_or_broken_down_by_generic_autopilot(db, monkeypatch):
    from tests.domain.test_followups import started
    from tests.domain.test_research import NOW
    _, tasks = started(db)
    db.query(TaskScheduleEntry).delete()
    for member in tasks:
        task = db.get(Task, member.task_id)
        task.priority = 'high'
        task.due_date = NOW + timedelta(days=1)
    db.commit()
    def unexpected(*args):
        raise AssertionError('Project tasks must use project planning')
    monkeypatch.setattr(autopilot, '_request_subtasks', unexpected)
    enable(db)
    result = autopilot.run_autopilot(db, make_cfg(db), NOW.date())
    assert result['actions'] == [] and db.query(TaskScheduleEntry).count() == 0
