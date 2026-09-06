# tests/infra/test_database.py
import sqlalchemy as sa
from zhishi.infra.database import make_engine, create_all


def test_engine_wal_and_fk(tmp_path):
    engine = make_engine(tmp_path / "t.db")
    create_all(engine)  # 此时无表也应成功（Base.metadata 为空亦可）
    with engine.connect() as conn:
        journal = conn.execute(sa.text("PRAGMA journal_mode")).scalar()
        fk = conn.execute(sa.text("PRAGMA foreign_keys")).scalar()
        busy = conn.execute(sa.text("PRAGMA busy_timeout")).scalar()
    assert journal.lower() == "wal"
    assert fk == 1
    assert busy >= 3000
