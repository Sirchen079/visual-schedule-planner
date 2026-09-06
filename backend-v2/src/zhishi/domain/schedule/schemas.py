# src/zhishi/domain/schedule/schemas.py
# 注意：字段名 date 与类型 datetime.date 同名——类体内 `date: date | None = None`
# 求值注解时默认值已绑入类局部命名空间，LOAD_NAME 会命中 None 而非类型。
# 故以 Date 别名引入类型，字段名保持 date（API 契约）。
from datetime import date as Date
from typing import Annotated
from pydantic import BaseModel, Field, model_validator

ReminderOffsets = Annotated[list[Annotated[int, Field(ge=0, le=10080, strict=True)]], Field(max_length=8)]
ReminderTime = Annotated[str, Field(pattern=r'^([01]\d|2[0-3]):[0-5]\d$')]


def reminder_recurrence_supported(value: str | None) -> bool:
    """Reminder scans accept at most daily occurrences, with no intra-day expansion."""
    if not value:
        return True
    import re
    raw = value.upper().removeprefix('RRULE:')
    pairs = raw.split(';')
    fields = dict(pair.split('=', 1) for pair in pairs if '=' in pair)
    return ('\n' not in raw and '\r' not in raw and len(fields) == len(pairs)
            and fields.get('FREQ') in ('DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY')
            and all(re.fullmatch(r'[1-9]\d*', fields[key]) for key in ('INTERVAL', 'COUNT') if key in fields)
            and not any(key in fields for key in ('BYSECOND', 'BYMINUTE', 'BYHOUR')))


class ScheduleEntryCreate(BaseModel):
    task_id: int
    date: Date
    start_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    source: str = "manual"   # manual/ai/ical
    note: str = ""


class ScheduleEntryUpdate(BaseModel):
    date: Date | None = None
    start_time: str | None = None
    end_time: str | None = None
    note: str | None = None


class EventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    date: Date
    start_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    location: str = ""
    category: str = "general"
    recur_rrule: str | None = None
    repeat_note: str | None = None   # 人类可读周次规则（课表导入写入，re #020 事项2）
    notes: str = ""
    remind_offsets: ReminderOffsets = Field(default_factory=list)
    reminder_time: ReminderTime | None = None

    @model_validator(mode='after')
    def _reminders(self):
        self.remind_offsets = sorted(set(self.remind_offsets))
        if self.remind_offsets:
            if not self.start_time and not self.reminder_time:
                raise ValueError('全天日程启用提醒时，请指定当天的提醒时间')
            if not reminder_recurrence_supported(self.recur_rrule):
                raise ValueError('日程提醒仅支持按天、周、月或年重复，不支持日内多次或复合规则')
            if self.recur_rrule:
                from datetime import datetime, time
                from dateutil.rrule import rrulestr
                # Validate syntax and datetime compatibility without enumerating an unbounded series.
                rrulestr(self.recur_rrule, dtstart=datetime.combine(self.date, time()))
        return self


class EventUpdate(BaseModel):
    title: str | None = None
    date: Date | None = None
    start_time: str | None = None
    end_time: str | None = None
    location: str | None = None
    category: str | None = None
    recur_rrule: str | None = None
    notes: str | None = None
    remind_offsets: ReminderOffsets | None = None
    reminder_time: ReminderTime | None = None
