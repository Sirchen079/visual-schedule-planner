import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from zhishi.agent.tools.registry import ToolSpec, register
from zhishi.domain import followups
from zhishi.domain.models import SecretaryFollowup
from zhishi.domain.research import service


def _result(db: Session, row: SecretaryFollowup) -> str:
    data = followups.to_read(db,row,include_plan=True).model_dump(mode='json')
    plan = data.pop('plan')
    if plan:
        data['plan_summary'] = {'scheduled':len(plan['assignments']), 'unassigned':len(plan['unassigned']),
            'preserved':len(plan['preserved']), 'state':plan['state'],
            'first_assignments':plan['assignments'][:20], 'first_unassigned':plan['unassigned'][:20]}
    if row.status == 'pending' and row.plan_id and plan and plan['state'] == 'draft':
        data['next_call'] = {'tool':'apply_secretary_followup','args':{'followup_id':row.id,'version':row.version}}
        data['next_step'] = '说明调整原因和未排入项，按用户授权通过权限门落实；不要再次创建任务。'
    elif row.status == 'applied':
        data['next_call'] = {'tool':'get_research_project','args':{'project_id':row.project_id}}
        data['next_step'] = '读取实际进度并汇报本次调整；没有新要求时到此结束。'
    elif row.status == 'pending' and row.kind == 'needs_plan':
        context = service.detail(db, row.project_id)
        data['project_context'] = context.project.model_dump(mode='json')
        data['next_step'] = context.next_step
        if context.next_step.get('tool') and not context.next_step.get('required_input'):
            data['next_call'] = {key:context.next_step[key] for key in ('tool','args')}
    else:
        data['project_context'] = service.to_read(db, service.get_project(db, row.project_id)).model_dump(mode='json')
        if row.kind == 'needs_review' and row.status == 'pending':
            from zhishi.domain.research.feedback import list_feedback
            data['feedback'] = list_feedback(db, row.project_id).model_dump(mode='json')
            data['next_step'] = ('核对用户真实反馈和原始目标；若已授权继续规划，按需要用preview_research_revision在尚未开始任务前补基础或替换内容，'
                '或者preview_research_extension追加下一阶段。目标编号/限制来自get_research_project的revision_targets。'
                'feedback_ids填实际回应的记录，手工时间默认保留。已落实方案回应不等于困难已解决，不重复记录反馈。')
            context = service.detail(db, row.project_id)
            if context.next_step.get('tool') == 'apply_research_plan':
                data['next_call'] = {key:context.next_step[key] for key in ('tool','args')}
                data['next_step'] = '已有最新后续方案，汇报新增内容与反馈依据，按用户授权落实该方案。'
        elif row.kind == 'completed':
            data['next_step'] = ('本阶段任务已完成，结合原始目标与用户反馈回顾；已授权继续学习时用preview_research_extension拟定下一阶段，'
                                 '必要时调整规划窗口；不能把完成任务当成掌握全部内容，不重排已完成任务。')
        elif row.status in ('dismissed','snoozed','resolved'):
            data['next_step'] = '汇报已保存的跟进状态并结束；没有新要求时不要重复检查或重新创建任务。'
        else:
            data['next_step'] = ('说明未排入原因或保留的人工安排。project_context 已包含完整约束和最新版本，无需反复读项目与跟进。'
                '只有用户已给出新的时间条件时，才用 update_research_project 保留原字段并修改相应约束，再 check_research_progress；'
                '否则请用户补充可用时间或决定如何处理冲突，到此结束，不自行延长明确期限。')
    return json.dumps(data,ensure_ascii=False)


def check_research_progress(db: Session, project_id: int) -> str:
    """用户让知时跟进项目、调整错过的学习安排时使用：一次检查实际进度和冲突并准备重排建议。
    复用持久跟进记录，相同状态不重复通知。只有现有自动档和权限允许时才自动落实；否则返回准确的确认工具。"""
    row = followups.check_project(db,project_id)
    return _result(db,row) if row else json.dumps({'ok':True,'project_id':project_id,
        'message':'当前没有需要调整的学习安排。','next_call':{'tool':'get_research_project','args':{'project_id':project_id}}},ensure_ascii=False)


def list_secretary_followups(db: Session, project_id: int | None = None) -> str:
    """读取最近的持续跟进记录、需要处理的原因、已落实或稍后提醒状态；最多20条。"""
    query = select(SecretaryFollowup).order_by(SecretaryFollowup.updated_at.desc()).limit(20)
    if project_id is not None:
        query = query.where(SecretaryFollowup.project_id == project_id)
    return json.dumps([followups.to_read(db,row).model_dump(mode='json') for row in db.scalars(query)],ensure_ascii=False)


def get_secretary_followup(db: Session, followup_id: int) -> str:
    """读取具体跟进的最新版本、调整数量及确定的下一工具；恢复冲突后先读本工具。"""
    return _result(db,followups.get(db,followup_id))


def apply_secretary_followup(db: Session, followup_id: int, version: int) -> str:
    """落实已保存的跟进重排。必须使用返回的编号和版本；实际状态或日历变化会拒绝旧建议。
    任务编号、完成记录和手工调整保留；已落实的建议重复调用只返回结果。"""
    return _result(db,followups.apply(db,followup_id,version))


def respond_secretary_followup(db: Session, followup_id: int, version: int, snooze_until: datetime | None = None) -> str:
    """用户明确要求稍后提醒或忽略这条跟进时使用。snooze_until为未来30天内时间；留空表示忽略当前状态。
    忽略不删除任务。相同状态不再打扰；有新问题仍可生成新跟进。"""
    return _result(db,followups.respond(db,followup_id,version,snooze_until=snooze_until))


for fn,safety in [(check_research_progress,'safe'),(list_secretary_followups,'readonly'),
                  (get_secretary_followup,'readonly'),(apply_secretary_followup,'confirm'),
                  (respond_secretary_followup,'confirm')]:
    register(ToolSpec(fn.__name__,fn.__doc__ or '',safety,None,fn))
