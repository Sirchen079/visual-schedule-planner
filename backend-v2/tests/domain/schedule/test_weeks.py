# tests/domain/schedule/test_weeks.py
from datetime import date
from zhishi.domain.schedule.weeks import week_spec_to_event


SEMESTER = date(2026, 9, 7)   # 第 1 周周一（学期锚点）


def test_continuous_range():
    """连续周 2-13，周二 → 首次 9/15（第2周周二），UNTIL 第13周周日（12/6）"""
    ev = week_spec_to_event(title="数值分析", weekday=2, week_kind="range",
                            start_week=2, end_week=13, semester_start=SEMESTER)
    # 偏差（对计划）：原断言 9/8 是第1周周二，与'连续周2-13首次出现在第2周'
    # 语义及本测试注释矛盾；第2周周二 = 9/15
    assert ev["date"] == date(2026, 9, 15)         # 第2周周二
    assert "FREQ=WEEKLY;BYDAY=TU" in ev["recur_rrule"]
    assert "UNTIL=20261206" in ev["recur_rrule"]   # 第13周周日 = 9/7+12周+6天


def test_odd_weeks_single():
    """单周 13-13（第13周一次）→ 13周周二 = 12/1（13周周一=11/30）"""
    ev = week_spec_to_event(title="海洋勘探单周", weekday=2, week_kind="odd",
                            start_week=13, end_week=13, semester_start=SEMESTER)
    assert ev["date"] == date(2026, 12, 1)
    assert "INTERVAL=2" in ev["recur_rrule"]


def test_even_weeks_anchor_at_week2():
    """双周 6-12：首偶数周=第6周 → 锚定第6周，INTERVAL=2"""
    ev = week_spec_to_event(title="双周实验", weekday=4, week_kind="even",
                            start_week=6, end_week=12, semester_start=SEMESTER)
    week6_mon = SEMESTER + __import__("datetime").timedelta(weeks=5)
    assert ev["date"] == week6_mon + __import__("datetime").timedelta(days=3)  # 周四
    assert "INTERVAL=2" in ev["recur_rrule"]


def test_odd_first_occurrence_aligns_to_odd_week():
    """单周 2-9：第2周是偶数周 → 首次落在第3周"""
    ev = week_spec_to_event(title="单周课", weekday=1, week_kind="odd",
                            start_week=2, end_week=9, semester_start=SEMESTER)
    assert ev["date"] == date(2026, 9, 21)   # 第3周周一


def test_invalid_inputs_raise():
    import pytest
    with pytest.raises(ValueError):
        week_spec_to_event(title="x", weekday=8, week_kind="range",
                           start_week=1, end_week=2, semester_start=SEMESTER)
    with pytest.raises(ValueError):
        week_spec_to_event(title="x", weekday=1, week_kind="range",
                           start_week=5, end_week=2, semester_start=SEMESTER)
