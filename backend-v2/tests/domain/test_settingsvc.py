# tests/domain/test_settingsvc.py
from zhishi.domain import settingsvc as sv

def test_defaults_and_roundtrip(db):
    assert sv.feature_enabled(db, "feature_goals_enabled") is True  # 默认开
    assert sv.working_hours(db) == ("09:00", "18:00")
    sv.set_setting(db, "working_hours_start", "08:30")
    sv.set_setting(db, "feature_goals_enabled", "false")
    db.commit()
    assert sv.working_hours(db) == ("08:30", "18:00")
    assert sv.feature_enabled(db, "feature_goals_enabled") is False

def test_dirty_value_falls_back(db):
    sv.set_setting(db, "working_hours_start", "garbage")
    db.commit()
    assert sv.working_hours(db) == ("09:00", "18:00")  # 脏值回退默认
