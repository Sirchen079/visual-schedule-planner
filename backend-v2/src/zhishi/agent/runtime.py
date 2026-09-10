"""AgentRuntime：PydanticAI 基座之上的组装与事件翻译。
run_stream 是唯一驱动入口：yield 契约事件 dict（events.py 的模型 dump），
落库消息与 run trace。审批暂停时以 awaiting_approval 结束并返回；
恢复由 resume_stream 用 history + DeferredToolResults 重启新 execution。"""
from __future__ import annotations
import asyncio
import contextvars
import inspect
import json
import time
import uuid
from dataclasses import dataclass, field
from inspect import Parameter, Signature
from typing import Any, AsyncIterator

from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.tools import DeferredToolRequests, DeferredToolResults, RunContext
from sqlalchemy.orm import Session

from zhishi.agent import events as ev
from zhishi.agent import prompts
from zhishi.agent.permissions import IRREVOCABLE_TOOLS, classify
from zhishi.agent.tool_feedback import FailureTracker, add_followup, failure_result


@dataclass
class AgentDeps:
    db: Session
    emit: Any                      # asyncio.Queue：子代理/工具/计划卡片事件外发（per-run 隔离）
    sub_model_factory: Any = None  #  -> Model：task 子代理模型工厂（per-run）
    conversation_id: int | None = None
    run_id: str | None = None
    capture_key: str = ""
    storage_root: Any = None
    model_config: Any = None
    failure_tracker: FailureTracker = field(default_factory=FailureTracker)


# 当前执行工具调用的主 RunContext（macro.task 经此取主 usage 做并入）
_run_ctx_var: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "zhishi_main_run_ctx", default=None)


def current_run_usage():
    """主 run 的 RunUsage（子代理种子 usage：pydantic-ai 以原对象就地累加，天然并入）。"""
    ctx = _run_ctx_var.get()
    return getattr(ctx, "usage", None) if ctx is not None else None


def _sse_event(model_cls, **fields) -> dict:
    return model_cls(**fields).model_dump()


def _args_dict(args) -> dict:
    """ToolCallPart.args 可能是 dict 或 JSON 字符串，统一为 dict（契约事件要求）。"""
    if isinstance(args, dict):
        return args
    if isinstance(args, str):
        try:
            parsed = json.loads(args)
            return parsed if isinstance(parsed, dict) else {"_raw": args}
        except ValueError:
            return {"_raw": args}
    return {}


async def _node_stream_events(node, ctx, queue):
    """Forward progress while a model connection or tool execution is awaiting."""
    async def events():
        async with node.stream(ctx) as stream:
            async for event in stream:
                yield event
    source = events()
    pending = asyncio.create_task(anext(source))
    extra = asyncio.create_task(queue.get())
    try:
        while True:
            ready, _ = await asyncio.wait((pending, extra), return_when=asyncio.FIRST_COMPLETED)
            if extra in ready:
                value = extra.result()
                extra = asyncio.create_task(queue.get())
                yield None, value
            if pending in ready:
                try:
                    value = pending.result()
                except StopAsyncIteration:
                    break
                yield value, None
                pending = asyncio.create_task(anext(source))
    finally:
        if extra.done() and not extra.cancelled() and extra.exception() is None:
            queue.put_nowait(extra.result())
        pending.cancel()
        extra.cancel()
        await asyncio.gather(pending, extra, return_exceptions=True)
        await source.aclose()


