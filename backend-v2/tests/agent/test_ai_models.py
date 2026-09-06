import sqlalchemy as sa
from zhishi.infra.database import make_engine, create_all


def test_ai_tables_created(tmp_path):
    engine = make_engine(tmp_path / "t.db")
    create_all(engine)
    names = {r[0] for r in engine.connect().execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table'"))}
    assert {"ai_configs", "ai_conversations", "ai_messages", "ai_runs",
            "ai_pending_actions", "ai_tool_grants", "ai_skills", "ai_usage_logs"} <= names


def test_ai_messages_dual_storage_columns(tmp_path):
    engine = make_engine(tmp_path / "t.db")
    create_all(engine)
    cols = {r[1] for r in engine.connect().execute(sa.text("PRAGMA table_info(ai_messages)"))}
    assert {"id", "conversation_id", "role", "display_json", "history_json", "created_at"} <= cols
