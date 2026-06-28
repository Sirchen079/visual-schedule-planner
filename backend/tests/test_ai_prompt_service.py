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
