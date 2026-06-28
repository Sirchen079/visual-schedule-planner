from __future__ import annotations

from app.models import AIConfig
from app.services import ai_action_service, ai_prompt_service, ai_tool_service


def _task(db_session, title: str):
    result = ai_tool_service.execute_tool(db_session, "create_task", {"title": title})
    assert result["ok"] is True
    return result["task"]


def _entry(client, task_id: int, target_date: str, **payload):
    response = client.post(
        "/schedule/entries",
        json={"task_id": task_id, "date": target_date, **payload},
    )
    assert response.status_code == 201
    return response.json()


def _planned_ids(schedule: dict) -> list[int]:
    return [item["task"]["id"] for item in schedule["buckets"]["planned"]]


def test_ai_can_read_day_schedule_without_confirmation(db_session):
    _task(db_session, "Prepare calendar redesign")

    result = ai_tool_service.execute_tool(
        db_session, "list_day_schedule", {"date": "2026-06-29"}
    )

    assert result["ok"] is True
    assert result["schedule"]["date"] == "2026-06-29"
    assert "summary" in result["schedule"]
    assert "buckets" in result["schedule"]
    assert result["schedule"]["summary"]["unscheduled"] == 1


def test_ai_can_read_month_schedule_without_confirmation(db_session):
    result = ai_tool_service.execute_tool(
        db_session, "list_month_schedule", {"year": 2026, "month": 6}
    )

    assert result["ok"] is True
    assert result["schedule"]["year"] == 2026
    assert result["schedule"]["month"] == 6
    assert len(result["schedule"]["days"]) == 30


def test_ai_can_assign_single_task_to_day_without_confirmation(db_session):
    task = _task(db_session, "Sketch icon set")

    result = ai_tool_service.execute_tool(
        db_session,
        "assign_task_to_day",
        {"task_id": task["id"], "date": "2026-06-29", "note": "AI arranged focus block"},
    )

    assert result["ok"] is True
    assert result["entry"]["task_id"] == task["id"]
    assert result["entry"]["source"] == "ai"
    assert result["entry"]["note"] == "AI arranged focus block"
    assert result["day_summary"]["planned"] == 1


def test_ai_assign_single_task_rejects_invalid_task_or_date(db_session):
    missing_task = ai_tool_service.execute_tool(
        db_session,
        "assign_task_to_day",
        {"task_id": 99999, "date": "2026-06-29"},
    )
    invalid_date = ai_tool_service.execute_tool(
        db_session,
        "assign_task_to_day",
        {"task_id": 1, "date": "2026-06-99"},
    )

    assert missing_task["ok"] is False
    assert invalid_date["ok"] is False


def test_update_schedule_entry_requires_confirmation(client, db_session):
    task = _task(db_session, "Move design block")
    entry = _entry(client, task["id"], "2026-06-29", source="manual", note="Original")
    action = ai_action_service.create_pending_action(
        db_session,
        None,
        "update_schedule_entry",
        {
            "entry_id": entry["id"],
            "patch": {
                "date": "2026-06-30",
                "note": "Moved by AI",
                "source": "ai",
            },
        },
        "Move schedule entry",
    )

    first = client.post(f"/ai/actions/{action.id}/confirm")
    assert first.status_code == 200
    preview = first.json()["action"]["preview"]
    assert any("Move design block" in line for line in preview)
    assert any("2026-06-29" in line for line in preview)
    assert any("2026-06-30" in line for line in preview)

    token = first.json()["confirm_token"]
    executed = client.post(
        f"/ai/actions/{action.id}/execute", json={"confirm_token": token}
    )
    assert executed.status_code == 200

    old_day = client.get("/schedule/day?date=2026-06-29").json()
    new_day = client.get("/schedule/day?date=2026-06-30").json()
    assert task["id"] not in _planned_ids(old_day)
    assert task["id"] in _planned_ids(new_day)


def test_delete_schedule_entry_requires_confirmation(client, db_session):
    task = _task(db_session, "Delete design block")
    entry = _entry(client, task["id"], "2026-06-29", source="manual", note="Delete me")
    action = ai_action_service.create_pending_action(
        db_session,
        None,
        "delete_schedule_entry",
        {"entry_id": entry["id"]},
        "Delete schedule entry",
    )

    first = client.post(f"/ai/actions/{action.id}/confirm")
    assert first.status_code == 200
    preview = first.json()["action"]["preview"]
    assert any("Delete design block" in line for line in preview)
    assert any("2026-06-29" in line for line in preview)

    token = first.json()["confirm_token"]
    executed = client.post(
        f"/ai/actions/{action.id}/execute", json={"confirm_token": token}
    )
    assert executed.status_code == 200

    assert client.delete(f"/schedule/entries/{entry['id']}").status_code == 404
    day = client.get("/schedule/day?date=2026-06-29").json()
    assert task["id"] not in _planned_ids(day)


