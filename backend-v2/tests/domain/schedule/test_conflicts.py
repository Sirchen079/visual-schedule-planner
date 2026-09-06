from datetime import date
from zhishi.domain.schedule import conflicts as cf
from zhishi.domain.schedule import service as ss


def _mk(db, day, st, et, title="课"):
    ss.create_event(db, title=title, date=day, start_time=st, end_time=et)


def test_overlap_detected(db):
    d = date(2026, 9, 7)
    _mk(db, d, "08:00", "09:40")
    _mk(db, d, "09:30", "10:10", title="冲突课")
    cs = cf.check_conflicts(db, d, d)
    assert len(cs) == 1
    # 冲突条目形如 {"date":…, "items":[a,b]}，无 title 顶层键；.get 使 or 兜底可评估
    assert {c.get("title") for c in cs} == {"课", "冲突课"} or len(cs[0]["items"]) == 2


def test_adjacent_not_conflict(db):
    d = date(2026, 9, 7)
    _mk(db, d, "08:00", "09:40")
    _mk(db, d, "09:40", "11:20", title="连堂")
    assert cf.check_conflicts(db, d, d) == []


def test_find_free_slots(db):
    d = date(2026, 9, 7)
    _mk(db, d, "09:00", "10:30")
    _mk(db, d, "13:00", "14:00", title="午后")
    slots = cf.find_free_slots(db, d, working=("08:00", "18:00"), min_minutes=60)
    # 08:00-09:00(60) 排除（不足60? 恰60 应保留）、10:30-13:00(150)、14:00-18:00(240)
    spans = [(s["start"], s["end"], s["minutes"]) for s in slots]
    assert ("08:00", "09:00", 60) in spans
    assert ("10:30", "13:00", 150) in spans
    assert ("14:00", "18:00", 240) in spans


def test_outside_hours_do_not_erase_or_extend_free_time(db):
    d = date(2026, 9, 7)
    _mk(db, d, '06:00', '08:00')
    _mk(db, d, '20:00', '21:00')
    assert cf.find_free_slots(db, d, working=('09:00', '18:00')) == [
        {'start':'09:00', 'end':'18:00', 'minutes':540}]
    _mk(db, d, '17:00', '19:00')
    assert cf.find_free_slots(db, d, working=('09:00', '18:00')) == [
        {'start':'09:00', 'end':'17:00', 'minutes':480}]
