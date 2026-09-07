"""L2 大颗粒工具：一次调用完成旧版需十几个连环调用的任务。
分工原则：LLM 管意图与脏文本理解，算法管 RRULE/调度。
事件通道与子代理模型工厂均为 per-run 注入（runtime 经 AgentDeps 传入 ctx.deps），
不再使用模块级全局（多会话并发不串线）；需要 ctx 的工具在签名中声明 ctx 参数，
runtime._wrap_tool 检测后注入（模型 schema 不含 ctx）。"""
from __future__ import annotations
import json
from datetime import date
from typing import Any
from sqlalchemy.orm import Session
from typing import Annotated
from pydantic import Field
from zhishi.agent.mutations import execute_mutation
from zhishi.agent.tools.input_models import (AssignmentInput, PlanStepInput, RequestKey,
                                            TimetableInput, validate_items)


def _json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def _emit_event(deps: Any, event: dict) -> None:
    """deps.emit 是 runtime 的 per-run asyncio.Queue（put_nowait）。"""
    emit = getattr(deps, "emit", None)
    if emit is not None:
        emit.put_nowait(event)


def subagent_specs(db: Session) -> list:
    """子代理可用的工具集：仅 readonly（写类/confirm/递归 task 一律不进）。"""
    from zhishi.agent.tools.registry import specs_for
    return [s for s in specs_for(db) if s.safety == "readonly"]


def import_document(db: Session, file_id: int, ctx=None) -> str:
    """读取资料库文档的结构化内容（正文 + 表格行列）。上传课表/名单/任何文档后，
    必须先用本工具查看内容，再决定如何转化（如整理成 import_timetable 条目）。
    返回 kind：text/csv/docx/xlsx/pdf 可直接读取；image 需用户以图片附件随消息发送（走视觉）；
    failed 时向用户说明需转换格式。"""
    from zhishi.domain.library import service as ls
    from zhishi.infra.config import get_settings
    file = ls.get_file(db, file_id)
    storage_root = (ctx.deps.storage_root if ctx is not None else None) or get_settings().attachments_dir
    doc = ls.ensure_parsed(db, file, storage_root=storage_root)
    data = json.loads(doc.to_json()) if doc.kind != "image" else {"kind": "image",
            "text": "图片文档：请让用户把图片作为对话附件发送，或将关键内容粘贴为文字", "tables": []}
    if file.parse_status == "failed":
        data = json.loads(file.extracted_text)
    data.pop('blocks', None)
    data['preview_only'] = True
    data['next_call'] = {'tool':'read_material', 'args':{'file_id':file_id}}
    data['reading_note'] = '本工具只提供结构预览；读取后续页面或正文请按 next_call 继续。'
    data["file"] = {"id": file.id, "name": file.original_name}
    return _json(data)


DEFAULT_PERIOD_TIMES = {
    1: ("08:00", "08:45"), 2: ("08:55", "09:40"), 3: ("10:00", "10:45"),
    4: ("10:55", "11:40"), 5: ("14:00", "14:45"), 6: ("14:55", "15:40"),
    7: ("16:00", "16:45"), 8: ("16:55", "17:40"), 9: ("19:00", "19:45"),
    10: ("19:55", "20:40"), 11: ("21:00", "21:45"), 12: ("21:55", "22:40"),
}


def _conflict_pair_key(conflict: dict) -> tuple:
    """重叠对的稳定身份（跨日期去重：重复日程每周重现属同一对冲突）。"""
    def _ident(item: dict):
        return item.get("event_id") or item.get("task_id") or item.get("entry_id") \
            or item.get("title")
    return tuple(sorted(_ident(i) for i in conflict["items"]))


def _rule_semantics(rrule: str | None, anchor: date) -> tuple:
    """RRULE 语义等价键（判重用）：FREQ/INTERVAL/BYDAY/UNTIL + 首现锚点日。
    锚点日区分单/双周相位与起始周（同 INTERVAL=2 的单双周靠它区分）；
    无 rrule 的单次日程以日期本身为键。"""
    if not rrule:
        return ("once", anchor.isoformat())
    parts = dict(p.split("=", 1) for p in rrule.split(";") if "=" in p)
    return ("recur", parts.get("FREQ", ""), parts.get("INTERVAL", "1"),
            parts.get("BYDAY", ""), parts.get("UNTIL", ""), anchor.isoformat())


