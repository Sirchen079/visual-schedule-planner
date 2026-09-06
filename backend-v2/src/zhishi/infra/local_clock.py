"""Read the host wall clock on demand; calendar storage stays in local dates/times."""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta

WEEKDAYS = ('周一', '周二', '周三', '周四', '周五', '周六', '周日')


def local_now() -> datetime:
    # Re-read OS timezone on every call, including after resume or timezone changes.
    return datetime.now().astimezone()


def snapshot(now: datetime | None = None) -> dict:
    now = now or local_now()
    if now.tzinfo is None:
        now = now.astimezone()
    today = now.date()
    monday = today - timedelta(days=today.weekday())
    return {
        'now': now.isoformat(timespec='seconds'), 'date': today.isoformat(),
        'time': now.strftime('%H:%M:%S'), 'weekday': WEEKDAYS[today.weekday()],
        'timezone': now.tzname(), 'utc_offset': now.strftime('%z')[:3]+':'+now.strftime('%z')[3:],
        'source': '本机系统时钟',
        'relative_dates': {'今天': str(today), '明天': str(today+timedelta(days=1)),
            '后天': str(today+timedelta(days=2)), '本周一': str(monday),
            '下周一': str(monday+timedelta(days=7)),
            '月底': str(today.replace(day=calendar.monthrange(today.year, today.month)[1]))},
        'timezone_note': '日期和时刻按本机本地时区保存；不自动换算成UTC。相对日期以用户该条消息的日期为基准。',
    }


def resolve_date(expression: str, reference_date: str | None = None) -> dict:
    state = snapshot()
    base = date.fromisoformat(reference_date or state['date'])
    value = re.sub(r'\s+', '', expression).replace('星期', '周').replace('礼拜', '周')
    rule = '相对用户消息日期'
    offsets = {'大前天':-3, '前天':-2, '昨天':-1, '今天':0, '今日':0,
               '明天':1, '明日':1, '后天':2, '大后天':3}
    if value in offsets:
        target = base + timedelta(days=offsets[value])
    elif match := re.fullmatch(r'(本|这|下下|下|上)?周([一二三四五六日天])', value):
        week, weekday = match.groups()
        number = '一二三四五六日天'.index(weekday)
        number = min(number, 6)
        if week is None:
            target = base + timedelta(days=(number-base.weekday()) % 7)
            rule = '无本/下周前缀时，取含今天在内最近的该星期；若用户另有含义需确认'
        else:
            target = base + timedelta(days={'本':0,'这':0,'下':7,'下下':14,'上':-7}[week]
                                      + number-base.weekday())
            rule = '每周从周一开始'
    elif value in ('月底', '本月底', '这个月底', '下月底', '下个月底'):
        month = base.replace(day=1)
        if value.startswith('下'):
            month = (month+timedelta(days=32)).replace(day=1)
        target = month.replace(day=calendar.monthrange(month.year, month.month)[1])
    elif match := re.fullmatch(r'(\d{1,3})天([后前])', value):
        target = base + timedelta(days=int(match[1]) * (1 if match[2] == '后' else -1))
    elif re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        target = date.fromisoformat(value)
        rule = '明确的日历日期'
    else:
        raise ValueError('日期表达不明确或暂不支持，请结合原话确认具体日期；不要猜测。')
    return {'expression': expression, 'reference_date': str(base), 'date': str(target),
            'weekday': WEEKDAYS[target.weekday()], 'rule': rule,
            'current_local_time': state['now'], 'utc_offset': state['utc_offset']}


def live_instructions() -> str:
    import json
    return ('【实时本机时钟】'+json.dumps(snapshot(), ensure_ascii=False)
            +'\n此块在每次模型请求前刷新。新消息的明天/后天按该消息时间换算；'
            '历史消息及已经确认的明确日期保持原义，跨午夜或审批恢复不能自动顺延。'
            '工具参数使用明确ISO日期；预定时刻已过去时说明情况并重新核对安排。')
