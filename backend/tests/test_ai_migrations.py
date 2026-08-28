from sqlalchemy import create_engine, text

from app.main import _migrate


def test_migrate_adds_missing_ai_config_columns(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE ai_configs (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(100),
                    provider VARCHAR(30) NOT NULL,
                    model VARCHAR(100) NOT NULL,
                    api_key TEXT NOT NULL
                )
                """
            )
        )
        conn.execute(text("CREATE TABLE subtasks (id INTEGER PRIMARY KEY)"))
        conn.execute(
            text(
                """
                CREATE TABLE task_schedule_entries (
                    id INTEGER PRIMARY KEY,
                    task_id INTEGER NOT NULL,
                    date DATE NOT NULL,
                    source VARCHAR(20) NOT NULL,
                    note TEXT NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE files (
                    id INTEGER PRIMARY KEY,
                    original_name VARCHAR(255) NOT NULL,
                    storage_path VARCHAR(500) NOT NULL,
                    size INTEGER NOT NULL,
                    mime_type VARCHAR(100)
                )
                """
            )
        )

    monkeypatch.setattr("app.main.engine", engine)
    _migrate()

    with engine.connect() as conn:
        ai_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(ai_configs)"))}
        subtask_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(subtasks)"))}
        entry_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(task_schedule_entries)"))}
        file_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(files)"))}

    assert {
        "assistant_name",
        "persona",
        "base_url",
        "full_url",
        "proxy_url",
        "extra_headers",
        "native_web_search_enabled",
        "native_web_search_options",
        "search_enhancement_enabled",
        "tool_calling_mode",
        "enabled",
        "active_skill_id",
        "created_at",
        "updated_at",
        # 阶段 2/3 新增列
        "price_input",
        "price_output",
        "show_reasoning",
    }.issubset(ai_cols)
    assert "completed_at" in subtask_cols
    assert "estimated_minutes" in subtask_cols
    assert {"start_time", "end_time"}.issubset(entry_cols)
    assert {"source_url", "resource_type"}.issubset(file_cols)