def import_timetable(db: Session, semester_start: str, entries: list[TimetableInput],
                     category: str = "course", request_key: RequestKey | None = None, ctx=None) -> str:
    """把课表条目批量导入为重复日程（一步完成创建+冲突检测+去重）。entries 每项：
    {title, weekday(1=周一..7=周日), periods:[节次...], location?, week_kind(range连续/odd单周/even双周),
    start_week, end_week}；semester_start=第1周周一的 ISO 日期。
    周次规则来自课表原文（如 连续周2-13周/单周/双周），照实填写。
    幂等：判重键 = (title, weekday, start_time, 周次规则语义)——同名课不同星期/节次/周次
    都是合法条目；location 不参与判重。命中既有日程自动跳过。
    返回 {created, skipped, conflicts, errors} 报告，
    conflicts 为同批/与既有的时间重叠对（同一对重叠只报首日一次）。"""
    from datetime import timedelta
    from zhishi.domain.schedule import service as ss
    from zhishi.domain.schedule.conflicts import check_conflicts
    from zhishi.domain.schedule.weeks import week_spec_to_event
    from zhishi.domain.models import Event

    def _event_key(e: Event) -> tuple:
        return (e.title, e.date.weekday() + 1, e.start_time or "",
                _rule_semantics(e.recur_rrule, e.date))

    try:
        anchor = date.fromisoformat(semester_start)
        if anchor.weekday() != 0:
            raise ValueError('semester_start 必须是周一')
        entries = validate_items(TimetableInput, entries)
        prepared = []
        for ent in entries:
            if not ent['title'].strip():
                raise ValueError('课程标题不能为空白')
            periods = sorted(set(ent['periods']))
            if periods != list(range(periods[0], periods[-1] + 1)):
                raise ValueError('不连续节次请拆成不同条目，避免占用中间空闲时间')
            spec = week_spec_to_event(title=ent['title'], weekday=ent['weekday'],
                week_kind=ent.get('week_kind', 'range'), start_week=ent['start_week'],
                end_week=ent['end_week'], semester_start=anchor)
            prepared.append((ent, spec, DEFAULT_PERIOD_TIMES[periods[0]][0], DEFAULT_PERIOD_TIMES[periods[-1]][1]))
        def action():
            existing = {_event_key(e) for e in db.query(Event).all()}
            created, skipped = [], []
            for ent, spec, start_t, end_t in prepared:
                key = (ent['title'], ent['weekday'], start_t, _rule_semantics(spec['recur_rrule'], spec['date']))
                if key in existing:
                    skipped.append({'title':ent['title'], 'reason':'同名同时段已存在'})
                    continue
                event = ss.create_event(db, title=ent['title'], date=spec['date'], start_time=start_t,
                    end_time=end_t, location=ent.get('location') or '', category=category,
                    recur_rrule=spec['recur_rrule'], repeat_note=spec['repeat_note'], commit=False)
                created.append({'event_id':event.id, 'title':event.title})
                existing.add(key)
            last = anchor + timedelta(weeks=max((e['end_week'] for e in entries), default=1))
            seen, conflicts = set(), []
            for conflict in check_conflicts(db, anchor, last):
                key = _conflict_pair_key(conflict)
                if key not in seen:
                    seen.add(key)
                    conflicts.append(conflict)
            return {'created':len(created), 'created_events':created, 'skipped':skipped,
                    'conflicts':conflicts, 'errors':[]}
        return execute_mutation(db, tool='import_timetable', arguments={
            'semester_start':semester_start, 'entries':entries, 'category':category},
            action=action, ctx=ctx, request_key=request_key)
    except (ValueError, TypeError) as exc:
        from zhishi.agent.mutations import MutationConflict
        if isinstance(exc, MutationConflict):
            raise
        db.rollback()
        return _json({'ok':False, 'code':'invalid_timetable', 'write_status':'not_applied',
                      'created':0, 'skipped':[], 'conflicts':[],
                      'errors':[{'entry':'', 'error':str(exc)[:400]}],
                      'next_step':'整批没有保存；按错误修正条目后重试，保留同一 request_key。'})


