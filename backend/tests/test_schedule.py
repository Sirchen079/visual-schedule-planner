from datetime import date, timedelta


def _task(client, title, **payload):
    response = client.post("/tasks", json={"title": title, **payload})
    assert response.status_code == 201
    return response.json()


def _bucket_task_ids(day_schedule, bucket_name):
    return [item["task"]["id"] for item in day_schedule["buckets"][bucket_name]]


def test_day_schedule_groups_due_planned_span_and_unscheduled_tasks(client):
    today = date(2026, 6, 29)

    due = _task(client, "Due today", due_date=str(today), priority="\u9ad8")
    planned = _task(client, "Planned manually")
    span = _task(
        client,
        "Multi-day span",
        start_date=str(today - timedelta(days=1)),
        end_date=str(today + timedelta(days=2)),
    )
    unscheduled = _task(client, "Unscheduled")

    entry_response = client.post(
        "/schedule/entries",
        json={
            "task_id": planned["id"],
            "date": str(today),
            "source": "manual",
            "note": "Design block",
        },
    )
    assert entry_response.status_code == 201

    response = client.get(f"/schedule/day?date={today}")

    assert response.status_code == 200
    body = response.json()
    assert _bucket_task_ids(body, "must_do") == [due["id"]]
    assert _bucket_task_ids(body, "planned") == [planned["id"]]
    assert _bucket_task_ids(body, "in_progress_today") == [span["id"]]
    assert _bucket_task_ids(body, "unscheduled") == [unscheduled["id"]]
    assert body["summary"]["total"] == 4


def test_month_schedule_counts_day_signals(client):
    target = date(2026, 6, 29)

    _task(client, "Due on month day", due_date=str(target))
    planned = _task(client, "Planned on month day")
    _task(
        client,
        "Spans into next month",
        start_date=str(target),
        end_date=str(date(2026, 7, 2)),
    )
    entry_response = client.post(
        "/schedule/entries",
        json={"task_id": planned["id"], "date": str(target), "source": "manual"},
    )
    assert entry_response.status_code == 201

    response = client.get("/schedule/month?year=2026&month=6")

    assert response.status_code == 200
    body = response.json()
    day = next(day for day in body["days"] if day["date"] == str(target))
    assert day["due_count"] == 1
    assert day["planned_count"] == 1
    assert day["in_progress_count"] == 1
    assert day["total_count"] >= 3


