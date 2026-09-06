# src/zhishi/agent/tools/macro.py
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


def import_timetable(db: Session, semester_start: str, entries: list[dict],
                     category: str = "course") -> str:
    """把课表条目批量导入为重复日程（一步完成创建+冲突检测+去重）。entries 每项：
    {title, weekday(1=周一..7=周日), periods:[节次...], location?, week_kind(range连续/odd单周/even双周),
    start_week, end_week}；semester_start=第1周周一的 ISO 日期。
    周次规则来自课表原文（如 连续周2-13周/单周/双周），照实填写。
    幂等：判重键 = (title, weekday, start_time, 周次规则语义)——同名课不同星期/节次/周次
    都是合法条目；location 不参与判重（Bug A 回归）。命中既有日程自动跳过。
    返回 {created, skipped, conflicts, errors} 报告，
    conflicts 为同批/与既有的时间重叠对（同一对重叠只报首日一次）。"""
    from datetime import timedelta
    from zhishi.domain.schedule import service as ss
    from zhishi.domain.schedule.conflicts import check_conflicts
    from zhishi.domain.schedule.weeks import week_spec_to_event
    from zhishi.domain.models import Event

    anchor = date.fromisoformat(semester_start)
    if anchor.weekday() != 0:
        return _json({"created": 0, "skipped": [], "conflicts": [],
                      "errors": [{"entry": "", "error": "semester_start 必须是周一"}]})

    def _event_key(e: Event) -> tuple:
        return (e.title, e.date.weekday() + 1, e.start_time or "",
                _rule_semantics(e.recur_rrule, e.date))

    existing = {_event_key(e) for e in db.query(Event).all()}
    created, skipped, errors = [], [], []
    for ent in entries:
        try:
            periods = sorted(int(p) for p in ent["periods"])
            start_t = DEFAULT_PERIOD_TIMES[periods[0]][0]
            end_t = DEFAULT_PERIOD_TIMES[periods[-1]][1]
            spec = week_spec_to_event(
                title=ent["title"], weekday=int(ent["weekday"]),
                week_kind=ent.get("week_kind", "range"),
                start_week=int(ent["start_week"]), end_week=int(ent["end_week"]),
                semester_start=anchor)
            key = (ent["title"], int(ent["weekday"]), start_t,
                   _rule_semantics(spec["recur_rrule"], spec["date"]))
            if key in existing:
                skipped.append({"title": ent["title"], "reason": "同名同时段已存在"})
                continue
            event = ss.create_event(
                db, title=ent["title"], date=spec["date"],
                start_time=start_t, end_time=end_t,
                location=ent.get("location") or "", category=category,
                recur_rrule=spec["recur_rrule"],
                repeat_note=spec["repeat_note"])   # 人类可读周次规则（re #020 事项2）
            created.append(key)
            existing.add(key)
            _ = event
        except (KeyError, ValueError, TypeError) as exc:
            errors.append({"entry": ent.get("title", ""), "error": str(exc)[:200]})
    first = anchor
    last = anchor + timedelta(weeks=max(
        (int(e.get("end_week", 1)) for e in entries), default=1))
    # 偏差（对计划）：check_conflicts 逐日报告，重复日程每周重现会产生 N 条同一对
    # 冲突；按重叠对去重只保留首日一条（同一冲突对的稳定语义，见 _conflict_pair_key）
    seen_pairs: set[tuple] = set()
    conflicts = []
    for c in check_conflicts(db, first, last):
        k = _conflict_pair_key(c)
        if k not in seen_pairs:
            seen_pairs.add(k)
            conflicts.append(c)
    return _json({"created": len(created), "skipped": skipped,
                  "conflicts": conflicts, "errors": errors})


def plan_day(db: Session, day: str) -> str:
    """生成某天（YYYY-MM-DD）的智能排期建议（只读，不写库）。
    算法按 逾期>优先级>截止 排序，装入工作时段空闲块并尊重每日容量。
    向用户展示建议；用户同意后调用 apply_day_plan 落地。"""
    from zhishi.domain.schedule import planner
    return _json(planner.plan_day(db, date.fromisoformat(day)))