class AgentRuntime:
    def __init__(self, model, db: Session, sub_model_factory=None, storage_root=None,
                 session_factory=None, model_config=None):
        self.model = model
        self.model_config = model_config
        self.db = db
        # 子代理模型工厂（缺省复用主 model）；macro.task 派生只读子代理时调用
        self.sub_model_factory = sub_model_factory
        # 附件存储根（缺省全局 settings；应用装配时传 app.state.storage_root 以支持 data_dir 覆盖）
        from pathlib import Path
        self.storage_root: Path | None = Path(storage_root) if storage_root else None
        # 工具调用 = 独立事务：每次工具执行从工厂开新 Session（用完即关），
        # run 级 db 只用于消息/审批落库（Bug B：根治一次失败毒化整个 run 的 Session）。
        # 未显式提供时从 run 级 Session 的 bind 派生（测试与旧调用方零改动兼容）。
        if session_factory is not None:
            self.session_factory = session_factory
        else:
            from sqlalchemy.orm import sessionmaker
            self.session_factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)

    def _build_agent(self, plan_mode: bool = False, conversation_id: int | None = None, emit=None, brainstorm_mode: bool = False) -> Agent:
        db = self.db
        from zhishi.agent.tools import atomic_read  # noqa: F401 触发注册
        from zhishi.agent.tools import web_tools  # noqa: F401 触发注册
        from zhishi.agent.tools.registry import specs_for
        from zhishi.agent.context_budget import context_budget_hooks
        from zhishi.agent.prompt_cache import live_clock_hooks
        from zhishi.agent.attachments import media_capability_hooks
        from zhishi.agent.tool_discovery import ToolDiscovery, SEARCH_DESCRIPTION, EXECUTE_DESCRIPTION
        from zhishi.agent.tool_results import tool_result_hooks
        from zhishi.agent.diagnostics import request_diagnostic_hooks
        from zhishi.domain.models import AISkill
        from sqlalchemy import select
        unavailable = {}
        discovery = ToolDiscovery([(row.name, row.content) for row in db.scalars(
            select(AISkill).where(AISkill.enabled.is_(True), AISkill.is_builtin.is_(True))) if row.name not in prompts.THINKING_SKILLS], unavailable=unavailable,
            plan_mode=plan_mode)

        agent = Agent(
            self.model,
            deps_type=AgentDeps,
            output_type=[str, DeferredToolRequests],
            instructions=prompts.build_instructions(db, plan_mode=plan_mode, brainstorm_mode=brainstorm_mode, defer_builtin=True),
            retries=2,
            toolsets=self._mcp_toolsets(unavailable=unavailable, readonly_only=plan_mode or brainstorm_mode),
            capabilities=[discovery.hook(), media_capability_hooks(self.model_config),
                          tool_result_hooks(self.model_config, db, conversation_id, discovery),
                          self._compaction_capability(conversation_id, emit),
                          discovery.context_hook(),
                          live_clock_hooks(self.model_config, conversation_id),
                          context_budget_hooks(self.model_config, allow_truncation=False),
                          request_diagnostic_hooks(self.model_config, conversation_id, str(db.get_bind().url))],
        )

        agent.tool(discovery.search, name='search_tools', description=SEARCH_DESCRIPTION)
        agent.tool(discovery.execute, name='execute_tool', description=EXECUTE_DESCRIPTION)
        from zhishi.agent.user_input import ask_user
        agent.tool_plain(ask_user)

        for spec in specs_for(db):
            if brainstorm_mode and (spec.safety != "readonly" or spec.name == "propose_plan"):
                continue
            # 计划模式：只挂只读工具 + propose_plan（写类一律不注册，模型无从调用）
            if plan_mode and spec.safety != "readonly" and spec.name != "propose_plan":
                continue
            fn = self._wrap_tool(spec)
            # 审批统一走动态 ApprovalRequired（权限门是唯一闸门，
            # 覆盖 careful 档下 safe 工具也要确认的场景——规格增强②：单一判定路径）
            agent.tool(fn, name=spec.name, description=spec.description)
        return agent

    def _compaction_capability(self, conversation_id, emit=None):
        from zhishi.agent.compaction import compaction_threshold, compaction_timeout, request_compaction_hooks
        from zhishi.domain.models import AIConversation

        def metadata(conv):
            try:
                value = json.loads(conv.meta_json or '{}') if conv else {}
                return value if isinstance(value, dict) else {}
            except (ValueError, TypeError):
                return {}

        def save(history, summary, fingerprint):
            # Callback runs on the Session owner after the cancellable await.
            conv = self.db.get(AIConversation, conversation_id, populate_existing=True)
            if conv is not None:
                value = metadata(conv)
                from zhishi.agent.session_store import archive_compaction
                archive_compaction(self.db, conversation_id, history, summary, fingerprint)
                value.update(summary=summary, summary_fingerprint=fingerprint)
                conv.meta_json = json.dumps(value, ensure_ascii=False)
                self.db.commit()

        conv = self.db.get(AIConversation, conversation_id) if conversation_id else None
        value = metadata(conv)
        return request_compaction_hooks(
            self.model_config, threshold=compaction_threshold(self.db), timeout=compaction_timeout(self.db),
            stored_summary=value.get('summary'), stored_fingerprint=value.get('summary_fingerprint'),
            on_compaction=save if conversation_id else None,
            on_progress=(lambda stage: emit.put_nowait(_sse_event(ev.StageChanged, stage=stage))) if emit is not None else None)

    def _mcp_toolsets(self, *, unavailable=None, readonly_only=False) -> list:
        """对每个 enabled 的 MCP 服务器构造带权限门的 toolset。
        stdio 服务器须 trusted=True 才装配（连 client 都不构造 → 不可能拉起
        子进程）；http 传输不受限。
        列取工具发生在 run 内（toolset.get_tools 由 pydantic-ai 异步调用）；
        单个服务器不可达时记录本轮故障，其余工具仍可继续。"""
        from sqlalchemy import select
        from zhishi.adapters import mcp_client
        from zhishi.domain.models import MCPServer
        rows = self.db.scalars(select(MCPServer).where(MCPServer.enabled.is_(True))).all()
        out = []
        for row in rows:
            if row.transport == "stdio" and not row.trusted:
                continue
            client, kwargs = mcp_client.build_client(row)
            out.append(_MCPGatedToolset(
                client, server_id=row.id, id=f"mcp-server-{row.id}", server_row=row,
                unavailable=unavailable, readonly_only=readonly_only,
                init_timeout=float(row.timeout_sec or 30),
                read_timeout=float(row.timeout_sec or 30), **kwargs))
        return out

    def _wrap_tool(self, spec):
        """把 (db: Session, **params) 形态的领域包装函数适配为
        async (ctx: RunContext[AgentDeps], **params) 形态，附带权限判定。
        PydanticAI 的工具 schema 从函数签名与注解推断，故同时以
        __signature__/__annotations__ 暴露去掉 db 后的参数（注解先解析为实对象）。
        声明了 ctx 参数的工具（macro.task/propose_plan）运行时注入 ctx（schema 不含）。
        执行语义：每次调用开独立 Session（工具调用=独立事务），异常回滚后以
        ok=False 错误文本返回给模型（工具失败=错误结果回灌，绝不崩流）。"""
        from typing import get_type_hints
        hints = get_type_hints(spec.fn, include_extras=True)
        orig = inspect.signature(spec.fn)
        takes_ctx = "ctx" in orig.parameters
        params = [Parameter("ctx", kind=Parameter.POSITIONAL_OR_KEYWORD,
                            annotation=RunContext[AgentDeps])]
        params += [p.replace(annotation=hints.get(name, p.annotation))
                   for name, p in orig.parameters.items() if name not in ("db", "ctx")]

        async def _fn(ctx: RunContext[AgentDeps], **kw):
            db: Session = ctx.deps.db
            if not ctx.tool_call_approved:  # deferred 恢复的已批准调用直接放行，不再落审批
                verdict = classify(db, spec.name, kw)
                if verdict == "deny":
                    return json.dumps({"ok": False, "error": f"工具 {spec.name} 不在白名单"},
                                      ensure_ascii=False)
                if verdict == "confirm":
                    from pydantic_ai.exceptions import ApprovalRequired
                    raise ApprovalRequired(metadata={"tool": spec.name, "args": kw})
            tracker = getattr(ctx.deps, 'failure_tracker', None)
            blocked = tracker.blocked(spec.name, kw) if tracker else None
            if blocked:
                return json.dumps(blocked, ensure_ascii=False)
            token = _run_ctx_var.set(ctx)   # macro.task 经 current_run_usage 并入用量

            async def _invoke(tool_db: Session):
                call_args = (tool_db,)
                call_kw = {**kw, **({'ctx': ctx} if takes_ctx else {})}
                from zhishi.domain.models import AIToolExecution
                receipt = None
                if ctx.deps.run_id and ctx.tool_call_id:
                    receipt = AIToolExecution(run_id=ctx.deps.run_id, call_id=ctx.tool_call_id, tool=spec.name)
                    tool_db.add(receipt)
                    tool_db.commit()

                def save_result(value, status='completed'):
                    value = add_followup(spec.name, kw, value)
                    if tracker:
                        tracker.record(spec.name, kw, value)
                    if receipt is not None:
                        receipt.status = status
                        receipt.result_json = json.dumps(value, ensure_ascii=False, default=str)
                        tool_db.commit()
                    return value

                if inspect.iscoroutinefunction(spec.fn):
                    try:
                        return save_result(await spec.fn(*call_args, **call_kw))
                    except Exception as exc:
                        tool_db.rollback()
                        save_result(failure_result(exc, tool=spec.name, arguments=kw,
                                                  readonly=spec.safety == 'readonly'), 'failed')
                        raise

                def invoke_sync():
                    try:
                        return save_result(spec.fn(*call_args, **call_kw))
                    except Exception as exc:
                        tool_db.rollback()
                        save_result(failure_result(exc, tool=spec.name, arguments=kw,
                                                  readonly=spec.safety == 'readonly'), 'failed')
                        raise

                worker = asyncio.create_task(asyncio.to_thread(invoke_sync))
                try:
                    return await asyncio.shield(worker)
                except asyncio.CancelledError:
                    # A thread cannot be aborted. Keep its session and the run lock
                    # alive until any already-started write and its receipt settle.
                    await asyncio.gather(worker, return_exceptions=True)
                    raise

            try:
                try:
                    with self.session_factory() as tool_db:   # 每次调用独立 Session
                        try:
                            raw = await _invoke(tool_db)
                        except BaseException:   # 含 CancelledError：先回滚再外抛
                            _safe_rollback(tool_db)
                            raise
                except Exception as exc:
                    _safe_rollback(db)   # 兜底：run 级会话不得滞留「待回滚」毒化态
                    from zhishi.infra.diagnostics import record, error_details
                    record('application', level='ERROR', module='agent.tools', function=spec.name, **error_details(exc))
                    failure = failure_result(exc, tool=spec.name, arguments=kw, readonly=spec.safety == 'readonly')
                    from zhishi.domain.inbox.service import InboxConflict
                    if isinstance(exc, InboxConflict) and exc.item_id is not None:
                        failure.update(code="inbox_conflict", next_call={
                            "tool": "get_inbox_item", "args": {"item_id": exc.item_id}},
                            next_step="按 next_call 读取最新候选，依据原文或用户澄清修订；有疑问先询问，已落实则停止。不要换键或改用直接创建工具。")
                    from zhishi.domain.research.service import ResearchConflict
                    from zhishi.domain.followups import FollowupConflict
                    from zhishi.domain.library.reading import MaterialConflict
                    if isinstance(exc, MaterialConflict):
                        failure.update(code='material_conflict', next_call={
                            'tool':'read_material', 'args':{'file_id':exc.file_id}},
                            next_step='按返回的真实版本和片段重新读取，再引用原文，不猜页码或沿用旧片段。')
                    if isinstance(exc, FollowupConflict):
                        failure.update(code='followup_conflict', next_call={
                            'tool':'get_secretary_followup', 'args':{'followup_id':exc.followup_id}},
                            next_step='先读最新跟进；状态变化时调用 check_research_progress 重新检查。不要绕过已忽略或稍后提醒的决定。')
                    if isinstance(exc, ResearchConflict):
                        failure.update(code="research_conflict", next_call={
                            "tool":"get_research_project", "args":{"project_id":exc.project_id}},
                            next_step="读取最新项目、任务和计划，按照返回的 next_step 继续；不要改用原子创建工具绕过版本校验。")
                    return json.dumps(failure, ensure_ascii=False)
            finally:
                _run_ctx_var.reset(token)
            return raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False, default=str)

        _fn.__name__ = spec.name
        _fn.__signature__ = Signature(params)
        _fn.__annotations__ = {p.name: p.annotation for p in params}
        return _fn

    def _build_attachment_blocks(self, file_ids: list[int], media_results=None) -> tuple[str, list[dict], list]:
        # Parsing/indexing is blocking; use a Session owned by this worker thread.
        with self.session_factory() as db:
            return self._attachment_blocks(db, file_ids, media_results or {})

    def _attachment_blocks(self, db: Session, file_ids: list[int], media_results: dict) -> tuple[str, list[dict], list]:
        """对话附件 → 模型输入注入块与展示元数据。
        图片附件（needs_vision）读出字节 → pydantic-ai BinaryContent（多模态视觉输入）。
        返回 (inject_text, meta, image_parts)；meta 每项 {id, name, excerpt}。"""
        from zhishi.domain.library import service as ls
        from zhishi.domain.models import LibraryFile
        from zhishi.infra.config import get_settings
        storage_root = self.storage_root or get_settings().attachments_dir
        inject_parts: list[str] = []
        meta: list[dict] = []
        image_parts: list = []
        for fid in file_ids:
            f = db.get(LibraryFile, fid)
            if f is None or f.deleted_at is not None:
                continue
            doc = None
            media = media_results.get(fid)
            if media is None:
                try:
                    doc = ls.ensure_parsed(db, f, storage_root=storage_root)
                except Exception as exc:
                    block = f"（附件 {f.original_name} 解析失败：{str(exc)[:200]}）"
            if media is not None:
                block = f'【附件：{f.original_name}】\n{media.text}'
                if media.binary is not None:
                    image_parts.append(media.binary)
            elif doc is not None and f.parse_status == "needs_vision":
                block = f'（附件 {f.original_name} 内容尚未读取，请检查模型输入能力与视觉 MCP 设置。）'
            elif doc is not None and f.parse_status == "failed":
                note = ""
                try:
                    note = str(json.loads(f.extracted_text or "{}").get("text", ""))[:300]
                except ValueError:
                    pass
                block = f"（附件 {f.original_name} 解析失败：{note}）"
            elif doc is not None:
                tables_text = "\n".join(" | ".join(row) for row in
                                        (r for t in doc.tables for r in t))
                content = f"{doc.text.strip()}\n{tables_text}".strip()[:8000]
                from zhishi.domain.library import reading
                try:
                    reading.ensure_index(db, fid, storage_root)
                    info = reading.summary(db, fid)
                except ValueError as exc:
                    info = {'error':str(exc)}
                block = (f"【附件：{f.original_name}；以下为开头预览】\n{content}\n"
                    f"【完整材料索引】{json.dumps(info, ensure_ascii=False)}\n"
                    f'继续阅读全文：read_material(file_id={fid},part=1)；找具体内容：search_materials(query=短关键词,file_id={fid})。'
                    '预览不代表已读全文；回答与规划时保留页码/行号、片段编号和原文依据。')
            from zhishi.domain.inbox.service import list_items
            prior = list_items(db, status=None, source_file_id=fid, limit=20)
            processed = [{"id": item.id, "item_key": item.item_key, "status": item.status,
                          "kind": item.proposal.kind, "version": item.version,
                          "target_id": item.target_id} for item in prior.items]
            guide = (
                f"【材料编号】source_file_id={fid}；文件名={f.original_name}\n"
                f"【已有处理记录】{json.dumps(processed, ensure_ascii=False)}；共 {prior.total} 条\n"
                "【执行路线】材料已在下方提供，先提取事实，不必重新寻找文件编号。"
                "普通通知/收据/混合材料 → propose_inbox_items；每项使用上面的 source_file_id，"
                "item_key 使用原文稳定位置（单笔收据统一 receipt-total），source_excerpt 摘录原文。"
                "proposal.kind 只能是 task/event/ledger，proposal.data 按相应工具结构填写。"
                "已有 applied/rejected 条目不要重建；已有 pending 条目用 get_inbox_item 再修订。"
                "若记录总数大于已展示数量，先 list_inbox_items 按 source_file_id 分页补齐。"
                "只要关键金额/日期无法确定，先向用户澄清，不编造。候选提交后明确告诉用户到收件箱确认。"
                "课表则走 import_timetable；仅要求阅读/总结时直接回答，不创建候选。\n"
                "若用户要求围绕材料学习/研究，使用 create_research_project → attach_research_material(project_id,file_id) → preview_research_plan；复用这里的文件编号。\n"
            )
            inject_parts.append(f"\n\n{guide}{block}")
            meta.append({"id": fid, "name": f.original_name, "excerpt": block[:500],
                         **(media.metadata if media is not None else {})})
        return "".join(inject_parts), meta, image_parts

    async def run_stream(self, *, user_text: str | None, conversation_id: int | None = None,
                         history: list | None = None,
                         deferred_results: DeferredToolResults | None = None,
                         run_id: str | None = None, cancel_token=None,
                         usage_meta: dict | None = None,
                         attachment_ids: list[int] | None = None,
                         plan_mode: bool = False, research_project_id: int | None = None, brainstorm_mode: bool = False) -> AsyncIterator[dict]:
        """user_text=None + history + deferred_results = 审批复活轮：
        不新增用户消息，直接从 CallToolsNode 继续（logical run 跨 execution）。"""
        db = self.db
        run_id = run_id or uuid.uuid4().hex
        t0 = time.monotonic()

        def stage(s: str) -> dict:
            return _sse_event(ev.StageChanged, stage=s)

        # 1) 会话先解析（run_started 首帧需要真实 conversation_id）
        from zhishi.domain.models import AIConversation, AIMessage
        if conversation_id is None:
            conv = AIConversation(title=(user_text or "审批恢复")[:30])
            db.add(conv); db.commit(); db.refresh(conv)
            conversation_id = conv.id
        else:
            conv = db.get(AIConversation, conversation_id)

        if conv is None:
            raise LookupError('会话不存在，不能在空上下文中继续')
        from zhishi.agent import session_store
        run_row, assistant_row = session_store.begin_turn(db, conversation_id, run_id, user_text, history, attachment_ids or [])

        yield _sse_event(ev.RunStarted, run_id=run_id, conversation_id=conversation_id)
        yield stage("preparing")

        if user_text is not None:
            def read_prefix():
                with self.session_factory() as prefix_db:
                    return prompts.build_user_message_prefix(prefix_db)
            prefix = await asyncio.to_thread(read_prefix)
            full_user: str | None = f"{prefix}{user_text}"
            if research_project_id is not None:
                from zhishi.domain.research.service import model_detail
                context = model_detail(db, research_project_id, excerpts=True)
                full_user += ('\n\n【当前打开的学习/研究项目】以下是最新参考状态。用户说“这个项目”时复用此编号；'
                              '需要正文时 get_research_project，不另建同名项目。用户明确谈其他事项时以用户要求为准。\n'
                              + json.dumps(context, ensure_ascii=False))
            attachment_meta: list[dict] = []
            image_parts: list = []
            if attachment_ids:
                from zhishi.agent.attachments import detect_media, process_media
                from zhishi.domain.models import LibraryFile
                from zhishi.infra.config import get_settings
                media_results = {}
                for fid in dict.fromkeys(attachment_ids):
                    file = db.get(LibraryFile, fid)
                    if file is not None and detect_media(file):
                        media_results[fid] = await process_media(
                            db, self.model_config, file,
                            self.storage_root or get_settings().attachments_dir, user_text)
                inject, attachment_meta, image_parts = await asyncio.to_thread(
                    self._build_attachment_blocks, list(dict.fromkeys(attachment_ids)), media_results)
                full_user = f"{full_user}{inject}"
        else:
            full_user = None
            attachment_meta = []
            image_parts = []

        # Route from configured capabilities before the first provider request.
        from zhishi.agent.attachments import sanitize_history_media
        history = await sanitize_history_media(history or [], self.model_config) or None
        model_input: Any = full_user
        if image_parts and full_user is not None:
            model_input = [full_user, *image_parts]
        if user_text is not None:
            from sqlalchemy import select
            from pydantic_ai.messages import ModelRequest, UserPromptPart
            user_row = db.scalar(select(AIMessage).where(AIMessage.conversation_id == conversation_id,
                AIMessage.role == 'user').order_by(AIMessage.id.desc()).limit(1))
            display = session_store.metadata(user_row.display_json)
            display['brainstorm_mode'] = brainstorm_mode
            if attachment_meta:
                display['attachments'] = attachment_meta
            user_row.display_json = json.dumps(display, ensure_ascii=False)
            session_store.checkpoint(db, run_row, assistant_row,
                [*(history or []), ModelRequest(parts=[UserPromptPart(model_input)])], [])

        # Deferred answers resume the mode recorded with their original user message.
        if user_text is None:
            from sqlalchemy import select
            source_user = db.scalar(select(AIMessage).where(
                AIMessage.conversation_id == conversation_id, AIMessage.role == 'user'
            ).order_by(AIMessage.id.desc()).limit(1))
            if source_user is not None:
                brainstorm_mode = session_store.metadata(source_user.display_json).get('brainstorm_mode', False) is True

        queue: asyncio.Queue = asyncio.Queue()
        agent = self._build_agent(plan_mode=plan_mode, conversation_id=conversation_id, emit=queue, brainstorm_mode=brainstorm_mode)
        # per-run 注入：事件外发通道/子代理模型工厂/会话 id 全部进 deps（并发 run 不串线）
        capture_key = run_id
        if user_text is None:
            from sqlalchemy import select
            latest_user = db.scalar(select(AIMessage).where(
                AIMessage.conversation_id == conversation_id, AIMessage.role == "user"
            ).order_by(AIMessage.id.desc()).limit(1))
            if latest_user is not None:
                capture_key = json.loads(latest_user.display_json).get("capture_key", run_id)
        deps = AgentDeps(db=db, emit=queue, capture_key=capture_key, storage_root=self.storage_root,
                         sub_model_factory=self.sub_model_factory or (lambda: self.model),
                         conversation_id=conversation_id, model_config=self.model_config)
        deps.run_id = run_id

        yield stage("connecting")

        collected: list[dict] = []
        final_messages = None
        run_output = None
        usage = None
        done_reason, run_error = "model_done", None
        attempt_input: Any = model_input
        saw_plan_card = False
        step_count = 0
        plan_retry_pending = plan_mode   # 计划模式受控重试：至多追加一轮
        current_run = None
        last_checkpoint = time.monotonic()
        from pydantic_ai.messages import TextPart
        node_text = ''
        baseline_responses = set()

        def snapshot():
            messages = list(current_run.all_messages())
            committed = ''.join(p.content for m in messages if id(m) not in baseline_responses
                                for p in m.parts if isinstance(p, TextPart))
            return session_store.with_partial_response(messages, node_text, committed_text=committed)
        while True:
            try:
                async with agent.iter(attempt_input, deps=deps, message_history=history,
                                      deferred_tool_results=deferred_results,
                                      usage_limits=self._limits(),
                                      cancellation_token=cancel_token) as run:
                    current_run = run
                    async for node in run:
                        if Agent.is_model_request_node(node):
                            node_text = ''
                            baseline_responses = {id(m) for m in run.all_messages()}
                            step_count += 1   # run trace：模型请求步数跨轮累加
                            yield stage("waiting_first_token")
                            async for evt, extra in _node_stream_events(node, run.ctx, queue):
                                if extra is not None:
                                    saw_plan_card |= extra.get("type") == "plan_card"
                                    yield extra
                                    continue
                                for out in _translate(evt):
                                    if out['type'] == 'text_delta':
                                        node_text += out.get('delta', '')
                                    yield out
                                    collected.append(out)
                                if time.monotonic() - last_checkpoint >= 1:
                                    session_store.checkpoint(db, run_row, assistant_row, snapshot(), collected)
                                    last_checkpoint = time.monotonic()
                        elif Agent.is_call_tools_node(node):
                            yield stage("executing_tools")
                            async for evt, extra in _node_stream_events(node, run.ctx, queue):
                                if extra is not None:
                                    saw_plan_card |= extra.get("type") == "plan_card"
                                    yield extra
                                    continue
                                for out in _translate(evt):
                                    yield out
                                    collected.append(out)
                            node_text = ''
                        session_store.checkpoint(db, run_row, assistant_row, run.all_messages(), collected)
                    if run.result is not None:  # 正常收敛：提取输出与 usage（跨轮累加）
                        final_messages = run.result.all_messages()
                        run_output = run.result.output
                        usage = run.result.usage if usage is None else usage + run.result.usage
                if (plan_retry_pending and final_messages is not None
                        and not isinstance(run_output, DeferredToolRequests)
                        and not saw_plan_card):
                    # 计划模式受控重试：execution 正常结束但既无 plan_card 也无审批/错误，
                    # 以追加指令再驱动一轮；仅一次，防止模型继续文本收尾时无限循环。
                    plan_retry_pending = False
                    history = final_messages
                    attempt_input = prompts.PLAN_RETRY_INSTRUCTION
                    yield stage("preparing")
                    continue
                break
            except Exception as exc:  # provider/预算/取消/视觉降级统一收口
                from pydantic_ai.exceptions import RunCancelled, UsageLimitExceeded
                if current_run is not None:
                    final_messages = snapshot()
                if isinstance(exc, RunCancelled):
                    # 取消：exc.all_messages 保留部分输出，落库后以 interrupted 收尾
                    done_reason = "cancelled"
                    usage = getattr(exc, "usage", None)
                    break
                if isinstance(exc, UsageLimitExceeded):
                    done_reason = "budget_exceeded"
                    break
                done_reason, run_error = "failed", str(exc)[:500]
                if image_parts and _looks_like_vision_error(exc):
                    run_error = ('模型接口拒绝媒体输入。请核对「设置 → AI 模型」中的输入能力与接口协议；'
                                 '纯文字模型可在「联网与视觉」中配置视觉 MCP。附件尚未读取。')
                yield _sse_event(ev.RunError, run_id=run_id,
                                 message=run_error, retryable=True)
                break

        yield stage("finalizing")
        for extra in _drain(queue):     # 收尾兜底：工具末尾投递的内部事件不丢
            yield extra

        # 2) 审批暂停判定
        if isinstance(run_output, DeferredToolRequests) and (run_output.approvals or run_output.calls):
            from zhishi.domain.models import AIPendingAction
            waiting = 'awaiting_input' if run_output.calls else 'awaiting_approval'
            yield stage(waiting)
            for call in run_output.calls:
                from zhishi.domain.models import AIUserInput
                from zhishi.agent.user_input import to_read
                question = AIUserInput(conversation_id=conversation_id, run_id=run_id,
                    tool_call_id=call.tool_call_id,
                    questions_json=json.dumps(_args_dict(call.args)['questions'], ensure_ascii=False))
                db.add(question)
                db.commit()
                db.refresh(question)
                yield _sse_event(ev.UserInputRequested, request=to_read(question).model_dump())
            for call in run_output.approvals:
                from zhishi.agent.tool_discovery import actual_tool_call
                call = actual_tool_call(call)
                args = _args_dict(call.args)
                from zhishi.agent.approval_preview import build as approval_preview
                preview = approval_preview(db, call.tool_name, args)
                action = AIPendingAction(
                    conversation_id=conversation_id, run_id=run_id,
                    tool_call_id=call.tool_call_id, tool_name=call.tool_name,
                    args_json=json.dumps(args, ensure_ascii=False, default=str),
                    preview=preview, status="pending")
                db.add(action); db.commit(); db.refresh(action)
                yield _sse_event(ev.ToolApprovalRequested, action_id=action.id,
                                 tool=call.tool_name, args=args, preview=preview,
                                 grant_available=call.tool_name not in IRREVOCABLE_TOOLS)
            run_row.status = waiting
            done_reason = waiting
        else:
            run_row.status = "interrupted" if done_reason == "cancelled" else (
                done_reason if done_reason != "model_done" else "completed")

        # 3) 消息落库（history 双存储）；恢复轮不新增用户消息
        if done_reason in ('failed', 'cancelled', 'budget_exceeded'):
            from pydantic_ai.messages import ModelMessagesTypeAdapter
            final_messages = final_messages or ModelMessagesTypeAdapter.validate_json(assistant_row.history_json)
            final_messages = session_store.close_unresolved_calls(final_messages,
                session_store.recorded_results(db, run_id))
        session_store.checkpoint(db, run_row, assistant_row, final_messages, collected,
            status=run_row.status, error=run_error)
        run_row.done_reason = done_reason
        run_row.steps = step_count   # run trace：模型请求步数（含重试轮，正常累加）
        run_row.elapsed_ms = int((time.monotonic() - t0) * 1000)
        run_row.usage_json = json.dumps(_usage_dict(usage))
        db.commit()

        usage_dict = _usage_dict(usage)
        if usage_dict["total_tokens"] > 0:
            # 用量记录：TestModel 等无 token 计数时不落（provider/model 取配置）
            from zhishi.domain.models import AIUsageLog
            meta = usage_meta or {}
            db.add(AIUsageLog(
                config_id=meta.get("config_id"), run_id=run_id, kind="chat",
                provider=meta.get("provider") or "", model=meta.get("model") or str(self.model),
                prompt_tokens=usage_dict["input_tokens"],
                completion_tokens=usage_dict["output_tokens"],
                total_tokens=usage_dict["total_tokens"]))
            db.commit()
            yield _sse_event(ev.UsageUpdated, tokens_in=usage_dict["input_tokens"],
                             tokens_out=usage_dict["output_tokens"],
                             cache_read_tokens=usage_dict["cache_read_tokens"],
                             cache_write_tokens=usage_dict["cache_write_tokens"],
                             cost_estimate=0.0, model=meta.get("model") or str(self.model))

        yield _sse_event(ev.RunCompleted, run_id=run_id, usage=usage_dict,
                         elapsed_ms=run_row.elapsed_ms, done_reason=done_reason)
        yield _sse_event(ev.Done, run_id=run_id)

    def _limits(self):
        from pydantic_ai.usage import UsageLimits
        return UsageLimits(request_limit=30, tool_calls_limit=40)