def plan_day(db: Session, day: str) -> str:
    """生成某天（YYYY-MM-DD）的智能排期建议（只读，不写库）。
    算法按 逾期>优先级>截止 排序，装入工作时段空闲块并尊重每日容量。
    向用户展示建议；用户同意后调用 apply_day_plan 落地。"""
    from zhishi.domain.schedule import planner
    result = planner.plan_day(db, date.fromisoformat(day))
    result['next_call'] = ({'tool':'apply_day_plan', 'args':{'day':day, 'assignments':result['assignments']}}
                           if result['assignments'] else None)
    result['next_step'] = '向用户展示建议；确认后使用 next_call，参数已完整生成。' if result['assignments'] else '没有可安排条目，查看 unassigned 原因。'
    return _json(result)


def apply_day_plan(db: Session, day: str, assignments: list[AssignmentInput],
                   request_key: RequestKey | None = None, ctx=None) -> str:
    """把排期建议落地：为 assignments 每项 {task_id, start, end, title} 创建当日排期
    （source=ai）。直接复制 plan_day 返回的 next_call 参数；保存前重新校验空闲时段。
    整批成功或整批回滚；计划过期时重新 plan_day，不自行编造时段。"""
    from zhishi.domain.schedule import planner, service as ss
    from zhishi.domain.models import TaskScheduleEntry
    from sqlalchemy import select
    assignments = validate_items(AssignmentInput, assignments)
    when = date.fromisoformat(day)
    if len({a['task_id'] for a in assignments}) != len(assignments):
        raise ValueError('同批排期不能重复 task_id')
    def action():
        fresh = {a['task_id']:a for a in planner.plan_day(db, when)['assignments']}
        applied = []
        for a in assignments:
            previous = db.scalar(select(TaskScheduleEntry).where(
                TaskScheduleEntry.task_id == a['task_id'], TaskScheduleEntry.date == when))
            if previous and (previous.start_time, previous.end_time) == (a['start'], a['end']):
                applied.append(a['task_id'])
                continue
            candidate = fresh.get(a['task_id'])
            if not candidate or (candidate['start'], candidate['end']) != (a['start'], a['end']):
                raise StaleDayPlan(day)
            ss.assign_task_to_day(db, a['task_id'], when, start_time=a['start'],
                                  end_time=a['end'], source='ai', note='plan_day 建议排期', commit=False)
            applied.append(a['task_id'])
        return {'applied':applied, 'date':day,
                'next_call':{'tool':'list_day_schedule', 'args':{'day':day}}}
    return execute_mutation(db, tool='apply_day_plan', arguments={'day':day,'assignments':assignments},
                            action=action, ctx=ctx, request_key=request_key)


class StaleDayPlan(ValueError):
    def __init__(self, day):
        self.day = day
        super().__init__('排期建议已过期或条目不匹配，本批次未保存；请重新生成当天计划')


