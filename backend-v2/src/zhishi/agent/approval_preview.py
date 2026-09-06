"""Concrete research changes shown before a deferred apply is authorized."""
from sqlalchemy.orm import Session


def build(db: Session, tool: str, args: dict) -> str:
    if tool != 'apply_research_plan':
        return ''
    from zhishi.domain.research import service
    from zhishi.infra.local_clock import snapshot
    try:
        plan = service.plan_read(service.get_plan(db, int(args['plan_id'])))
    except (ValueError, TypeError, KeyError):
        return '方案暂无法读取；执行时将重新校验方案状态。'
    lines = [f'方案 #{plan.id} · 项目 #{plan.project_id}', plan.rationale,
             f'核对时间：{snapshot()["now"]}']
    if plan.revision:
        revision = plan.revision
        action = '替换内容，保留任务编号' if revision.mode == 'replace' else '在此之前插入新内容'
        lines += [f'{action}：{revision.before_task.title}',
                  '原内容：'+revision.before_task.notes[:1200]]
        lines += ['允许调整手工时间：'+str(item.get('title', '')) for item in revision.moved_manual]
        lines += revision.warnings
    changed = [u for u in plan.units if not u.existing_task_id or u.replace_content]
    for unit in changed[:8]:
        lines.append(f'{unit.title} · {unit.minutes}分钟：{unit.outcome[:400]}')
    if len(changed) > 8:
        lines.append(f'共{len(changed)}项新内容，完整方案可在学习与研究项目页查看。')
    lines.append(f'安排{len(plan.assignments)}个时段；{len(plan.unassigned)}项未排入。')
    lines.append('确认时重新校验项目、学习记录与日历；已开始的安排不会自动移动。')
    return '\n'.join(lines)
