# tests/domain/test_journal.py
from datetime import date
from zhishi.domain.journal import service as js


def test_upsert_one_per_day(db):
    js.upsert(db, date(2026, 9, 3), content="第一天", mood="good")
    js.upsert(db, date(2026, 9, 3), content="改写第一天", mood="great")
    got = js.get_entry(db, date(2026, 9, 3))
    assert got.content == "改写第一天" and got.mood == "great"
    assert len(js.list_entries(db, limit=10)) == 1