def _safe_rollback(db: Session) -> None:
    """失败会话必须回滚：flush 中途异常后 Session 滞留「待回滚」态，后续任何
    commit 都会连环崩（Method 'commit' can't be called here）。回滚自身失败
    不掩盖原异常；已关闭/无事务的 Session 回滚为无害空操作。"""
    try:
        db.rollback()
    except Exception:
        pass


def _translate(evt) -> list[dict]:
    """PydanticAI 流事件 → 契约事件（映射表，runtime 核心）。
    注意 PartStartEvent：parts manager 对新文本/思考 part 的首个分片以
    PartStartEvent(part=TextPart(首片内容)) 发出（而非 PartDeltaEvent），
    不处理它则每次流式回复的开头一段会丢（FunctionModel 短回复几乎全丢）。"""
    out: list[dict] = []
    from pydantic_ai.messages import (FunctionToolCallEvent, FunctionToolResultEvent,
                                      PartDeltaEvent, PartStartEvent, TextPart,
                                      TextPartDelta, ThinkingPart, ThinkingPartDelta,
                                      ToolCallPartDelta)
    if isinstance(evt, PartStartEvent):
        if isinstance(evt.part, TextPart) and evt.part.content:
            out.append(_sse_event(ev.TextDelta, delta=evt.part.content))
        elif isinstance(evt.part, ThinkingPart) and evt.part.content:
            out.append(_sse_event(ev.ReasoningDelta, delta=evt.part.content))
    elif isinstance(evt, PartDeltaEvent):
        if isinstance(evt.delta, TextPartDelta) and evt.delta.content_delta:
            out.append(_sse_event(ev.TextDelta, delta=evt.delta.content_delta))
        elif isinstance(evt.delta, ThinkingPartDelta) and evt.delta.content_delta:
            out.append(_sse_event(ev.ReasoningDelta, delta=evt.delta.content_delta))
        elif isinstance(evt.delta, ToolCallPartDelta):
            frag = getattr(evt.delta, "args_delta", None)
            if frag:
                out.append(_sse_event(ev.ToolCallArgsDelta, call_id=evt.delta.tool_call_id or "",
                                      args_delta=str(frag)))
    elif isinstance(evt, FunctionToolCallEvent):
        from zhishi.agent.tool_discovery import actual_tool_call
        call = actual_tool_call(evt.part)
        out.append(_sse_event(ev.ToolCallStarted, call_id=evt.part.tool_call_id,
                              tool=call.tool_name,
                              args_preview=str(_args_dict(call.args))[:200]))
    elif isinstance(evt, FunctionToolResultEvent):
        result = getattr(evt.part, "content", "")
        from pydantic_ai.messages import RetryPromptPart
        ok = not isinstance(evt.part, RetryPromptPart)
        try:
            parsed = json.loads(result) if isinstance(result, str) else result
            if isinstance(parsed, dict) and parsed.get("ok") is False:
                ok = False
        except (TypeError, ValueError):
            pass
        out.append(_sse_event(ev.ToolCallResult, call_id=evt.part.tool_call_id, ok=ok,
                              result_preview=str(result)[:400], duration_ms=0))
    return out


