import json
from datetime import date
from zhishi.agent.tools import macro


ENTRIES = [
    {"title": "示例课程A", "weekday": 2, "periods": [2, 3], "location": "示例教室A",
     "week_kind": "range", "start_week": 2, "end_week": 13},
    {"title": "双周实验", "weekday": 4, "periods": [5, 6], "location": "示例教室B",
     "week_kind": "even", "start_week": 6, "end_week": 12},
]


def test_import_creates_events_with_conflict_report(db):
    out = json.loads(macro.import_timetable(
        db, semester_start="2026-09-07", entries=ENTRIES))
    assert out["created"] == 2 and out["skipped"] == [] and out["conflicts"] == []
    from zhishi.domain.schedule import service as ss
    from zhishi.domain.models import Event
    events = db.query(Event).all()
    assert len(events) == 2
    ev = next(e for e in events if e.title == "示例课程A")
    assert ev.date == date(2026, 9, 15) and "UNTIL" in ev.recur_rrule and ev.location == "示例教室A"
    # 节次 2,3 → 默认时刻 08:55-10:45（2 节起止时刻）
    assert ev.start_time == "08:55" and ev.end_time == "10:45"


def test_import_writes_human_readable_repeat_note(db):
    """每门课写入人类可读周次规则（repeat_note），
    连续周=每周 / odd=单周课 / even=双周课，括号内为周次区间。"""
    json.loads(macro.import_timetable(db, semester_start="2026-09-07", entries=ENTRIES))
    from zhishi.domain.models import Event
    events = {e.title: e for e in db.query(Event).all()}
    assert events["示例课程A"].repeat_note == "每周（第2-13周）"
    assert events["双周实验"].repeat_note == "双周课（第6-12周）"

    odd = [{"title": "单周讨论", "weekday": 3, "periods": [1], "week_kind": "odd",
            "start_week": 1, "end_week": 16}]
    json.loads(macro.import_timetable(db, semester_start="2026-09-07", entries=odd))
    ev = db.query(Event).filter(Event.title == "单周讨论").one()
    assert ev.repeat_note == "单周课（第1-16周）"


def test_idempotent_rerun_skips_duplicates(db):
    macro.import_timetable(db, semester_start="2026-09-07", entries=ENTRIES)
    out = json.loads(macro.import_timetable(
        db, semester_start="2026-09-07", entries=ENTRIES))
    assert out["created"] == 0 and len(out["skipped"]) == 2   # 同名同地点跳过
    from zhishi.domain.models import Event
    assert db.query(Event).count() == 2


def test_overlap_detected_as_conflict(db):
    conflict_entries = [
        {"title": "A课", "weekday": 2, "periods": [2, 3], "location": "一教",
         "week_kind": "range", "start_week": 1, "end_week": 16},
        {"title": "B课", "weekday": 2, "periods": [3, 4], "location": "二教",
         "week_kind": "range", "start_week": 1, "end_week": 16},
    ]
    out = json.loads(macro.import_timetable(
        db, semester_start="2026-09-07", entries=conflict_entries))
    assert out["created"] == 2 and len(out["conflicts"]) == 1
    assert {c["title"] for c in out["conflicts"][0]["items"]} == {"A课", "B课"}


def test_invalid_entry_reported_not_raised(db):
    bad = [{"title": "坏条目", "weekday": 9, "periods": [1], "location": "",
            "week_kind": "range", "start_week": 1, "end_week": 2}]
    out = json.loads(macro.import_timetable(db, semester_start="2026-09-07", entries=bad))
    assert out["created"] == 0 and len(out["errors"]) == 1


# ---- Bug A 回归：判重键必须是 (title, weekday, start_time, 周次规则语义) ----

def _slot(title, weekday, location="示例教室A"):
    return {"title": title, "weekday": weekday, "periods": [2, 3], "location": location,
            "week_kind": "range", "start_week": 2, "end_week": 13}


def test_same_title_location_different_weekday_both_created(db):
    """真实课表场景：示例课程A 周二2-3节 与 周四2-3节 同教室 = 两条合法排课。
    旧判重键 (title, location) 把后者误跳过（reason=同名同地点已存在）；location 不参与判重。"""
    entries = [_slot("示例课程A", 2), _slot("示例课程A", 4)]
    out = json.loads(macro.import_timetable(db, semester_start="2026-09-07", entries=entries))
    assert out["created"] == 2, f"不同 weekday 不得判重: {out['skipped']}"
    assert out["skipped"] == []
    from zhishi.domain.models import Event
    weekdays = sorted(e.date.weekday() + 1 for e in db.query(Event).all())
    assert weekdays == [2, 4]


def test_reimport_same_batch_all_skipped_as_existing(db):
    """新判重键下幂等依旧：同批条目重复导入 → 全部 skipped「已存在」，不重复建。"""
    entries = [_slot("示例课程A", 2), _slot("示例课程A", 4)]
    macro.import_timetable(db, semester_start="2026-09-07", entries=entries)
    out = json.loads(macro.import_timetable(
        db, semester_start="2026-09-07", entries=entries))
    assert out["created"] == 0 and len(out["skipped"]) == 2
    assert all("已存在" in s["reason"] for s in out["skipped"])
    from zhishi.domain.models import Event
    assert db.query(Event).count() == 2


def test_same_slot_different_week_kind_all_created(db):
    """同名同 weekday 同节次、周次规则不同（连续/单周/双周）= 三条合法条目互不判重。"""
    entries = [
        {"title": "算法课", "weekday": 1, "periods": [1, 2], "location": "A教",
         "week_kind": "range", "start_week": 1, "end_week": 15},
        {"title": "算法课", "weekday": 1, "periods": [1, 2], "location": "A教",
         "week_kind": "odd", "start_week": 1, "end_week": 15},
        {"title": "算法课", "weekday": 1, "periods": [1, 2], "location": "A教",
         "week_kind": "even", "start_week": 1, "end_week": 15},
    ]
    out = json.loads(macro.import_timetable(db, semester_start="2026-09-07", entries=entries))
    assert out["created"] == 3 and out["skipped"] == []


def test_db_existing_event_skips_only_matching_slot(db):
    """库内查重同语义：已有 周二2-3节(range 2-13) → 同条 skipped；周四同教室不受牵连。"""
    entries = [_slot("示例课程A", 2), _slot("示例课程A", 4)]
    first = json.loads(macro.import_timetable(
        db, semester_start="2026-09-07", entries=entries[:1]))
    assert first["created"] == 1
    out = json.loads(macro.import_timetable(
        db, semester_start="2026-09-07", entries=entries))
    assert out["created"] == 1   # 只补建周四
    assert [s["title"] for s in out["skipped"]] == ["示例课程A"]
    assert all("已存在" in s["reason"] for s in out["skipped"])
    from zhishi.domain.models import Event
    assert db.query(Event).count() == 2