def reschedule_overdue(db: Session, horizon_days: Annotated[int, Field(ge=1, le=31)] = 7,
                       request_key: RequestKey | None = None, ctx=None) -> str:
    """把逾期未完成任务重排进未来空闲日（确定性算法：逾期天数大的优先，
    按 plan_day 同款容量约束分配到 horizon_days 内）。立即写入（source=ai），返回移动报告。"""
    import datetime as _dt
    from sqlalchemy import select
    from zhishi.domain.models import TaskScheduleEntry
    from zhishi.domain.schedule import planner, service as ss
    from zhishi.domain.tasks import service as ts
    if type(horizon_days) is not int or not 1 <= horizon_days <= 31:
        raise ValueError('horizon_days 必须为1至31')
    def action():
        now = _dt.datetime.now()
        booked = set(db.scalars(select(TaskScheduleEntry.task_id).where(TaskScheduleEntry.date >= now.date())))
        overdue = {t.id:t for t in ts.list_tasks(db, status='todo')
                   if t.due_date and t.due_date < now and t.id not in booked}
        pending, moved = set(overdue), []
        for offset in range(horizon_days):
            day = now.date() + _dt.timedelta(days=offset)
            for a in planner.plan_day(db, day, task_ids=pending)['assignments']:
                ss.assign_task_to_day(db, a['task_id'], day, start_time=a['start'], end_time=a['end'],
                                      source='ai', note='逾期重排', commit=False)
                moved.append({'task_id':a['task_id'], 'title':a['title'], 'to':day.isoformat(),
                              'start':a['start'], 'end':a['end']})
                pending.remove(a['task_id'])
            if not pending:
                break
        return {'moved':moved, 'unmoved':[{'task_id':tid,'title':overdue[tid].title} for tid in sorted(pending)],
                'next_call':{'tool':'get_range_load','args':{'start':now.date().isoformat(),'days':horizon_days}}}
    return execute_mutation(db, tool='reschedule_overdue', arguments={'horizon_days':horizon_days},
                            action=action, ctx=ctx, request_key=request_key)


def propose_plan(db: Session, ctx: Any, title: str, steps: list[PlanStepInput]) -> str:
    """提交计划卡片供用户审阅（计划模式专用）。steps 每项：
    {action(做什么), tool(用哪个工具), reason(为什么), args_preview?}。
    系统向用户展示计划卡片；批准后以普通模式按计划执行，拒绝则终止。
    仅在计划模式下使用；计划本身不执行任何操作。"""
    from datetime import datetime
    from zhishi.agent import events as _ev
    from zhishi.domain.models import AIConversation
    steps = validate_items(PlanStepInput, steps, 12)
    conversation_id = getattr(ctx.deps, "conversation_id", None)
    if conversation_id is None:
        return _json({"ok": False, "error": "会话上下文缺失，无法提交计划"})
    conv = db.get(AIConversation, conversation_id)
    if conv is None:
        return _json({"ok": False, "error": "会话不存在"})
    meta = json.loads(conv.meta_json or "{}")
    plans = meta.setdefault("plans", [])
    plan_id = max((int(p.get("id", 0)) for p in plans), default=0) + 1
    plans.append({"id": plan_id, "title": title, "steps": steps, "status": "proposed",
                  "created_at": datetime.now().isoformat(timespec="seconds")})
    conv.meta_json = json.dumps(meta, ensure_ascii=False)
    db.commit()
    _emit_event(ctx.deps, _ev.PlanCard(plan_id=plan_id, title=title, steps=steps).model_dump())
    return _json({"plan_id": plan_id, "status": "proposed",
                  "message": "计划已提交，等待用户审阅；批准后系统将按计划执行。"})