def apply_day_plan(db: Session, day: str, assignments: list[dict]) -> str:
    """把排期建议落地：为 assignments 每项 {task_id, start, end, title} 创建当日排期
    （source=ai）。仅接受来自 plan_day 输出的条目，不自行编造。"""
    from zhishi.domain.schedule import service as ss
    applied = []
    for a in assignments:
        ss.assign_task_to_day(db, int(a["task_id"]), date.fromisoformat(day),
                              start_time=a.get("start"), end_time=a.get("end"),
                              source="ai", note="plan_day 建议排期")
        applied.append(a["task_id"])
    return _json({"applied": applied, "date": day})


def reschedule_overdue(db: Session, horizon_days: int = 7) -> str:
    """把逾期未完成任务重排进未来空闲日（确定性算法：逾期天数大的优先，
    按 plan_day 同款容量约束分配到 horizon_days 内）。立即写入（source=ai），返回移动报告。"""
    import datetime as _dt
    from zhishi.domain.schedule import planner, service as ss
    from zhishi.domain.tasks import service as ts
    now = _dt.datetime.now()
    overdue = [t for t in ts.list_tasks(db, status="todo") if t.due_date and t.due_date < now]
    overdue.sort(key=lambda t: t.due_date)      # 最早逾期优先
    moved = []
    for d_off in range(horizon_days):
        day = (now + _dt.timedelta(days=d_off)).date()
        plan = planner.plan_day(db, day)
        used = sum(a["estimated_minutes"] for a in plan["assignments"])
        capacity = plan["capacity_minutes"]
        while overdue and used < capacity:
            t = overdue[0]
            need = t.estimated_minutes or 60
            if used + need > capacity:
                break
            ss.assign_task_to_day(db, t.id, day, source="ai", note="逾期重排")
            moved.append({"task_id": t.id, "title": t.title, "to": day.isoformat()})
            overdue.pop(0)
            used += need
    unmoved = [{"task_id": t.id, "title": t.title} for t in overdue]
    return _json({"moved": moved, "unmoved": unmoved})


def propose_plan(db: Session, ctx: Any, title: str, steps: list[dict]) -> str:
    """提交计划卡片供用户审阅（计划模式专用）。steps 每项：
    {action(做什么), tool(用哪个工具), reason(为什么), args_preview?}。
    系统向用户展示计划卡片；批准后以普通模式按计划执行，拒绝则终止。
    仅在计划模式下使用；计划本身不执行任何操作。"""
    from datetime import datetime
    from zhishi.agent import events as _ev
    from zhishi.domain.models import AIConversation
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
    返回子代理的结论文本。子代理只能读不能写；进度以 subagent_* 事件实时外发。"""
    import uuid
    from pydantic_ai import Agent
    from pydantic_ai.messages import (PartDeltaEvent, PartStartEvent, TextPart,
                                      TextPartDelta)
    from zhishi.agent import events as _ev
    from zhishi.agent import prompts as _prompts
    from zhishi.agent.runtime import _wrap_for_subagent, current_run_usage

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
        sub = Agent(
            model=factory(),
            output_type=str,
            instructions=_prompts.build_instructions(db)
            + "\n你是只读调研子代理：只允许调用只读工具，完成后用一段话汇报结论。",
            retries=2,
            capabilities=[media_capability_hooks(getattr(deps, 'model_config', None)),
                          request_compaction_hooks(getattr(deps, 'model_config', None)),
                          context_budget_hooks(getattr(deps, 'model_config', None))],
        )
        for spec in subagent_specs(db):
            sub.tool_plain(_wrap_for_subagent(spec, db),
                           name=spec.name, description=spec.description)
        seed = current_run_usage()   # 主 run 的 RunUsage 原对象：子 run 就地累加=用量并入
        kwargs = {"usage": seed} if seed is not None else {}
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
        summary = await _run()
    except Exception as exc:  # 子代理失败不拖垮主 run：事件如实上报，错误文本回传模型
        _emit(_ev.SubagentCompleted(subagent_id=sub_id, ok=False,
                                    summary=str(exc)[:300]).model_dump())
        return _json({"ok": False, "error": str(exc)[:300]})
    _emit(_ev.SubagentCompleted(subagent_id=sub_id, ok=True,
                                summary=summary[:500]).model_dump())
    return summary