def _drain(queue) -> list[dict]:
    """非阻塞取出工具执行期间投递的内部事件（子代理/plan_card），穿透进主流。"""
    out = []
    while not queue.empty():
        out.append(queue.get_nowait())
    return out


def _looks_like_vision_error(exc: Exception) -> bool:
    """异常文本是否为「模型/网关不支持图片输入」类错误（降级判据，宽匹配）。"""
    text = str(exc).lower()
    return any(k in text for k in ("vision", "image", "multimodal", "multi-modal",
                                   "图片", "多模态", "视觉"))


class _MCPGatedToolset(MCPToolset):
    """MCP 工具集 + 权限门（继承 pydantic-ai MCPToolset）。
    - 工具名映射 mcp__{server_id}__{原名}（命名空间隔离，多服务器不撞名）；
    - 权限门与内置工具同路径：classify 判 confirm 时在 call 包装里 raise
      ApprovalRequired（deferred 恢复轮 ctx.tool_call_approved 直接放行）；
    - classify 的 mcp 分支需要 server 行与 readOnlyHint，均由本类持有传入；
    - 工具清单复用 mcp_client 模块级 60s TTL 缓存：toolset 每 run
      新建，框架实例级 cache_tools 随 __aexit__ 失效、且框架每 run 都 __aenter__
      toolset（真实连接）——本类改为查模块级缓存：命中不连接，未命中真连后回写；
      工具调用不缓存（必要行为），无活动会话时按需真连、用完即断。失效钩子
      （PUT/enable/DELETE → mcp_client.invalidate）天然覆盖 run 装配路径。"""

    def __init__(self, client, *, server_id: int, server_row=None, unavailable=None, readonly_only=False, **kwargs):
        super().__init__(client, **kwargs)
        self._server_id = server_id
        self._prefix = f"mcp__{server_id}__"
        self._read_only: dict[str, bool] = {}
        self._server_row = server_row
        self._unavailable = unavailable if unavailable is not None else {}
        self._readonly_only = readonly_only
        self._listing_failed = False
        self._connection_lock = asyncio.Lock()
        self._call_results = {}

    def _tools_cache_hit(self) -> list | None:
        """mcp_client 模块级 TTL 缓存命中返回记录列表，未命中/过期返回 None。"""
        from time import monotonic
        from zhishi.adapters import mcp_client
        if self._server_id is None:
            return None
        hit = mcp_client._tools_cache.get(self._server_id)
        if hit is not None and monotonic() < hit[0]:
            return hit[1]
        return None

    async def __aenter__(self):
        # Each network operation owns its connection. Merely enabling an offline
        # server must not prevent the agent from entering other toolsets.
        return self

    async def __aexit__(self, *args):
        return None

    async def _list_tools_connected(self) -> list:
        """真连列取：本 toolset 尚无活动会话（缓存命中短路进入）时按需连、用完即断。"""
        async with self._connection_lock:
            await super().__aenter__()
            try:
                return await super().list_tools()
            finally:
                await super().__aexit__(None, None, None)

    async def list_tools(self) -> list:
        """跨 run 工具清单缓存：先查 mcp_client._tools_cache（键 server_id，60s TTL
        与 /tools 端点同源），命中还原 Tool 对象直接返回；未命中 super 真连后
        以记录格式回写缓存。写回前校验 mcp_client 缓存世代（与 list_tools 端点同一规则）：网络等待期间发生过 invalidate 则丢弃本次
        结果，防止旧服务器工具（含 readOnlyHint）回填污染。"""
        from time import monotonic
        from zhishi.adapters import mcp_client
        gen = mcp_client._cache_generation                # 进入时捕获
        hit = self._tools_cache_hit()
        if hit is not None:
            return [mcp_client.tool_from_record(rec) for rec in hit]
        tools = await self._list_tools_connected()
        if self._server_id is not None and gen == mcp_client._cache_generation:
            mcp_client._tools_cache[self._server_id] = (
                monotonic() + mcp_client.TOOLS_CACHE_TTL_SECONDS,
                [mcp_client.tool_to_record(t) for t in tools])
        return tools

    async def get_tools(self, ctx):
        import dataclasses
        if self._listing_failed:
            return {}
        try:
            tools = await super().get_tools(ctx)
        except Exception as exc:
            self._listing_failed = True
            self._record_failure(exc)
            return {}
        renamed: dict = {}
        for name, t in tools.items():
            ann = (t.tool_def.metadata or {}).get("annotations") or {}
            self._read_only[name] = bool(ann.get("readOnlyHint"))
            if self._readonly_only and not self._read_only[name]:
                continue
            new_name = self._prefix + name
            # 与 pydantic-ai RenamedToolset 同款写法：dict 键与 tool_def.name 一并改名
            renamed[new_name] = dataclasses.replace(
                t, tool_def=dataclasses.replace(t.tool_def, name=new_name))
        return renamed

    async def call_tool(self, name, tool_args, ctx, tool):
        if not ctx.tool_call_approved:
            from zhishi.domain.models import MCPServer
            original = self._original_name(name)
            server = ctx.deps.db.get(MCPServer, self._server_id)
            verdict = classify(ctx.deps.db, name, tool_args,
                               readonly_hint=self._read_only.get(original),
                               mcp_server=server)
            if verdict == "confirm":
                from pydantic_ai.exceptions import ApprovalRequired
                raise ApprovalRequired(metadata={"tool": name, "args": tool_args})
            if verdict == "deny":
                return json.dumps({"ok": False, "error": "工具不可用"}, ensure_ascii=False)
        original = self._original_name(name)
        tracker = getattr(ctx.deps, 'failure_tracker', None)
        blocked = tracker.blocked(name, tool_args) if tracker else None
        if blocked:
            return json.dumps(blocked, ensure_ascii=False)
        try:
            async with self._connection_lock:
                call_id = getattr(ctx, 'tool_call_id', None)
                call_key = (getattr(ctx.deps, 'run_id', None) or getattr(ctx, 'run_id', None), call_id)
                signature = FailureTracker.key(name, tool_args)
                if call_id and call_key in self._call_results:
                    previous_signature, previous_result = self._call_results[call_key]
                    if previous_signature != signature:
                        return json.dumps({'ok':False, 'code':'call_id_conflict', 'retryable':False,
                            'error':'同一工具调用 ID 不能对应不同参数；请核对已有调用结果。'}, ensure_ascii=False)
                    return previous_result
                await super().__aenter__()
                try:
                    result = await super().call_tool(original, tool_args, ctx, tool)
                finally:
                    await super().__aexit__(None, None, None)
                if call_id:
                    self._call_results[call_key] = (signature, result)
        except Exception as exc:
            detail = self._record_failure(exc)
            readonly = self._read_only.get(original, False)
            result = {'ok':False, 'code':'external_tool_failed', 'error':detail['error'],
                      'retryable':readonly, 'write_status':'not_applicable' if readonly else 'unknown',
                      'next_step':'只读查询可重试一次或使用已配置的其他来源；外部写入结果不明，先核对远端状态，不重复提交。'}
        if tracker:
            tracker.record(name, tool_args, result)
        return json.dumps(result, ensure_ascii=False) if isinstance(result, dict) and result.get('ok') is False else result

    def _record_failure(self, exc):
        from zhishi.adapters.mcp_client import sanitize
        error = sanitize(str(exc), self._server_row) if self._server_row is not None else '外部工具连接或执行失败'
        detail = {'server_id':self._server_id, 'error':error,
                  'next_step':'本轮继续使用可用工具；需要此服务时请检查 MCP 设置后重试。'}
        self._unavailable[self._server_id] = detail
        return detail

    def _original_name(self, namespaced: str) -> str:
        if namespaced.startswith(self._prefix):
            return namespaced[len(self._prefix):]
        return namespaced