def test_schedule_entry_requires_existing_active_task(client):
    response = client.post(
        "/schedule/entries",
        json={"task_id": 99999, "date": "2026-06-29", "source": "manual"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] != "Not Found"


def test_schedule_entry_update_and_delete_refresh_day_schedule(client):
    day_one = date(2026, 6, 29)
    day_two = date(2026, 6, 30)
    task = _task(client, "Move around")

    create_response = client.post(
        "/schedule/entries",
        json={"task_id": task["id"], "date": str(day_one), "source": "manual"},
    )
    assert create_response.status_code == 201
    entry = create_response.json()

    update_response = client.put(
        f"/schedule/entries/{entry['id']}",
        json={"date": str(day_two), "note": "Moved"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["date"] == str(day_two)
    assert update_response.json()["note"] == "Moved"

    day_one_response = client.get(f"/schedule/day?date={day_one}")
    assert day_one_response.status_code == 200
    assert task["id"] not in _bucket_task_ids(day_one_response.json(), "planned")

    delete_response = client.delete(f"/schedule/entries/{entry['id']}")
    assert delete_response.status_code == 204

    day_two_response = client.get(f"/schedule/day?date={day_two}")
    assert day_two_response.status_code == 200
    assert task["id"] not in _bucket_task_ids(day_two_response.json(), "planned")


def test_schedule_entry_update_after_soft_deleted_task_returns_404(client):
    task = _task(client, "Deleted scheduled task")
    create_response = client.post(
        "/schedule/entries",
        json={"task_id": task["id"], "date": "2026-06-29", "source": "manual"},
    )
    assert create_response.status_code == 201
    entry = create_response.json()

    assert client.delete(f"/tasks/{task['id']}").status_code == 204

    update_response = client.put(
        f"/schedule/entries/{entry['id']}",
        json={"note": "Should not update"},
    )

    assert update_response.status_code == 404


def test_schedule_entry_update_after_completed_task_returns_404(client):
    task = _task(client, "Completed scheduled task")
    create_response = client.post(
        "/schedule/entries",
        json={"task_id": task["id"], "date": "2026-06-29", "source": "manual"},
    )
    assert create_response.status_code == 201
    entry = create_response.json()

    complete_response = client.put(
        f"/tasks/{task['id']}", json={"status": "\u5b8c\u6210"}
    )
    assert complete_response.status_code == 200

    update_response = client.put(
        f"/schedule/entries/{entry['id']}",
        json={"note": "Should not update"},
    )

    assert update_response.status_code == 404


def test_schedule_entry_rejects_invalid_source_on_create(client):
    task = _task(client, "Invalid source create")

    response = client.post(
        "/schedule/entries",
        json={"task_id": task["id"], "date": "2026-06-29", "source": "external"},
    )

    assert response.status_code == 422


def test_schedule_entry_rejects_invalid_source_on_update(client):
    task = _task(client, "Invalid source update")
    create_response = client.post(
        "/schedule/entries",
        json={"task_id": task["id"], "date": "2026-06-29", "source": "manual"},
    )
    assert create_response.status_code == 201
    entry = create_response.json()

    response = client.put(
        f"/schedule/entries/{entry['id']}",
        json={"source": "external"},
    )

    assert response.status_code == 422


def test_duplicate_schedule_entry_create_upserts_without_duplicate_planned_item(client):
    task = _task(client, "Duplicate planned task")
    first_response = client.post(
        "/schedule/entries",
        json={
            "task_id": task["id"],
            "date": "2026-06-29",
            "source": "manual",
            "note": "Initial",
        },
    )
    assert first_response.status_code == 201
    first_entry = first_response.json()

    second_response = client.post(
        "/schedule/entries",
        json={
            "task_id": task["id"],
            "date": "2026-06-29",
            "source": "ai",
            "note": "Refined",
        },
    )
    assert second_response.status_code == 201
    second_entry = second_response.json()

    assert second_entry["id"] == first_entry["id"]
    assert second_entry["source"] == "ai"
    assert second_entry["note"] == "Refined"

    day_response = client.get("/schedule/day?date=2026-06-29")
    assert day_response.status_code == 200
    assert _bucket_task_ids(day_response.json(), "planned").count(task["id"]) == 1


def test_schedule_entry_update_to_duplicate_date_merges_into_target_entry(client):
    task = _task(client, "Merge planned task")
    entry_a_response = client.post(
        "/schedule/entries",
        json={
            "task_id": task["id"],
            "date": "2026-06-29",
            "source": "manual",
            "note": "Original A",
        },
    )
    assert entry_a_response.status_code == 201
    entry_a = entry_a_response.json()

    entry_b_response = client.post(
        "/schedule/entries",
        json={
            "task_id": task["id"],
            "date": "2026-06-30",
            "source": "ai",
            "note": "Original B",
        },
    )
    assert entry_b_response.status_code == 201
    entry_b = entry_b_response.json()

    merge_response = client.put(
        f"/schedule/entries/{entry_b['id']}",
        json={
            "date": "2026-06-29",
            "source": "system",
            "note": "Merged into A",
        },
    )

    assert merge_response.status_code == 200
    merged_entry = merge_response.json()
    assert merged_entry["id"] == entry_a["id"]
    assert merged_entry["id"] != entry_b["id"]
    assert merged_entry["date"] == "2026-06-29"
    assert merged_entry["source"] == "system"
    assert merged_entry["note"] == "Merged into A"

    missing_b_response = client.put(
        f"/schedule/entries/{entry_b['id']}",
        json={"note": "Entry B should be gone"},
    )
    assert missing_b_response.status_code == 404

    day_response = client.get("/schedule/day?date=2026-06-29")
    assert day_response.status_code == 200
    assert _bucket_task_ids(day_response.json(), "planned").count(task["id"]) == 1


def test_purge_task_removes_schedule_entry_from_schedules_and_updates(
    client, db_session
):
    from app.models import TaskScheduleEntry

    task = _task(client, "Purge scheduled task")
    create_response = client.post(
        "/schedule/entries",
        json={"task_id": task["id"], "date": "2026-06-29", "source": "manual"},
    )
    assert create_response.status_code == 201
    entry = create_response.json()

    assert client.delete(f"/tasks/{task['id']}").status_code == 204
    assert client.delete(f"/tasks/{task['id']}/purge").status_code == 204

    assert db_session.get(TaskScheduleEntry, entry["id"]) is None

    day_response = client.get("/schedule/day?date=2026-06-29")
    assert day_response.status_code == 200
    assert task["id"] not in _bucket_task_ids(day_response.json(), "planned")

    month_response = client.get("/schedule/month?year=2026&month=6")
    assert month_response.status_code == 200
    day = next(
        day for day in month_response.json()["days"] if day["date"] == "2026-06-29"
    )
    assert day["planned_count"] == 0

    update_response = client.put(
        f"/schedule/entries/{entry['id']}",
        json={"note": "Cannot update purged task entry"},
    )
    assert update_response.status_code == 404


def test_delete_missing_schedule_entry_returns_404(client):
    response = client.delete("/schedule/entries/99999")

    assert response.status_code == 404


def test_month_schedule_rejects_invalid_year_and_month(client):
    invalid_year_response = client.get("/schedule/month?year=0&month=6")
    invalid_month_response = client.get("/schedule/month?year=2026&month=13")

    assert invalid_year_response.status_code == 400
    assert invalid_month_response.status_code == 400


def test_month_schedule_overdue_does_not_spread_to_future(client):
    today = date.today()
    yesterday = today - timedelta(days=1)
    _task(client, "Overdue task", due_date=str(yesterday))

    response = client.get(f"/schedule/month?year={today.year}&month={today.month}")

    assert response.status_code == 200
    days = response.json()["days"]
    today_day = next(d for d in days if d["date"] == str(today))
    assert today_day["overdue_count"] == 1  # 逾期任务压在今天
    future_days = [d for d in days if d["date"] > str(today)]
    assert all(d["overdue_count"] == 0 for d in future_days)  # 不蔓延到未来


def test_schedule_entry_update_rejects_invalid_time_format(client):
    task = _task(client, "Time check")
    entry = client.post(
        "/schedule/entries",
        json={"task_id": task["id"], "date": "2026-06-29", "source": "manual"},
    ).json()

    resp = client.put(f"/schedule/entries/{entry['id']}", json={"start_time": "25:99"})

    assert resp.status_code == 422
