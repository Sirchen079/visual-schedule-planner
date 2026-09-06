"""Compile content changes and stable task order into bounded calendar operations."""
from copy import deepcopy
from datetime import datetime


def future_entries(state: dict, task_id: int, now: datetime) -> list[dict]:
    return [e for e in state['entries'] if e['task_id'] == task_id and
            (e['date'] > str(now.date()) or e['date'] == str(now.date()) and
             (not e['end'] or datetime.fromisoformat(e['date']+'T'+e['end']) > now))]


def started(entry: dict, now: datetime) -> bool:
    return datetime.fromisoformat(entry['date']+'T'+(entry['start'] or '00:00')) <= now


def targets(state: dict, now: datetime) -> list[dict]:
    from zhishi.domain.research.planning import slot_record
    result = []
    for member in state['members']:
        future = future_entries(state, member['task_id'], now)
        ongoing = any(started(e, now) for e in future) or member.get('focus_running', False)
        can_move = member['status'] == 'todo' and not ongoing
        can_insert = can_move and not (member.get('progress') or member.get('subtasks_done') or member.get('focus_minutes'))
        can_replace = can_insert and not member.get('subtask_count')
        reason = ('' if can_replace else '已有子任务，可在前面补充内容' if can_insert
                  else '已有学习记录、已开始或状态不允许修改内容')
        result.append({'task_link_id':member['link_id'], 'title':member['title'], 'can_move':can_move,
            'can_insert_before':can_insert, 'can_replace':can_replace,
            'manual_schedule':any(slot_record(e) not in member['managed_slots'] for e in future), 'reason':reason})
    return result


def compile_units(state: dict, now: datetime, *, target_link_id: int | None = None,
                  mode: str | None = None, new_units: list[dict] | None = None,
                  movable_task_link_ids: list[int] | None = None) -> tuple[list, list, list, list, list]:
    from zhishi.domain.research.planning import slot_record
    units, preserved, movable, new_indices, moved_manual = [], [], [], [], []
    gate, blocker = None, None
    since_anchor = []
    allowed = set(movable_task_link_ids or [])
    known = {m['link_id'] for m in state['members']}
    if not allowed <= known:
        raise ValueError('允许移动的任务记录不属于本项目')
    target = next((m for m in state['members'] if m['link_id'] == target_link_id), None)
    if mode and (not target or target['status'] != 'todo'):
        raise ValueError('插入或替换的目标必须是本项目尚未开始的任务')
    if target and (target.get('progress') or target.get('subtasks_done') or
                   target.get('focus_minutes') or target.get('focus_running')):
        raise ValueError('目标已有学习进度或专注记录，请保留当前学习内容，选择尚未开始的后续任务')
    if mode == 'replace' and target.get('subtask_count'):
        raise ValueError('目标已有子任务，请先核对子任务，或改为插入补充内容，避免覆盖已有拆解')

    def add(items: list[dict], is_new: bool = False):
        for original in items:
            unit = deepcopy(original)
            unit.update(not_before=gate, blocked_by=blocker)
            since_anchor.append(len(units))
            if is_new:
                new_indices.append(len(units))
            units.append(unit)

    def anchor(entries: list[dict]):
        nonlocal gate
        upper = min(e['date']+'T'+(e['start'] or '00:00') for e in entries)
        for index in since_anchor:
            units[index]['not_after'] = upper
        since_anchor.clear()
        gate = max([gate or '', *[e['date']+'T'+(e['end'] or '23:59') for e in entries]])

    for member in state['members']:
        tid, lid = member['task_id'], member['link_id']
        future = future_entries(state, tid, now)
        ongoing = any(started(e, now) for e in future) or member.get('focus_running', False)
        if lid in allowed and (member['status'] != 'todo' or ongoing):
            raise ValueError('不能移动已完成、进行中或已经开始的安排')
        if lid == target_link_id and ongoing:
            raise ValueError('目标任务的安排已经开始，请结束本次学习后再调整内容')
        if member['status'] != 'todo':
            preserved.append({'task_id':tid, 'title':member['title'], 'reason':member['status']})
            if member['status'] == 'doing':
                if future:
                    anchor(future)
                else:
                    blocker = tid
            continue
        owned = [e for e in future if slot_record(e) in member['managed_slots'] and not started(e, now)]
        manual = [e for e in future if e not in owned]
        protected = ongoing or bool(manual) and lid not in allowed
        if lid == target_link_id and mode == 'replace' and protected:
            raise ValueError('目标有保留的手工安排；若要重新安排，请明确允许移动该任务的手工时间')
        if lid == target_link_id and mode == 'insert_before':
            add(new_units or [], True)
        if protected:
            preserved.append({'task_id':tid, 'title':member['title'], 'reason':'保留手工或已开始的安排'})
            if future:
                anchor(future)
            else:
                blocker = tid
            continue
        moved = future if lid in allowed else owned
        movable.extend(e['id'] for e in moved)
        if manual and lid in allowed:
            moved_manual.append({'task_link_id':lid, 'task_id':tid, 'title':member['title'],
                                 'slots':[slot_record(e) for e in manual]})
        if lid == target_link_id and mode == 'replace':
            replacements = deepcopy(new_units or [])
            replacements[0].update(existing_task_id=tid, replace_content=True)
            add(replacements, True)
        else:
            add([{'title':member['title'], 'outcome':member['notes'], 'minutes':member['minutes'] or 45,
                  'source_ids':member['source_ids'], 'existing_task_id':tid}])
    return units, preserved, movable, new_indices, moved_manual


def prepare(db, project_id, payload, now):
    from zhishi.domain.research import planning, service
    project = service.get_project(db, project_id, active=True)
    if project.version != payload.version:
        raise service.ResearchConflict('项目或反馈已变化，请读取最新状态后调整', project_id)
    state = planning.calendar_state(db, project_id, service.spec_of(project), now)
    try:
        units, preserved, movable, indices, moved_manual = compile_units(state, now,
            target_link_id=payload.target_link_id, mode=payload.mode,
            new_units=planning.split_steps(service.spec_of(project), payload.steps),
            movable_task_link_ids=payload.movable_task_link_ids)
    except ValueError as exc:
        raise service.ResearchConflict(str(exc), project_id) from exc
    before = next(t for t in service.task_rows(db, project_id) if t['id'] == payload.target_link_id)
    context = {'mode':payload.mode, 'target_link_id':payload.target_link_id, 'before_task':before,
               'moved_manual':moved_manual, 'new_unit_indices':indices, 'warnings':[]}
    return service._save_preview(db, project, units, payload.rationale, 'revision', state, now,
        preserved=preserved, movable=movable, feedback_ids=payload.feedback_ids, edit_context=context)
