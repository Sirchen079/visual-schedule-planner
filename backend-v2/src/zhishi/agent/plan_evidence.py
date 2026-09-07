"""Resolve progress evidence to completed calls in the same conversation."""
from sqlalchemy import select

from zhishi.agent.tool_feedback import parsed_result
from zhishi.domain.models import AIRun, AIToolExecution


def resolve_evidence(db, conversation_id, call_ids: list[str]) -> list[dict]:
    if not call_ids:
        return []
    if conversation_id is None:
        raise ValueError('当前会话不可用，不能关联执行回执')
    rows = db.scalars(select(AIToolExecution).join(AIRun, AIRun.run_id == AIToolExecution.run_id).where(
        AIRun.conversation_id == conversation_id, AIToolExecution.call_id.in_(call_ids)).order_by(AIToolExecution.id))
    found = {}
    for row in rows:
        value = parsed_result(row.result_json)
        if isinstance(value, str):
            value = parsed_result(value)
        if row.status == 'completed' and not (isinstance(value, dict) and value.get('ok') is False) \
                and row.tool not in ('update_work_plan', 'propose_plan'):
            found[row.call_id] = {'call_id':row.call_id, 'tool':row.tool, 'run_id':row.run_id}
    missing = [call_id for call_id in call_ids if call_id not in found]
    if missing:
        raise ValueError('这些调用没有本会话成功回执：' + ', '.join(missing)[:250])
    return [found[call_id] for call_id in dict.fromkeys(call_ids)]