def test_bulk_schedule_assignment_requires_preview_and_confirms_atomically(
    client, db_session
):
    first = _task(db_session, "Morning design pass")
    second = _task(db_session, "Afternoon interaction pass")
    action = ai_action_service.create_pending_action(
        db_session,
        None,
        "bulk_assign_tasks_to_days",
        {
            "assignments": [
                {"task_id": first["id"], "date": "2026-06-29", "note": "Morning"},
                {"task_id": second["id"], "date": "2026-06-30", "note": "Afternoon"},
            ]
        },
        "Arrange the two design tasks across two days",
    )

    first_confirm = client.post(f"/ai/actions/{action.id}/confirm")
    assert first_confirm.status_code == 200
    preview = first_confirm.json()["action"]["preview"]
    assert any("Morning design pass" in line for line in preview)
    assert any("Afternoon interaction pass" in line for line in preview)

    token = first_confirm.json()["confirm_token"]
    executed = client.post(
        f"/ai/actions/{action.id}/execute", json={"confirm_token": token}
    )
    assert executed.status_code == 200

    day_one = client.get("/schedule/day?date=2026-06-29").json()
    day_two = client.get("/schedule/day?date=2026-06-30").json()
    assert first["id"] in _planned_ids(day_one)
    assert second["id"] in _planned_ids(day_two)


def test_bulk_schedule_assignment_with_invalid_task_does_not_partially_apply(
    client, db_session
):
    valid = _task(db_session, "Valid bulk task")
    action = ai_action_service.create_pending_action(
        db_session,
        None,
        "bulk_assign_tasks_to_days",
        {
            "assignments": [
                {"task_id": valid["id"], "date": "2026-06-29", "note": "Morning"},
                {"task_id": 99999, "date": "2026-06-30", "note": "Broken"},
            ]
        },
        "Arrange tasks across days",
    )

    token = client.post(f"/ai/actions/{action.id}/confirm").json()["confirm_token"]
    executed = client.post(
        f"/ai/actions/{action.id}/execute", json={"confirm_token": token}
    )

    assert executed.status_code == 409
    assert client.get("/schedule/day?date=2026-06-29").json()["summary"]["planned"] == 0


def test_auto_plan_tasks_uses_confirmation_and_writes_assignments_atomically(
    client, db_session
):
    first = _task(db_session, "Auto plan first")
    second = _task(db_session, "Auto plan second")
    action = ai_action_service.create_pending_action(
        db_session,
        None,
        "auto_plan_tasks",
        {
            "assignments": [
                {"task_id": first["id"], "date": "2026-06-29", "note": "Morning"},
                {"task_id": second["id"], "date": "2026-06-30", "note": "Afternoon"},
            ]
        },
        "Auto plan the next two tasks",
    )

    first_confirm = client.post(f"/ai/actions/{action.id}/confirm")
    assert first_confirm.status_code == 200
    preview = first_confirm.json()["action"]["preview"]
    assert any("Auto plan" in line or "自动" in line for line in preview)

    token = first_confirm.json()["confirm_token"]
    executed = client.post(
        f"/ai/actions/{action.id}/execute", json={"confirm_token": token}
    )
    assert executed.status_code == 200

    day_one = client.get("/schedule/day?date=2026-06-29").json()
    day_two = client.get("/schedule/day?date=2026-06-30").json()
    assert first["id"] in _planned_ids(day_one)
    assert second["id"] in _planned_ids(day_two)


def test_prompt_and_local_context_include_schedule_capabilities(db_session):
    config = AIConfig(
        name="default",
        assistant_name="知时助手",
        persona="",
        provider="openai_chat",
        model="gpt-4.1-mini",
        api_key="test-key",
        enabled=True,
    )

    prompt = ai_prompt_service.build_system_prompt(db_session, config)
    context = ai_prompt_service.build_local_context(db_session)

    assert "list_day_schedule" in prompt
    assert "assign_task_to_day" in prompt
    assert "update_schedule_entry" in prompt
    assert "delete_schedule_entry" in prompt
    assert "schedule" in context or "日程" in context
