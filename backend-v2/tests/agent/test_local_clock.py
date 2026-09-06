import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from zhishi.agent.runtime import AgentRuntime
from zhishi.infra import local_clock


@pytest.mark.parametrize(('base', 'expression', 'expected'), [
    ('2026-12-31', '明天', '2027-01-01'), ('2026-12-31', '后天', '2027-01-02'),
    ('2028-02-28', '后天', '2028-03-01'), ('2028-02-01', '月底', '2028-02-29'),
    ('2026-09-06', '下周一', '2026-09-07'), ('2026-09-07', '下星期一', '2026-09-14'),
    ('2026-09-06', '本周一', '2026-08-31'), ('2026-09-07', '周一', '2026-09-07'),
    ('2026-09-06', '下下周天', '2026-09-20'), ('2026-12-21', '下个月底', '2027-01-31'),
    ('2026-09-06', '3天后', '2026-09-09'), ('2026-09-06', '2027-01-01', '2027-01-01'),
])
def test_relative_dates_at_calendar_boundaries(base, expression, expected):
    assert local_clock.resolve_date(expression, base)['date'] == expected


@pytest.mark.parametrize('expression', ['过几天', '下周末', '2026-02-30', '9月', ''])
def test_ambiguous_dates_are_not_guessed(expression):
    with pytest.raises(ValueError):
        local_clock.resolve_date(expression)


def test_clock_reads_host_timezone_each_time(monkeypatch):
    for offset, hour, day in [(8, 0, 7), (-7, 9, 6)]:
        now = datetime(2026, 9, day, hour, 1, tzinfo=timezone(timedelta(hours=offset)))
        monkeypatch.setattr(local_clock, 'local_now', lambda value=now:value)
        state = local_clock.snapshot()
        assert state['date'] == f'2026-09-{day:02}'
        assert state['now'] == now.isoformat(timespec='seconds')
        assert state['utc_offset'] == ('+08:00' if offset == 8 else '-07:00')


async def test_live_instructions_refresh_inside_one_run_without_changing_message_date(db, monkeypatch):
    now = datetime(2026, 12, 31, 23, 59, tzinfo=timezone(timedelta(hours=8)))
    monkeypatch.setattr(local_clock, 'local_now', lambda:now)
    rounds = 0
    async def stream(messages, info):
        nonlocal now, rounds
        rounds += 1
        instructions = messages[-1].instructions
        assert '【实时本机时钟】' in instructions
        if rounds == 1:
            assert '2026-12-31T23:59:00+08:00' in instructions
            now = now + timedelta(minutes=2)
            yield {0:DeltaToolCall(name='resolve_local_date', json_args=json.dumps(
                {'expression':'明天', 'reference_date':'2026-12-31'}), tool_call_id='date')}
        else:
            assert '2027-01-01T00:01:00+08:00' in instructions
            result = next(p for p in messages[-1].parts if isinstance(p, ToolReturnPart))
            assert json.loads(result.content)['date'] == '2027-01-01'
            yield '已换算为2027年1月1日。'
    runtime = AgentRuntime(FunctionModel(stream_function=stream), db)
    events = [e async for e in runtime.run_stream(user_text='明天安排练习')]
    assert not [e for e in events if e['type'] == 'run_error'], events
    assert rounds == 2