def _wrap_for_subagent(spec, db: Session, context=None, tracker=None, observer=None):
    """子代理只读工具包装：_wrap_tool 去权限门版（子代理只挂 readonly，天然无审批）。
    schema 同样从去掉 db 的函数签名与注解推断。异常同主工具语义：回滚后以
    ok=False 错误文本返回（子代理工具失败不崩子 run）。"""
    from typing import get_type_hints
    hints = get_type_hints(spec.fn, include_extras=True)
    orig = inspect.signature(spec.fn)
    params = [p.replace(annotation=hints.get(name, p.annotation))
              for name, p in orig.parameters.items() if name not in ("db", "ctx")]

    async def _fn(**kw):
        blocked = tracker.blocked(spec.name, kw) if tracker else None
        if blocked:
            return json.dumps(blocked, ensure_ascii=False)
        def invoke():
            with Session(bind=db.get_bind(), expire_on_commit=False) as tool_db:
                return spec.fn(tool_db, **({'ctx':context} if 'ctx' in orig.parameters else {}), **kw)
        try:
            if inspect.iscoroutinefunction(spec.fn):
                with Session(bind=db.get_bind(), expire_on_commit=False) as tool_db:
                    raw = await spec.fn(tool_db, **({'ctx':context} if 'ctx' in orig.parameters else {}), **kw)
            else:
                worker = asyncio.create_task(asyncio.to_thread(invoke))
                try:
                    raw = await asyncio.shield(worker)
                except asyncio.CancelledError:
                    await asyncio.gather(worker, return_exceptions=True)
                    raise
        except Exception as exc:
            raw = failure_result(exc, tool=spec.name, arguments=kw, readonly=True)
        if tracker:
            tracker.record(spec.name, kw, raw)
        if observer:
            observer(spec.name, kw, raw)
        return raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False, default=str)

    _fn.__name__ = spec.name
    _fn.__signature__ = Signature(params)
    _fn.__annotations__ = {p.name: p.annotation for p in params}
    return _fn


def _usage_dict(usage) -> dict:
    inp = getattr(usage, "input_tokens", 0) or 0
    outp = getattr(usage, "output_tokens", 0) or 0
    return {"input_tokens": inp, "output_tokens": outp, "total_tokens": inp + outp,
            "cache_read_tokens": getattr(usage, "cache_read_tokens", 0) or 0,
            "cache_write_tokens": getattr(usage, "cache_write_tokens", 0) or 0,
            "cache_hit_rate": (getattr(usage, "cache_read_tokens", 0) or 0) / inp if inp else None,
            "requests": getattr(usage, "requests", 0) or 0}
