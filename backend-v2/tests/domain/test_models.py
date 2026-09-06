# tests/domain/test_models.py
import sqlalchemy as sa
from zhishi.infra.database import make_engine, create_all


def test_all_tables_created(tmp_path):
    engine = make_engine(tmp_path / "t.db")
    create_all(engine)
    names = {r[0] for r in engine.connect().execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table'"))}
    expected = {
        "tasks", "subtasks", "tags", "task_tag", "task_file", "task_schedule_entries",
        "events", "goals", "key_results", "habits", "habit_logs", "journal_entries",
        "time_logs", "library_files", "notification_logs", "app_settings",
    }
    assert expected <= names


def test_task_columns(tmp_path):
    engine = make_engine(tmp_path / "t.db")
    create_all(engine)
    cols = {r[1] for r in engine.connect().execute(sa.text("PRAGMA table_info(tasks)"))}
    assert {"id", "title", "notes", "due_date", "due_time", "priority", "status",
            "progress", "remind_offsets", "recur_rule", "recur_interval",
            "recur_rrule", "estimated_minutes", "sort_order", "deleted_at",
            "completed_at", "created_at", "updated_at"} <= cols
