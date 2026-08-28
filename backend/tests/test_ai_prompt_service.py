from datetime import datetime, timedelta, timezone

from app.schemas import TaskCreate
from app.services import ai_prompt_service, task_service


def test_time_context_includes_local_datetime_and_relative_date_rules():
    now = datetime(2026, 6, 27, 10, 30, 5, tzinfo=timezone(timedelta(hours=8)))

    text = ai_prompt_service.build_time_context(now)

    assert "当前本地日期：2026-06-27" in text
    assert "当前本地时间：2026-06-27 10:30:05" in text
    assert "当前星期：星期六" in text
    assert "当前时区：UTC+08:00" in text
    assert "下周六" in text
    assert "明确 ISO 时间" in text


def test_local_context_includes_current_state_and_reminders(db_session):
    now = datetime.now()
    task_service.create_task(
        db_session,
        TaskCreate(
            title="已经逾期的提醒",
            due_date=now - timedelta(hours=2),
            priority="高",
            tags=["提醒"],
        ),
    )
    task_service.create_task(
        db_session,
        TaskCreate(
            title="即将到期的提醒",
            due_date=now + timedelta(hours=2),
            priority="中",
            tags=["提醒"],
        ),
    )

    text = ai_prompt_service.build_local_context(db_session)

    assert "当前时间状态" in text
    assert "当前任务统计" in text
    assert "当前提醒状态" in text
    assert "已逾期" in text
    assert "未来 7 天" in text
    assert "已经逾期的提醒" in text
    assert "即将到期的提醒" in text


def test_local_context_task_lines_include_estimated_minutes(db_session):
    task_service.create_task(
        db_session,
        TaskCreate(title="写季度总结", estimated_minutes=90, priority="高"),
    )

    text = ai_prompt_service.build_local_context(db_session)

    assert "预估:90分钟" in text  # B1：任务行带预估时长
    assert "写季度总结" in text


def test_local_context_lists_must_do_and_unscheduled(db_session):
    now = datetime.now()
    task_service.create_task(
        db_session,
        TaskCreate(title="逾期报告", due_date=now - timedelta(days=1), estimated_minutes=45),
    )

    text = ai_prompt_service.build_local_context(db_session)

    assert "今日必做（含逾期）：" in text  # B3：从只报数改为列清单
    assert "未排期任务（需要安排）：" in text
    assert "逾期报告" in text
    assert "预估:45分钟" in text
