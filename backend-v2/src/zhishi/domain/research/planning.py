"""The model supplies ordered learning content; this module assigns actual available time."""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from zhishi.domain import settingsvc
from zhishi.domain.models import ResearchTask, Task, TaskScheduleEntry, TimeLog
from zhishi.domain.research.order import ordered_links
from zhishi.domain.research.schemas import ProjectSpec, StepDraft
from zhishi.domain.schedule.conflicts import free_intervals
from zhishi.domain.schedule.service import expand_events_between


def encoded(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def fingerprint(value) -> str:
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def minute(value: str) -> int:
    h, m = value.split(':')
    return int(h) * 60 + int(m)


def hhmm(value: int) -> str:
    return f'{value // 60:02d}:{value % 60:02d}'


def end_date(spec: ProjectSpec):
    return spec.end_date or spec.start_date + timedelta(days=13)


def calendar_state(db: Session, project_id: int, spec: ProjectSpec, now: datetime) -> dict:
    """Persist enough evidence to reject a plan if its calendar or tracked tasks changed."""
    end = end_date(spec)
    entries = []
    project_ids = select(ResearchTask.task_id).where(ResearchTask.project_id == project_id)
    for entry, task in db.execute(select(TaskScheduleEntry, Task).join(Task).where(
            or_(TaskScheduleEntry.date.between(spec.start_date, end), Task.id.in_(project_ids)),
            Task.deleted_at.is_(None)
    ).order_by(TaskScheduleEntry.id)):
        entries.append({'id': entry.id, 'task_id': task.id, 'date': entry.date.isoformat(),
            'start': entry.start_time, 'end': entry.end_time, 'source': entry.source, 'note': entry.note,
            'minutes': task.estimated_minutes or 0, 'status': task.status})
    members = []
    focus = defaultdict(list)
    for log in db.scalars(select(TimeLog).where(TimeLog.task_id.in_(project_ids), TimeLog.kind == 'focus')):
        focus[log.task_id].append(log)
    for link in ordered_links(db, project_id):
        task = db.get(Task, link.task_id, populate_existing=True) if link.task_id else None
        members.append({'link_id': link.id, 'task_id': link.task_id,
            'title': task.title if task else link.title, 'notes': task.notes if task else '',
            'minutes': task.estimated_minutes if task else None,
            'status': 'missing' if task is None else 'deleted' if task.deleted_at else task.status,
            'due_date': str(task.due_date) if task and task.due_date else None,
            'progress':task.progress if task else 0,
            'subtask_count':len(task.subtasks) if task else 0,
            'subtasks_done':sum(s.done for s in task.subtasks) if task else 0,
            'focus_minutes':sum(log.minutes for log in focus[link.task_id]),
            'focus_running':any(log.ended_at is None for log in focus[link.task_id]),
            'source_ids': json.loads(link.source_ids_json),
            'managed_slots': json.loads(link.managed_slots_json)})
    return {'events': expand_events_between(db, spec.start_date, end), 'entries': entries,
        'members': members, 'working': settingsvc.working_hours(db),
        'capacity': max(0, settingsvc.daily_capacity_minutes(db)), 'today': now.date().isoformat()}


def split_steps(spec: ProjectSpec, steps: list[StepDraft]) -> list[dict]:
    units = []
    length = min(spec.session_minutes, spec.daily_minutes)
    for step in steps:
        count = (step.minutes + length - 1) // length
        base, remainder = divmod(step.minutes, count)
        for part in range(count):
            units.append({'title': step.title if count == 1 else f'{step.title} · {part + 1}/{count}',
                'outcome': step.outcome, 'minutes': base + (1 if part < remainder else 0),
                'source_ids': list(dict.fromkeys(step.source_ids + [ref.source_id for ref in step.source_refs])),
                'source_refs':[ref.model_dump() for ref in step.source_refs], 'existing_task_id': None})
    if len(units) > 200:
        raise ValueError('本次超过200个学习时段，请缩小到一个阶段后再规划')
    return units


def slot_record(entry: dict) -> dict:
    return {key: entry[key] for key in ('id', 'date', 'start', 'end', 'source', 'note')}


def replan_units(state: dict, now: datetime) -> tuple[list, list, list]:
    """Preserve fixed commitments and constrain earlier work to finish before them."""
    from zhishi.domain.research.curriculum import compile_units
    units, preserved, movable, _, _ = compile_units(state, now)
    return units, preserved, movable


def allocate(spec: ProjectSpec, units: list[dict], state: dict, now: datetime,
             movable: list[int] | None = None) -> tuple[list, list]:
    """Ordered first-fit within selected days, project budget, global task budget and free time."""
    skip = set(movable or [])
    events, entries = defaultdict(list), defaultdict(list)
    for event in state['events']:
        events[event['date']].append(event)
    for entry in state['entries']:
        if entry['id'] not in skip:
            entries[entry['date']].append(entry)
    working = (spec.window_start, spec.window_end) if spec.window_start else state['working']
    project_task_ids = {m['task_id'] for m in state['members'] if m['task_id']}
    lo, hi = minute(working[0]), minute(working[1])
    days = []
    day = max(spec.start_date, now.date())
    while day <= end_date(spec):
        key = day.isoformat()
        # An all-day event is an explicit commitment, not an empty day.
        if day.weekday() in spec.weekdays and not any(not e['start_time'] or not e['end_time'] for e in events[key]):
            busy = [(minute(e['start_time']), minute(e['end_time'])) for e in events[key]]
            busy += [(minute(e['start']), minute(e['end'])) for e in entries[key] if e['start'] and e['end']]
            lower = max(lo, ((now.hour * 60 + now.minute + (1 if now.second or now.microsecond else 0) + 4) // 5) * 5) if day == now.date() else lo
            slots = free_intervals(lower, hi, busy)
            used = sum(max(e['minutes'], minute(e['end']) - minute(e['start']) if e['start'] and e['end'] else 0) for e in entries[key])
            project_used = sum(max(e['minutes'], minute(e['end']) - minute(e['start']) if e['start'] and e['end'] else 0)
                               for e in entries[key] if e['task_id'] in project_task_ids)
            days.append({'date': key, 'slots': slots, 'remaining': min(max(0, spec.daily_minutes - project_used), max(0, state['capacity'] - used))})
        day += timedelta(days=1)
    assignments, unassigned = [], []
    # A later prerequisite-dependent unit must not be placed before an earlier unit.
    after = (spec.start_date.isoformat(), '00:00')
    blocked = False
    for index, unit in enumerate(units):
        placed = False
        if unit.get('not_before'):
            gate = unit['not_before'].split('T')
            after = max(after, (gate[0], gate[1]))
        if unit.get('blocked_by'):
            blocked = True
        if not blocked:
            for day in days:
                if day['date'] < after[0] or day['remaining'] < unit['minutes']:
                    continue
                for slot_index, (start, end) in enumerate(day['slots']):
                    if day['date'] == after[0]:
                        start = max(start, minute(after[1]))
                    if end - start < unit['minutes']:
                        continue
                    stop = start + unit['minutes']
                    if unit.get('not_after') and day['date']+'T'+hhmm(stop) > unit['not_after']:
                        continue
                    assignments.append({'unit_index': index, 'date': day['date'], 'start': hhmm(start), 'end': hhmm(stop)})
                    day['slots'][slot_index] = (stop, end)
                    day['remaining'] -= unit['minutes']
                    after = (day['date'], hhmm(stop))
                    placed = True
                    break
                if placed:
                    break
        if not placed:
            reason = ('前置任务没有可确定的结束时段，安排或完成后可重新排程' if unit.get('blocked_by')
                      else '前置学习时段尚未排入，保留顺序' if blocked
                      else '保留的后续安排开始前没有满足时长和容量的空闲时间' if unit.get('not_after')
                      else '规划窗口内无满足连续时长、每日投入及已有安排约束的时段')
            unassigned.append({'unit_index': index, 'reason': reason})
            blocked = True
    return assignments, unassigned
