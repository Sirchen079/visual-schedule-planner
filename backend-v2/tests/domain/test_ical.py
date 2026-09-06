# tests/domain/test_ical.py
from datetime import date, datetime
from icalendar import Calendar
from zhishi.domain import ical
from zhishi.domain.schedule import service as ss


def test_export_and_roundtrip(db):
    ss.create_event(db, title="高数", date=date(2026, 9, 7), start_time="08:00", end_time="09:40",
                    recur_rrule="FREQ=WEEKLY;INTERVAL=2;BYDAY=MO")
    ics_text = ical.export_ics(db)
    cal = Calendar.from_ical(ics_text)
    events = [c for c in cal.walk("VEVENT")]
    assert len(events) == 1
    assert events[0]["SUMMARY"] == "高数"

    count = ical.import_ics(db, ics_text)
    assert count == 1  # 再导入一次生成一条新日程


def test_export_mobile_calendar_fields_and_stable_identity(db):
    timed = ss.create_event(db, title="只有开始时间", date=date(2026, 9, 7), start_time="08:30",
                            notes="第一行\n中文，分号;反斜杠\\", location="会议室",
                            recur_rrule="FREQ=WEEKLY;COUNT=4")
    ss.create_event(db, title="全天", date=date(2026, 9, 8))
    first = Calendar.from_ical(ical.export_ics(db)).walk('VEVENT')
    assert first[0].decoded('DTSTART') == datetime(2026, 9, 7, 8, 30)
    assert 'DTEND' not in first[0]
    assert str(first[0]['DESCRIPTION']) == timed.notes
    assert first[0]['RRULE']['COUNT'] == [4]
    assert first[1].decoded('DTSTART') == date(2026, 9, 8)
    assert first[1].decoded('DTEND') == date(2026, 9, 9)
    assert first[1]['DTSTART'].params['VALUE'] == 'DATE'
    assert first[0]['UID'] != first[1]['UID']
    assert all(e.decoded('DTSTAMP').tzinfo is not None for e in first)
    timed.title = '修改名称'; db.commit()
    second = Calendar.from_ical(ical.export_ics(db)).walk('VEVENT')
    assert [e['UID'] for e in first] == [e['UID'] for e in second]
