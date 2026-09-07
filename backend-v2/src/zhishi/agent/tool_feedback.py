"""Short, actionable tool outcomes and bounded repeated-failure protection."""
from __future__ import annotations

import json

from pydantic import ValidationError

ATOMIC_WRITES = {'create_task', 'create_event', 'check_in_habit', 'create_subtasks',
                 'apply_day_plan', 'reschedule_overdue', 'import_timetable', 'import_web_resources',
                 'bulk_delete_tasks', 'bulk_delete_files'}


def failure_result(exc: Exception, *, tool: str, arguments: dict, readonly=False) -> dict:
    from zhishi.agent.mutations import MutationConflict
    from zhishi.agent.tools.macro import StaleDayPlan
    result = {'ok':False, 'code':'tool_failed', 'error':str(exc)[:400],
              'retryable':False, 'write_status':'not_applicable' if readonly else
              'not_applied' if tool in ATOMIC_WRITES else 'unknown',
              'next_step':'先读取目标当前状态；不要原样重复调用或换工具重复写入。'}
    if isinstance(exc, ValidationError):
        result.update(code='invalid_arguments', fields=[{'path':'.'.join(map(str, e['loc'])),
            'message':e['msg'], 'type':e['type']} for e in exc.errors(include_input=False, include_url=False)[:6]],
            next_step='只修正 fields 指出的字段，保留其他参数与原 request_key。')
    elif isinstance(exc, MutationConflict):
        result.update(code='request_key_conflict', write_status='prior_committed',
            next_step='同一键已有操作回执。先读取业务对象确认，不换键绕过去重；只有用户明确提出另一操作才使用新键。')
    elif isinstance(exc, StaleDayPlan):
        result.update(code='stale_plan', write_status='not_applied',
            next_call={'tool':'plan_day', 'args':{'day':exc.day}},
            next_step='使用 next_call 重新获取计划；本批未保存，重新确认新方案后再执行。')
    elif isinstance(exc, LookupError):
        result.update(code='not_found', next_step='目标不存在或已删除。重新定位目标，不猜 ID；不要改为创建替代对象。')
        if 'task_id' in arguments:
            result['next_call'] = {'tool':'list_tasks', 'args':{}}
        elif 'habit_id' in arguments:
            result['next_call'] = {'tool':'list_habits', 'args':{}}
    elif isinstance(exc, (ValueError, TypeError)):
        result.update(code='invalid_arguments', next_step='按 error 修正参数后再试；保留原 request_key，不增加同义重复调用。')
    elif isinstance(exc, (TimeoutError, ConnectionError)):
        result.update(code='temporarily_unavailable', retryable=readonly or tool in ATOMIC_WRITES,
            next_step='可重试一次；写入结果不明时先核对当前状态，不直接重试写入。')
    return result


def parsed_result(value):
    try:
        return json.loads(value) if isinstance(value, str) else value
    except (ValueError, TypeError):
        return None


def add_followup(tool: str, arguments: dict, value):
    result = parsed_result(value)
    if not isinstance(result, dict) or result.get('ok') is False or 'next_call' in result:
        return value
    target = None
    if tool in ('update_task', 'create_subtasks') and arguments.get('task_id'):
        target = {'tool':'get_task', 'args':{'task_id':arguments['task_id']}}
    elif tool == 'update_event' and arguments.get('event_id'):
        target = {'tool':'get_event', 'args':{'event_id':arguments['event_id']}}
    elif tool in ('record_transaction', 'update_transaction', 'delete_transaction', 'restore_transaction'):
        entry_id = result.get('id') or arguments.get('entry_id')
        if entry_id:
            target = {'tool':'get_transaction', 'args':{'entry_id':entry_id}}
    elif tool in ('confirm_bill_payment', 'skip_bill_occurrence') and arguments.get('occurrence_id'):
        target = {'tool':'get_bill_occurrence', 'args':{'occurrence_id':arguments['occurrence_id']}}
    elif tool == 'assign_task_to_day' and arguments.get('day'):
        target = {'tool':'list_day_schedule', 'args':{'day':arguments['day']}}
    if target:
        return json.dumps({**result, 'next_call':target}, ensure_ascii=False, default=str)
    return value


class FailureTracker:
    def __init__(self):
        self.failures: dict[str, tuple[int, dict]] = {}

    @staticmethod
    def key(tool, arguments):
        return tool + '\0' + json.dumps(arguments, sort_keys=True, ensure_ascii=False, default=str)

    def blocked(self, tool, arguments):
        count, previous = self.failures.get(self.key(tool, arguments), (0, {}))
        if count and previous.get('write_status') == 'unknown':
            return {**previous, 'ok':False, 'code':'unresolved_write', 'retryable':False,
                    'error':'前次写入结果不明，本次未重复提交。',
                    'next_step':'先读取远端或业务对象确认结果；需要用户处理时说明阻塞点。'}
        if count < 2:
            return None
        return {**previous, 'ok':False, 'code':'repeated_failure', 'retryable':False,
                'error':'相同工具和参数已经连续失败两次，本次未再次执行。',
                'previous_error':previous.get('error', ''),
                'next_step':'按已有错误修正参数或执行 next_call；仍无法解决时说明阻塞点，不继续原样试错。'}

    def record(self, tool, arguments, result):
        key, value = self.key(tool, arguments), parsed_result(result)
        if isinstance(value, dict) and value.get('ok') is False:
            count, _ = self.failures.get(key, (0, {}))
            self.failures[key] = (count + 1, value)
            if len(self.failures) > 80:
                self.failures.pop(next(iter(self.failures)))
        else:
            self.failures.pop(key, None)