async def task(db: Session, ctx: Any, description: str, instructions: str = "") -> str:
    """派出子代理独立完成一项调研型子任务（只读工具，独立上下文，不污染主对话）。
    适用于：多步检索（如"查未来两周每天负载"）、需要翻多页数据的汇总。
    返回 summary、sources、completed_reads、unresolved；来源由程序记录，未解决项留给主代理处理。
    子代理只能读不能写，最多额外12次模型请求、20次工具调用；进度实时外发。"""
    import uuid
    from pydantic_ai import Agent
    from pydantic_ai.messages import (PartDeltaEvent, PartStartEvent, TextPart,
                                      TextPartDelta)
    from zhishi.agent import events as _ev
    from zhishi.agent import prompts as _prompts
    from zhishi.agent.runtime import _wrap_for_subagent, current_run_usage
    from zhishi.agent.subtask_results import SubtaskEvidence
    from zhishi.agent.tool_feedback import FailureTracker
    from pydantic_ai.usage import UsageLimits
    import asyncio
    evidence, tracker = SubtaskEvidence(), FailureTracker()

    deps = ctx.deps   # per-run 注入：emit 队列 / 子代理模型工厂（多会话并发不串线）

    def _emit(event: dict) -> None:
        _emit_event(deps, event)

    sub_id = uuid.uuid4().hex[:8]
    _emit(_ev.SubagentStarted(subagent_id=sub_id, description=description).model_dump())

    def _delta(text: str) -> None:
        if text:
            _emit(_ev.SubagentDelta(subagent_id=sub_id, delta=text).model_dump())

    async def _run() -> str:
        factory = getattr(deps, "sub_model_factory", None)
        if factory is None:
            raise RuntimeError("子代理模型未配置（deps.sub_model_factory 未注入）")
        from zhishi.agent.context_budget import context_budget_hooks
        from zhishi.agent.attachments import media_capability_hooks
        from zhishi.agent.compaction import request_compaction_hooks
        from zhishi.agent.tool_discovery import ToolDiscovery, SEARCH_DESCRIPTION
        from zhishi.agent.tool_results import tool_result_hooks
        from zhishi.domain.models import AISkill
        from sqlalchemy import select
        discovery = ToolDiscovery([(row.name, row.content) for row in db.scalars(
            select(AISkill).where(AISkill.enabled.is_(True), AISkill.is_builtin.is_(True)))])
        sub = Agent(
            model=factory(),
            output_type=str,
            instructions=_prompts.build_instructions(db, defer_builtin=True)
            + "\n你是只读调研子代理：只允许调用只读工具，完成后用一段话汇报结论。",
            retries=2,
            capabilities=[discovery.hook(), media_capability_hooks(getattr(deps, 'model_config', None)),
                          tool_result_hooks(getattr(deps, 'model_config', None), db, getattr(deps, 'conversation_id', None)),
                          request_compaction_hooks(getattr(deps, 'model_config', None)),
                          context_budget_hooks(getattr(deps, 'model_config', None), allow_truncation=False)],
        )
        sub.tool(discovery.search, name='search_tools', description=SEARCH_DESCRIPTION)
        for spec in subagent_specs(db):
            sub.tool_plain(_wrap_for_subagent(spec, db, ctx, tracker=tracker, observer=evidence.record),
                           name=spec.name, description=spec.description)
        seed = current_run_usage()   # 主 run 的 RunUsage 原对象：子 run 就地累加=用量并入
        kwargs = {"usage": seed} if seed is not None else {}
        kwargs['usage_limits'] = UsageLimits(request_limit=min(30, (seed.requests if seed else 0) + 12),
                                            tool_calls_limit=min(40, (seed.tool_calls if seed else 0) + 20))
        async with sub.iter(f"任务：{description}\n补充要求：{instructions or '无'}",
                            **kwargs) as run:
            async for node in run:
                if Agent.is_model_request_node(node):
                    async with node.stream(run.ctx) as stream:
                        async for evt in stream:
                            # 两种形态都透传：真实 provider 逐 token delta；
                            # FunctionModel 单串文本走 PartStartEvent(整段 TextPart)
                            if isinstance(evt, PartDeltaEvent) \
                                    and isinstance(evt.delta, TextPartDelta):
                                _delta(evt.delta.content_delta)
                            elif isinstance(evt, PartStartEvent) \
                                    and isinstance(evt.part, TextPart):
                                _delta(evt.part.content)
        if run.result is None:
            raise RuntimeError("子代理运行未产生结果")
        return str(run.result.output)

    try:
        async with asyncio.timeout(120):
            summary = await _run()
    except Exception as exc:  # 子代理失败不拖垮主 run：事件如实上报，错误文本回传模型
        _emit(_ev.SubagentCompleted(subagent_id=sub_id, ok=False,
                                    summary=str(exc)[:300]).model_dump())
        return _json(evidence.report('', error=str(exc)[:300] or '子任务超过时间预算'))
    _emit(_ev.SubagentCompleted(subagent_id=sub_id, ok=True,
                                summary=summary[:500]).model_dump())
    return _json(evidence.report(summary))
