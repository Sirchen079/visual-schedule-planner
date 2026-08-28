from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, File as UploadFileParam, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.models import AIConfig, AIConversation, AIMessage, AIPendingAction
from app.schemas import (
    AIActionExecute,
    AIChatAttachmentResponse,
    AIChatRequest,
    AIChatResponse,
    AIChatResumeRequest,
    AIConversationDetailResponse,
    AIConversationMessageResponse,
    AIConversationRename,
    AIConversationSummaryResponse,
    AIConfigCreate,
    AIConfigResponse,
    AIConfigUpdate,
    AIModelsRequest,
    AIModelsResponse,
    AIPendingActionResponse,
    AIPlanApproveRequest,
    AIPlanRejectRequest,
    AIReportGenerateRequest,
    AIReportResponse,
    AISkillCreate,
    AISkillImport,
    AISkillResponse,
    AISkillUpdate,
    AIToolGrantCreate,
    AIToolGrantResponse,
)
from app.services import (
    ai_action_service,
    ai_attachment_service,
    ai_client,
    ai_compaction_service,
    ai_config_service,
    ai_grant_service,
    ai_harness_service,
    ai_prompt_service,
    ai_report_service,
    ai_skill_service,
    ai_tool_service,
    ai_usage_service,
    app_setting_service,
    autopilot_service,
    mcp_service,
    tool_registry,
)

router = APIRouter(prefix="/ai", tags=["ai"])
logger = logging.getLogger("zhishi.ai")
# 步数预算：默认读 settings.agent_max_steps（默认 15，env APP_AGENT_MAX_STERS 可覆盖）。
# 阶段 B2：从硬编码 5 升级为可配置预算。各 agent 循环接收 max_steps 参数，可被请求级覆盖。
from app.config import settings as _app_settings  # noqa: E402

AGENT_MAX_STEPS = max(3, min(30, int(getattr(_app_settings, "agent_max_steps", 15) or 15)))
AGENT_OBSERVATION_CHAR_LIMIT = 12000
AGENT_TOOL_RETRY_LIMIT = 2

# 阶段 5：运行中的 agent run 注册表（桌面单进程可行）。
# key=run_id，value=asyncio.Event；set 后对应流在下一个步边界停止并发 cancelled done。
_active_runs: dict[str, asyncio.Event] = {}


def _register_run(run_id: str) -> asyncio.Event:
    """注册一次 agent run，返回其取消事件。run 结束时由 _release_run 清理。"""
    event = asyncio.Event()
    _active_runs[run_id] = event
    return event


def _release_run(run_id: str) -> None:
    """run 结束（正常/失败/取消）后从注册表移除。"""
    _active_runs.pop(run_id, None)


@dataclass
class AgentRunResult:
    final_text: str
    final_plan: dict
    tool_results: list[dict]
    run_summary: dict
    reached_limit: bool = False
    stopped_for_repeat: bool = False
    stop_message: str = ""
    # 仅在 native 路径因 pending_confirmation 暂停时填充：携带续跑所需的尾部上下文。
    # /ai/chat 端点会在落库时把 pending_action_ids 回填进此结构，再写入 assistant 消息 meta.resume。
    resume_checkpoint: dict | None = None
    # 本次 run 真实发生过的 tool 交互序列（每步 assistant(tool_calls 含 id) + tool 消息(含 tool_call_id)），
    # 持久化到 meta.tool_chain 供跨轮回放，解决正常完成轮不回放 tool 链导致的上下文失忆。
    tool_chain: list[dict] | None = None
    # 本次 run 各 provider 轮次的累计 token 用量（阶段 2）：用于 done 帧 + AIMessage.meta.usage。
    # provider 不回 usage 时三键均为 0；前端对全 0 不展示。
    usage: dict | None = None
    # 阶段 3：本次 run 累计的推理/思维链文本（provider 已给出的，非主动请求）。空串则不展示。
    reasoning: str = ""
    # 阶段 C1：plan 模式下 agent 调用 propose_plan 产出的计划卡片（None=未提交计划）。
    plan_card: dict | None = None
    # 阶段 C2：本次 run 最后一次工作清单快照（agent 调用 update_work_plan 产出）。
    work_plan: list[dict] | None = None


def sanitize_provider_error(exc: Exception) -> str:
    text = str(exc)
    text = re.sub(
        r"(authorization\s*[:=]\s*(?:bearer\s+)?)[^\s,;\"'}]+",
        r"\1[已隐藏]",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"(x-api-key\s*[:=]\s*)[^\s,;\"'}]+",
        r"\1[已隐藏]",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"((?:api[_-]?key|token|secret|password)[\"']?\s*[:=]\s*[\"']?)[^\"',\s}]+",
        r"\1[已隐藏]",
        text,
        flags=re.I,
    )
    text = re.sub(r"\b(sk|ak|pk)-[A-Za-z0-9_-]{8,}\b", r"\1-[已隐藏]", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:300] if text else exc.__class__.__name__


def provider_failure_detail(operation: str, exc: Exception) -> str:
    return f"{operation}失败: {sanitize_provider_error(exc)}"


def tool_signature(item: dict) -> str:
    return json.dumps(
        {"name": item.get("name", ""), "args": dict(item.get("args", {}))},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )


def successful_tool_signatures(tool_results: list[dict]) -> set[str]:
    signatures = set()
    for item in tool_results:
        result = item.get("result")
        if isinstance(result, dict) and result.get("ok") is True and not result.get("skipped"):
            signatures.add(
                json.dumps(
                    {"name": item.get("tool", ""), "args": item.get("args", {})},
                    sort_keys=True,
                    ensure_ascii=False,
                    default=str,
                )
            )
    return signatures


def compact_attachments_for_followup(messages: list[dict]) -> list[dict]:
    compacted = []
    for message in messages:
        attachments = message.get("attachments") or []
        if not attachments:
            compacted.append(message)
            continue
        lines = [
            (
                f"- {item.get('filename')} | 附件 ID:{item.get('id')} | "
                f"类型:{item.get('mime_type') or '未知'} | 大小:{item.get('size') or 0} bytes"
            )
            for item in attachments
        ]
        compacted.append(
            {
                "role": message.get("role", "user"),
                "content": (
                    f"{message.get('content', '')}\n\n"
                    "[附件已在上一轮完整发送，本轮仅保留引用]\n"
                    + "\n".join(lines)
                ).strip(),
            }
        )
    return compacted


def build_chat_provider_request(
    db: Session,
    config: AIConfig,
    messages: list[dict],
    *,
    mode: str = "chat",
) -> ai_client.ProviderRequest:
    # 阶段 7：plan 模式已硬删，工具调用方式恒为 native（列保留但忽略，免迁移）。
    system_prompt = (
        ai_prompt_service.build_system_prompt(db, config)
        + "\n\n"
        + ai_prompt_service.build_local_context(db)
    )
    # 阶段 C1：plan 模式追加专属系统提示段（只读调研 + 必须 propose_plan 收尾）
    if mode == "plan":
        system_prompt = system_prompt + "\n\n" + _PLAN_MODE_SYSTEM_SUFFIX
    tools = _assemble_native_tools(db, mode=mode)
    return ai_client.build_provider_request(
        provider=config.provider,
        model=config.model,
        api_key=config.api_key,
        messages=messages,
        system_prompt=system_prompt,
        extra_headers=ai_config_service.headers_from_json(config.extra_headers),
        base_url=config.base_url,
        full_url=config.full_url,
        proxy_url=config.proxy_url,
        native_web_search_enabled=bool(
            config.native_web_search_enabled or config.search_enhancement_enabled
        ),
        native_web_search_options=ai_config_service.options_from_json(
            config.native_web_search_options
        ),
        tools=tools,
    )


# 阶段 C1：plan 模式专属系统提示——只读调研 + 必须 propose_plan 收尾，禁止任何写操作
_PLAN_MODE_SYSTEM_SUFFIX = (
    "【当前为计划模式】\n"
    "你只能使用只读工具进行调研，禁止执行任何写操作（创建/修改/删除）。\n"
    "调研充分后，你必须调用 propose_plan 工具提交一份结构化计划作为收尾，不要直接给最终答复。\n"
    "计划应包含：标题、分步动作（每步注明动作类型、目标工具、参数预览、理由）、影响的日期范围。\n"
    "用户会审阅计划并决定批准/拒绝/编辑；批准后才会切回对话模式执行。"
)


def _assemble_native_tools(db: Session, *, mode: str = "chat") -> list[dict]:
    """原生模式工具装配：内置工具（registry）+ MCP 工具（namespaced），provider 无关。

    阶段 C1：plan 模式下只暴露只读工具 + propose_plan，写类工具不暴露给模型。
    """
    if mode == "plan":
        readonly = tool_registry.readonly_names()
        tools = [
            t for t in tool_registry.provider_tools(db)
            if t.get("name") in readonly or t.get("name") == "propose_plan"
        ]
        return tools
    tools = list(tool_registry.provider_tools(db))
    for entry in mcp_service.list_enabled_tools_for_agent(db):
        tools.append(
            {
                "name": entry["namespaced"],
                "description": entry["description"] or "（MCP 服务器未提供描述）",
                "input_schema": entry["input_schema"] or {"type": "object", "properties": {}},
            }
        )
    return tools


async def run_agent_loop(
    db: Session,
    config: AIConfig,
    messages: list[dict],
    user_text: str,
    conversation_id: int | None = None,
    max_steps: int | None = None,
    mode: str = "chat",
) -> AgentRunResult:
    # 阶段 7：plan 模式已硬删，工具调用方式恒为 native（AIConfig.tool_calling_mode 列保留但忽略）。
    # 阶段 B2：max_steps 透传至 native 循环（None 时回落 settings.agent_max_steps）。
    # 阶段 C1：mode 透传（chat/plan），plan 模式过滤工具 + 专属系统提示。
    return await _run_native_agent_loop(
        db, config, messages, user_text, conversation_id, max_steps=max_steps, mode=mode
    )


async def _run_native_agent_loop(
    db: Session,
    config: AIConfig,
    messages: list[dict],
    user_text: str,
    conversation_id: int | None = None,
    max_steps: int | None = None,
    mode: str = "chat",
) -> AgentRunResult:
    run_id = uuid4().hex
    started_at = datetime.now()
    # 阶段 B2：步数预算可配置（settings / 请求级覆盖），夹在 [3, 30]
    step_budget = max(3, min(30, int(max_steps or AGENT_MAX_STEPS)))
    working_messages = list(messages)
    # 阶段 C1/C2：捕获 propose_plan / update_work_plan 产出
    captured_plan_card: dict | None = None
    captured_work_plan: list[dict] | None = None
    tool_results: list[dict] = []
    steps: list[dict] = []
    dangerous_actions: list[dict] = []
    final_text = ""
    final_plan = {"reply": "", "tools": [], "dangerous_actions": []}
    reached_limit = False
    stopped_for_repeat = False
    done_reason = "unknown"
    stop_message = ""
    resume_checkpoint: dict | None = None
    tool_chain: list[dict] = []
    # 阶段 2：非流式路径同样累计 usage，保持降级通道体验一致
    run_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": 0}
    # 阶段 3：累计各轮 reasoning（非流式路径同样从 turn 提取）
    reasoning_parts: list[str] = []

    for step in range(1, step_budget + 1):
        # 阶段 B2 优雅收尾：到达预算的倒数第 2 步时，注入系统提示让模型主动收尾总结，
        # 把「撞墙硬停」变成「有准备的收尾」。
        if step == step_budget - 1 and step_budget >= 4:
            working_messages = [
                *compact_attachments_for_followup(working_messages),
                {
                    "role": "user",
                    "content": (
                        f"⚠️ 你还剩 2 步工作预算。请在下一步内收尾："
                        "完成当前最关键的写操作，并用一段话向用户总结「已完成 / 未完成 / 建议下一步」"
                        "，不要再发起新的多步调研。"
                    ),
                },
            ]
        req = build_chat_provider_request(db, config, working_messages, mode=mode)
        try:
            raw = await ai_client.call_provider(req)
            step_usage = ai_usage_service.log_usage(
                db, config=config, kind="chat", payload=raw,
                conversation_id=conversation_id,
            )
            if step_usage:
                run_usage["prompt_tokens"] += step_usage.get("prompt_tokens", 0)
                run_usage["completion_tokens"] += step_usage.get("completion_tokens", 0)
                run_usage["total_tokens"] += step_usage.get("total_tokens", 0)
            run_usage["calls"] += 1
        except Exception as exc:
            provider_error = _native_provider_error_with_hint(config, exc)
            if step == 1:
                raise Exception(provider_error) from exc
            tool_results.append(
                {
                    "tool": "ai_agent",
                    "args": {"step": step},
                    "result": {"ok": False, "error": provider_error},
                }
            )
            done_reason = "provider_error"
            stop_message = provider_error
            break

        turn = ai_client.extract_assistant_turn(config.provider, raw)
        final_text = turn["text"]
        tool_calls = turn.get("tool_calls") or []
        # 阶段 3：累积非流式 turn 提取的 reasoning
        if turn.get("reasoning") and getattr(config, "show_reasoning", True):
            reasoning_parts.append(turn["reasoning"])

        # 硬化：输出被截断（max_tokens / length）→ 回喂缩短指令，避免静默死循环
        if _is_truncated(config.provider, turn.get("stop_reason")):
            steps.append(
                {
                    "step": step,
                    "reply": final_text,
                    "plan": {},
                    "tools": [],
                    "dangerous_actions": [],
                    "observations": [],
                    "done": False,
                    "truncated": True,
                }
            )
            done_reason = "max_tokens"
            working_messages = [
                *compact_attachments_for_followup(working_messages),
                {"role": "assistant", "content": final_text},
                {
                    "role": "user",
                    "content": "你的上一条输出被截断（达到 max_tokens），请缩短单次回复后继续。",
                },
            ]
            if step >= step_budget:
                reached_limit = True
                done_reason = "max_steps"
                break
            continue

        if not tool_calls:
            steps.append(
                {
                    "step": step,
                    "reply": final_text,
                    "plan": {},
                    "tools": [],
                    "dangerous_actions": [],
                    "observations": [],
                    "done": True,
                }
            )
            done_reason = "no_tools"
            break

        skip_signatures = successful_tool_signatures(tool_results)
        # 预分类：本轮是否存在需确认调用。若有，按 plan 路径不变量——本轮不执行任何
        # safe 工具，全部转待确认，避免「同轮回 safe 已执行 + confirm 被用户拒绝」的半成品副作用。
        classifications = [_classify_native_call(db, call) for call in tool_calls]
        has_pending = any(cls == "dangerous" for cls in classifications)

        step_results: list[dict] = []
        step_tool_messages: list[dict] = []
        assistant_tool_calls = []
        for call, cls in zip(tool_calls, classifications):
            if has_pending and cls != "dangerous":
                # 本轮回含需确认操作：safe / 畸形 / 未知工具一律暂缓执行，回 pending 结果
                name = str(call.get("name", ""))
                call_id = str(call.get("id", ""))
                paused_args = call.get("arguments") or {}
                outcome = _pack_native_outcome(
                    name,
                    call_id,
                    paused_args,
                    {
                        "ok": False,
                        "pending": True,
                        "error": "本轮回包含需确认操作，安全工具暂缓执行，待用户确认后继续",
                    },
                )
            else:
                outcome = _dispatch_native_tool_call(db, call, skip_signatures, final_text)
            step_results.append(outcome["tool_result"])
            step_tool_messages.append(outcome["tool_message"])
            assistant_tool_calls.append(
                {
                    "id": str(call.get("id", "")),
                    "name": str(call.get("name", "")),
                    "arguments": call.get("arguments") or {},
                }
            )
            if outcome["dangerous_action"] is not None:
                dangerous_actions.append(outcome["dangerous_action"])
            # 阶段 C1/C2：捕获 propose_plan / update_work_plan 产出
            _res = outcome["tool_result"].get("result") or {}
            if isinstance(_res, dict) and _res.get("plan_card"):
                captured_plan_card = _res["plan_card"]
            if isinstance(_res, dict) and _res.get("work_plan"):
                captured_work_plan = _res["work_plan"]

        tool_results.extend(step_results)
        # 记录本步 tool 交互（含 call_id）到 tool_chain，供跨轮回放
        tool_chain.append(
            {"role": "assistant", "content": final_text, "tool_calls": list(assistant_tool_calls)}
        )
        tool_chain.extend(step_tool_messages)
        steps.append(
            {
                "step": step,
                "reply": final_text,
                "plan": {},
                "tools": [{"name": c["name"], "args": c["arguments"]} for c in assistant_tool_calls],
                "dangerous_actions": list(dangerous_actions),
                "observations": ai_harness_service.step_observations(step_results),
                "done": False,
            }
        )

        # 有任何 pending 产生 → 本轮结束
        if dangerous_actions:
            final_plan = {
                "reply": final_text,
                "tools": [],
                "dangerous_actions": list(dangerous_actions),
            }
            done_reason = "pending_confirmation"
            # 落 checkpoint 供 /ai/chat/resume 续跑：本轮 assistant tool_calls + 已生成 tool 消息
            # （含 pending 占位）+ 被暂缓的 safe 工具（has_pending 时未执行，待续跑补执行）。
            # has_pending 时非 dangerous 调用都走了 pending 占位分支，可安全重分发。
            paused_calls = []
            if has_pending:
                for call, cls in zip(tool_calls, classifications):
                    if cls != "dangerous":
                        paused_calls.append(
                            {
                                "id": str(call.get("id", "")),
                                "name": str(call.get("name", "")),
                                "arguments": call.get("arguments") or {},
                                "arguments_error": call.get("arguments_error"),
                            }
                        )
            resume_checkpoint = {
                "step": step,
                "user_text": user_text,
                "assistant_text": final_text,
                "assistant_tool_calls": assistant_tool_calls,
                "tool_messages": step_tool_messages,
                "paused_tool_calls": paused_calls,
                # pending_action_ids 由 /ai/chat 端点在创建 pending 后回填
                "pending_action_ids": [],
            }
            break

        if step_results and all(
            isinstance(item.get("result"), dict) and item["result"].get("skipped")
            for item in step_results
        ):
            stopped_for_repeat = True
            done_reason = "no_progress"
            break

        retry_message = ai_harness_service.failed_retry_budget_message(
            ai_harness_service.failed_tool_signatures(tool_results),
            tool_results,
            AGENT_TOOL_RETRY_LIMIT,
        )
        if retry_message:
            done_reason = "retry_budget_exhausted"
            stop_message = retry_message
            break

        if step >= step_budget:
            reached_limit = True
            done_reason = "max_steps"
            break

        working_messages = [
            *compact_attachments_for_followup(working_messages),
            {"role": "assistant", "content": final_text, "tool_calls": assistant_tool_calls},
            *step_tool_messages,
        ]

    if not dangerous_actions:
        final_plan = {"reply": final_text, "tools": [], "dangerous_actions": []}
    else:
        final_plan = {
            "reply": final_text,
            "tools": [],
            "dangerous_actions": list(dangerous_actions),
        }

    return AgentRunResult(
        final_text=final_text,
        final_plan=final_plan,
        tool_results=tool_results,
        run_summary=ai_harness_service.build_run_summary(
            run_id=run_id,
            objective=user_text,
            started_at=started_at,
            steps=steps,
            final_plan=final_plan,
            tool_results=tool_results,
            done_reason=done_reason,
            stop_message=stop_message,
            max_steps=step_budget,
            retry_limit=AGENT_TOOL_RETRY_LIMIT,
        ),
        reached_limit=reached_limit,
        stopped_for_repeat=stopped_for_repeat,
        stop_message=stop_message,
        resume_checkpoint=resume_checkpoint,
        tool_chain=tool_chain,
        usage=run_usage,
        reasoning="".join(reasoning_parts)[:8000],
        plan_card=captured_plan_card,
        work_plan=captured_work_plan,
    )


def _classify_native_call(db: Session, call: dict) -> str:
    """预判单个 tool_call 的处置类别（不执行）：'dangerous' | 'safe' | 'error'。

    用于 native 循环决定本轮是否暂缓 safe 执行。判定与 _dispatch_native_tool_call 的闸门保持一致。
    阶段 D1：confirm 类工具若被「始终允许」规则命中（grant / autonomous 档），降级为 safe。
    """
    name = str(call.get("name", ""))
    if call.get("arguments_error"):
        return "error"
    is_mcp = name.startswith("mcp__")
    td = tool_registry.get(name)
    if td is None and not is_mcp:
        return "error"
    if td is not None and td.safety == "confirm":
        # 阶段 D1：查 grant / autonomous 档；命中则降级为 safe（直接执行，免确认）
        if ai_grant_service.is_granted(db, name, call.get("arguments")):
            return "safe"
        return "dangerous"
    if is_mcp:
        parsed = mcp_service.parse_namespaced(name)
        if parsed is None:
            return "error"
        server_id, _ = parsed
        if not mcp_service.is_auto_approved(db, server_id, name):
            return "dangerous"
    return "safe"


def _dispatch_native_tool_call(
    db: Session,
    call: dict,
    skip_signatures: set[str],
    summary_source: str,
) -> dict:
    """原生 tool_call 分发闸门：返回 {tool_result, tool_message, dangerous_action}。

    - 畸形参数 / 未知工具 → 错误 tool_result
    - confirm 内置工具 → 记录 dangerous_action，不执行
    - MCP 非 auto_approved → 记录 mcp_tool_call dangerous_action，不执行
    - safe（含 MCP auto_approved）→ execute_tool（或重复成功跳过）
    """
    name = str(call.get("name", ""))
    call_id = str(call.get("id", ""))
    args = call.get("arguments")
    args_error = call.get("arguments_error")

    if args_error:
        result = {"ok": False, "error": args_error}
        return _pack_native_outcome(name, call_id, args, result)

    args = dict(args or {})
    signature = tool_signature({"name": name, "args": args})
    td = tool_registry.get(name)
    is_mcp = name.startswith("mcp__")

    # 未知工具
    if td is None and not is_mcp:
        result = {"ok": False, "error": f"未知工具: {name}"}
        return _pack_native_outcome(name, call_id, args, result)

    # confirm 类内置工具 → 待确认（阶段 D1：grant 命中则降级为 safe 直接执行）
    if td is not None and td.safety == "confirm":
        if ai_grant_service.is_granted(db, name, args):
            # 授权命中：跳过确认，直接执行（复用 skip 逻辑后走 safe 执行）
            if signature in skip_signatures:
                result = {"ok": True, "skipped": True, "message": "已跳过重复成功工具"}
            else:
                result = ai_tool_service.execute_tool(db, name, args)
                if not result.get("ok") and result.get("error", "").startswith("工具需要待确认操作"):
                    # execute_tool 对 confirm 工具会拒绝；授权时绕过闸门直接调底层 service
                    result = _execute_granted_confirm_tool(db, td, args)
            return _pack_native_outcome(name, call_id, args, result)
        action = {
            "action_type": td.confirm_action_type,
            "payload": args,
            "summary": _native_action_summary(summary_source, f"调用确认类工具 {name}"),
        }
        result = {"ok": False, "pending": True, "error": "已创建待确认操作，等待用户确认"}
        return _pack_native_outcome(name, call_id, args, result, action)

    # MCP 工具：非 auto_approved → 待确认
    if is_mcp:
        parsed = mcp_service.parse_namespaced(name)
        if parsed is None:
            result = {"ok": False, "error": f"MCP 工具名格式无效: {name}"}
            return _pack_native_outcome(name, call_id, args, result)
        server_id, fallback_name = parsed
        # 命名空间名可能被截断：用 namespaced 形态判定免确认，payload 里写回原始工具名
        original_name = mcp_service.resolve_tool_name(db, server_id, name) or fallback_name
        if not mcp_service.is_auto_approved(db, server_id, name):
            action = {
                "action_type": "mcp_tool_call",
                "payload": {
                    "server_id": server_id,
                    "tool_name": original_name,
                    "arguments": args,
                },
                "summary": _native_action_summary(summary_source, f"调用 MCP 工具 {name}"),
            }
            result = {"ok": False, "pending": True, "error": "已创建待确认操作，等待用户确认"}
            return _pack_native_outcome(name, call_id, args, result, action)

    # safe 执行（内置 safe 或 MCP auto_approved），含重复成功跳过
    if signature in skip_signatures:
        result = {"ok": True, "skipped": True, "message": "已跳过重复成功工具"}
    else:
        result = ai_tool_service.execute_tool(db, name, args)
    return _pack_native_outcome(name, call_id, args, result)


# 阶段 B4：安全工具并行执行。SQLite 单 Session 非线程安全，因此只读工具在各自独立的
# 短命 Session 里并发跑（asyncio.to_thread + asyncio.gather）；写类 safe 工具仍串行用请求 Session。
_READONLY_BUILTIN = tool_registry.readonly_names()


def _execute_granted_confirm_tool(db: Session, td, args: dict) -> dict:
    """阶段 D1：被 grant / autonomous 授权的 confirm 工具，绕过两段确认直接执行。

    复用 ai_action_service._execute_payload（与确认后执行同一代码路径，行为一致）。
    返回 {ok, ...} 形态（execute_tool 兼容）。
    """
    action_type = td.confirm_action_type or td.name
    payload = {"tool_name": td.name, **dict(args)}
    try:
        ok, message = ai_action_service._execute_payload(db, action_type, dict(args))
        return {"ok": bool(ok), "message": message, "granted": True}
    except (KeyError, TypeError, ValueError) as exc:
        return {"ok": False, "error": str(exc), "granted": True}


async def _dispatch_native_safe_calls(
    db: Session,
    calls: list[dict],
    skip_signatures: set[str],
    summary_source: str,
) -> list[dict]:
    """异步派发一批 safe 调用（has_pending=False 时调用方才进入此函数）。

    优化：若本批全部为内置只读工具，用各自独立 Session 并发执行（asyncio.to_thread + gather）；
    否则（含写类 safe / MCP auto_approved）退化为串行，保证请求 Session 的写事务语义不变。
    返回 outcome 列表，顺序与入参 calls 一致（gather 后按原顺序排回，满足协议要求）。
    """
    if not calls:
        return []

    all_readonly = all(
        str(c.get("name", "")) in _READONLY_BUILTIN and not c.get("arguments_error")
        for c in calls
    )
    # 单个调用或非全部只读 → 串行（无并发收益，且写工具需保持请求 Session 事务）
    if len(calls) == 1 or not all_readonly:
        return [
            _dispatch_native_tool_call(db, c, skip_signatures, summary_source)
            for c in calls
        ]

    # 全部只读 → 并发：每个调用一个独立短命 Session，避免共享 Session 的线程安全问题
    from app.database import SessionLocal as _SessionLocal

    def _run_one(call: dict) -> dict:
        local_db = _SessionLocal()
        try:
            return _dispatch_native_tool_call(local_db, call, skip_signatures, summary_source)
        finally:
            local_db.close()

    outcomes = await asyncio.gather(*(asyncio.to_thread(_run_one, c) for c in calls))
    return list(outcomes)


def _pack_native_outcome(
    name: str,
    call_id: str,
    args: dict | None,
    result: dict,
    dangerous_action: dict | None = None,
) -> dict:
    payload = json.dumps(result, ensure_ascii=False, default=str)
    if len(payload) > AGENT_OBSERVATION_CHAR_LIMIT:
        payload = payload[:AGENT_OBSERVATION_CHAR_LIMIT] + "...[已截断]"
    return {
        "tool_result": {"tool": name, "args": dict(args or {}), "result": result},
        "tool_message": {
            "role": "tool",
            "tool_call_id": call_id,
            "name": name,
            "content": payload,
        },
        "dangerous_action": dangerous_action,
    }


def _is_truncated(provider: str, stop_reason: str | None) -> bool:
    if not stop_reason:
        return False
    return stop_reason in {"max_tokens", "length", "max_output_tokens", "incomplete"}


def _native_action_summary(summary_source: str, fallback: str) -> str:
    return (summary_source or "")[:500] or fallback


def _native_provider_error_with_hint(config: AIConfig, exc: Exception) -> str:
    """provider 拒绝 tools 时追加用户可操作的回退提示（走现有脱敏通道）。

    仅返回脱敏后的原始错误 + 提示，不重复加「模型请求失败」前缀——外层 chat 端点会统一加。
    """
    detail = sanitize_provider_error(exc)
    lowered = detail.lower()
    if any(token in lowered for token in ("tool", "function", "tool_choice")):
        detail = (
            f"{detail}\n该服务商/模型可能不支持原生工具调用，请更换服务商或模型。"
        )
    return detail


async def stream_native_agent_loop(
    db: Session,
    config: AIConfig,
    messages: list[dict],
    user_text: str,
    conversation_id: int | None = None,
    cancelled: asyncio.Event | None = None,
    max_steps: int | None = None,
    mode: str = "chat",
) -> AsyncIterator[dict]:
    """流式版 native agent 循环：yield SSE 事件帧，末帧 yield terminal + AgentRunResult。

    与 _run_native_agent_loop 共用不变量（整轮暂停、分类、skip、retry budget），仅 provider
    调用点换成 stream_provider，text/tool_call_start/tool_result 向下游 yield。
    cancelled 为可选的 asyncio.Event：命中则停止 yield done{cancelled:true}（阶段 5 中断链路）。
    """
    run_id = uuid4().hex
    started_at = datetime.now()
    logger.info("stream_loop 开始 run=%s conv=%s provider=%s", run_id, conversation_id, config.provider)
    # 阶段 B2：步数预算可配置（settings / 请求级覆盖），夹在 [3, 30]
    step_budget = max(3, min(30, int(max_steps or AGENT_MAX_STEPS)))
    working_messages = list(messages)
    tool_results: list[dict] = []
    steps: list[dict] = []
    dangerous_actions: list[dict] = []
    final_text = ""
    final_plan = {"reply": "", "tools": [], "dangerous_actions": []}
    reached_limit = False
    stopped_for_repeat = False
    done_reason = "unknown"
    stop_message = ""
    resume_checkpoint: dict | None = None
    tool_chain: list[dict] = []
    cancelled_flag = False
    # 阶段 2：累计各 provider 轮次的 token 用量，供 usage 事件（实时）+ terminal 帧（落库）
    run_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": 0}
    # 阶段 3：累计各轮 reasoning（非流式 turn 提取的），与流式 reasoning_delta 合并后落库
    reasoning_parts: list[str] = []
    # 阶段 C1/C2：捕获 propose_plan / update_work_plan 产出
    captured_plan_card: dict | None = None
    captured_work_plan: list[dict] | None = None

    for step in range(1, step_budget + 1):
        if cancelled is not None and getattr(cancelled, "is_set", lambda: False)():
            cancelled_flag = True
            done_reason = "cancelled"
            break
        # 阶段 B2 优雅收尾：到达预算的倒数第 2 步时，注入系统提示让模型主动收尾总结
        if step == step_budget - 1 and step_budget >= 4:
            working_messages = [
                *compact_attachments_for_followup(working_messages),
                {
                    "role": "user",
                    "content": (
                        f"⚠️ 你还剩 2 步工作预算。请在下一步内收尾："
                        "完成当前最关键的写操作，并用一段话向用户总结「已完成 / 未完成 / 建议下一步」"
                        "，不要再发起新的多步调研。"
                    ),
                },
            ]
        req = build_chat_provider_request(db, config, working_messages, mode=mode)
        # 流式调用：收 text_delta 等增量帧，末帧 turn 携带组装完整 payload
        raw: dict | None = None
        try:
            async for frame in ai_client.stream_provider(req):
                ftype = frame.get("type")
                if ftype == "text_delta":
                    yield {"event": "text_delta", "data": {"step": step, "delta": frame.get("delta", "")}}
                elif ftype == "reasoning_delta":
                    # 阶段 3：思维链增量透传（仅 config.show_reasoning 为真时；默认 True）
                    if getattr(config, "show_reasoning", True):
                        reasoning_parts.append(frame.get("delta", ""))
                        yield {"event": "reasoning_delta", "data": {"step": step, "delta": frame.get("delta", "")}}
                elif ftype == "tool_call_start":
                    yield {
                        "event": "tool_call_start",
                        "data": {
                            "step": step,
                            "call_id": frame.get("call_id", ""),
                            "name": frame.get("name", ""),
                        },
                    }
                elif ftype == "turn":
                    raw = frame.get("raw") or {}
            if raw is None:
                # 流未产出 turn 帧（异常断流）——视为 provider 错误
                raise RuntimeError("provider 流式响应未产出完整帧")
            step_usage = ai_usage_service.log_usage(
                db, config=config, kind="chat", payload=raw,
                conversation_id=conversation_id,
            )
            # 阶段 2：累加并发 usage 事件（累计值，前端无需做加法；provider 不回 usage 时全 0，前端不展示）
            if step_usage:
                run_usage["prompt_tokens"] += step_usage.get("prompt_tokens", 0)
                run_usage["completion_tokens"] += step_usage.get("completion_tokens", 0)
                run_usage["total_tokens"] += step_usage.get("total_tokens", 0)
            run_usage["calls"] += 1
            yield {"event": "usage", "data": {**dict(run_usage), "step": step}}
        except Exception as exc:
            provider_error = _native_provider_error_with_hint(config, exc)
            logger.warning("stream_loop provider 错误 run=%s step=%d: %s", run_id, step, provider_error)
            if step == 1:
                yield {"event": "error", "data": {"message": provider_error, "fatal": True}}
                return
            tool_results.append(
                {
                    "tool": "ai_agent",
                    "args": {"step": step},
                    "result": {"ok": False, "error": provider_error},
                }
            )
            done_reason = "provider_error"
            stop_message = provider_error
            break

        turn = ai_client.extract_assistant_turn(config.provider, raw)
        final_text = turn["text"]
        tool_calls = turn.get("tool_calls") or []
        # 阶段 3：累积非流式 turn 提取的 reasoning（与流式 reasoning_delta 合并）
        if turn.get("reasoning") and getattr(config, "show_reasoning", True):
            reasoning_parts.append(turn["reasoning"])

        if _is_truncated(config.provider, turn.get("stop_reason")):
            steps.append(
                {
                    "step": step,
                    "reply": final_text,
                    "plan": {},
                    "tools": [],
                    "dangerous_actions": [],
                    "observations": [],
                    "done": False,
                    "truncated": True,
                }
            )
            done_reason = "max_tokens"
            working_messages = [
                *compact_attachments_for_followup(working_messages),
                {"role": "assistant", "content": final_text},
                {
                    "role": "user",
                    "content": "你的上一条输出被截断（达到 max_tokens），请缩短单次回复后继续。",
                },
            ]
            if step >= step_budget:
                reached_limit = True
                done_reason = "max_steps"
                break
            continue

        if not tool_calls:
            steps.append(
                {
                    "step": step,
                    "reply": final_text,
                    "plan": {},
                    "tools": [],
                    "dangerous_actions": [],
                    "observations": [],
                    "done": True,
                }
            )
            done_reason = "no_tools"
            break

        skip_signatures = successful_tool_signatures(tool_results)
        classifications = [_classify_native_call(db, call) for call in tool_calls]
        has_pending = any(cls == "dangerous" for cls in classifications)

        step_results: list[dict] = []
        step_tool_messages: list[dict] = []
        assistant_tool_calls = []
        for call, cls in zip(tool_calls, classifications):
            # 工具分发前检查取消（阶段 5）：原子点，被取消则停止且不执行半个工具
            if cancelled is not None and cancelled.is_set():
                cancelled_flag = True
                done_reason = "cancelled"
                break
            if has_pending and cls != "dangerous":
                name = str(call.get("name", ""))
                call_id = str(call.get("id", ""))
                paused_args = call.get("arguments") or {}
                outcome = _pack_native_outcome(
                    name,
                    call_id,
                    paused_args,
                    {
                        "ok": False,
                        "pending": True,
                        "error": "本轮回包含需确认操作，安全工具暂缓执行，待用户确认后继续",
                    },
                )
            else:
                outcome = _dispatch_native_tool_call(db, call, skip_signatures, final_text)
            step_results.append(outcome["tool_result"])
            step_tool_messages.append(outcome["tool_message"])
            assistant_tool_calls.append(
                {
                    "id": str(call.get("id", "")),
                    "name": str(call.get("name", "")),
                    "arguments": call.get("arguments") or {},
                }
            )
            if outcome["dangerous_action"] is not None:
                dangerous_actions.append(outcome["dangerous_action"])
            # 流式：补发带完整 args 的 tool_call_start（ai_client 早期帧仅含 name），供前端卡片显示参数
            yield {
                "event": "tool_call_start",
                "data": {
                    "step": step,
                    "call_id": str(call.get("id", "")),
                    "name": str(call.get("name", "")),
                    "args": call.get("arguments") or {},
                },
            }
            # 流式发射工具结果（含 pending/skipped/error 态）
            tr = outcome["tool_result"]
            result = tr.get("result") or {}
            yield {
                "event": "tool_result",
                "data": {
                    "step": step,
                    "call_id": str(call.get("id", "")),
                    "name": tr.get("tool", ""),
                    "ok": bool(result.get("ok")),
                    "skipped": bool(result.get("skipped")),
                    "pending": bool(result.get("pending")),
                    "error": result.get("error"),
                    "preview": _preview_tool_result(result),
                },
            }
            # 阶段 C1/C2：捕获 propose_plan / update_work_plan 并推送专属事件
            if isinstance(result, dict) and result.get("plan_card"):
                captured_plan_card = result["plan_card"]
                yield {"event": "plan_proposed", "data": {"plan_card": captured_plan_card}}
            if isinstance(result, dict) and result.get("work_plan"):
                captured_work_plan = result["work_plan"]
                yield {"event": "work_plan", "data": {"items": captured_work_plan}}

        tool_results.extend(step_results)
        # 记录本步 tool 交互（含 call_id）到 tool_chain，供跨轮回放
        tool_chain.append(
            {"role": "assistant", "content": final_text, "tool_calls": list(assistant_tool_calls)}
        )
        tool_chain.extend(step_tool_messages)
        steps.append(
            {
                "step": step,
                "reply": final_text,
                "plan": {},
                "tools": [{"name": c["name"], "args": c["arguments"]} for c in assistant_tool_calls],
                "dangerous_actions": list(dangerous_actions),
                "observations": ai_harness_service.step_observations(step_results),
                "done": False,
            }
        )

        if dangerous_actions:
            final_plan = {
                "reply": final_text,
                "tools": [],
                "dangerous_actions": list(dangerous_actions),
            }
            done_reason = "pending_confirmation"
            paused_calls = []
            if has_pending:
                for call, cls in zip(tool_calls, classifications):
                    if cls != "dangerous":
                        paused_calls.append(
                            {
                                "id": str(call.get("id", "")),
                                "name": str(call.get("name", "")),
                                "arguments": call.get("arguments") or {},
                                "arguments_error": call.get("arguments_error"),
                            }
                        )
            resume_checkpoint = {
                "step": step,
                "user_text": user_text,
                "assistant_text": final_text,
                "assistant_tool_calls": assistant_tool_calls,
                "tool_messages": step_tool_messages,
                "paused_tool_calls": paused_calls,
                "pending_action_ids": [],
            }
            yield {
                "event": "pending_confirmation",
                "data": {
                    "step": step,
                    "actions": [
                        {
                            "action_type": da.get("action_type", ""),
                            "summary": da.get("summary", ""),
                        }
                        for da in dangerous_actions
                    ],
                },
            }
            yield {"event": "step_finish", "data": {"step": step}}
            break

        if step_results and all(
            isinstance(item.get("result"), dict) and item["result"].get("skipped")
            for item in step_results
        ):
            stopped_for_repeat = True
            done_reason = "no_progress"
            break

        retry_message = ai_harness_service.failed_retry_budget_message(
            ai_harness_service.failed_tool_signatures(tool_results),
            tool_results,
            AGENT_TOOL_RETRY_LIMIT,
        )
        if retry_message:
            done_reason = "retry_budget_exhausted"
            stop_message = retry_message
            break

        if step >= step_budget:
            reached_limit = True
            done_reason = "max_steps"
            break

        yield {"event": "step_finish", "data": {"step": step}}
        working_messages = [
            *compact_attachments_for_followup(working_messages),
            {"role": "assistant", "content": final_text, "tool_calls": assistant_tool_calls},
            *step_tool_messages,
        ]

    if not dangerous_actions:
        final_plan = {"reply": final_text, "tools": [], "dangerous_actions": []}
    else:
        final_plan = {
            "reply": final_text,
            "tools": [],
            "dangerous_actions": list(dangerous_actions),
        }

    agent_run = AgentRunResult(
        final_text=final_text,
        final_plan=final_plan,
        tool_results=tool_results,
        run_summary=ai_harness_service.build_run_summary(
            run_id=run_id,
            objective=user_text,
            started_at=started_at,
            steps=steps,
            final_plan=final_plan,
            tool_results=tool_results,
            done_reason=done_reason,
            stop_message=stop_message,
            max_steps=step_budget,
            retry_limit=AGENT_TOOL_RETRY_LIMIT,
        ),
        reached_limit=reached_limit,
        stopped_for_repeat=stopped_for_repeat,
        stop_message=stop_message,
        resume_checkpoint=resume_checkpoint,
        tool_chain=tool_chain,
        usage=run_usage,
        reasoning="".join(reasoning_parts)[:8000],
        plan_card=captured_plan_card,
        work_plan=captured_work_plan,
    )
    logger.info(
        "stream_loop 结束 run=%s done_reason=%s steps=%d cancelled=%s usage=%s",
        run_id, done_reason, len(steps), cancelled_flag, run_usage.get("total_tokens", 0),
    )
    yield {"event": "terminal", "data": {"agent_run": agent_run, "cancelled": cancelled_flag}}


def _preview_tool_result(result: dict, limit: int = 500) -> str:
    """生成 tool_result 的前端预览文本（截断），用于 SSE tool_result 事件。"""
    try:
        text = json.dumps(result, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = str(result)
    if len(text) > limit:
        return text[:limit] + "...[已截断]"
    return text


def _materialize_pending_actions(
    db: Session, conversation_id: int, dangerous_actions: list[dict]
) -> list:
    """把 agent 循环产出的 dangerous_actions 落库为 pending actions（chat 与 stream 共用）。"""
    pending = []
    for item in dangerous_actions:
        if not isinstance(item, dict):
            continue
        action_type = item.get("action_type", "")
        if not ai_action_service.is_supported_action_type(action_type):
            continue
        payload_data = item.get("payload", {})
        if payload_data is None:
            payload_data = {}
        if not isinstance(payload_data, dict):
            continue
        action = ai_action_service.create_pending_action(
            db,
            conversation_id,
            action_type,
            dict(payload_data),
            item.get("summary", "危险操作待确认"),
        )
        pending.append(action)
    return pending


def _compose_assistant_reply(agent_run: "AgentRunResult", tool_results: list[dict]) -> str:
    """组装最终回复文本：reply + 失败中断 + 上限提示 + stop_message（chat 与 stream 共用）。"""
    reply = agent_run.final_plan["reply"] or agent_run.final_text
    agent_failed = next(
        (
            item["result"]["error"]
            for item in tool_results
            if item.get("tool") == "ai_agent"
            and isinstance(item.get("result"), dict)
            and item["result"].get("error")
        ),
        None,
    )
    if agent_failed:
        reply = f"{reply}\n\n连续工作中断：{agent_failed}"
    if agent_run.reached_limit:
        # 步数预算来自 run_summary（可配置，阶段 B2）；不再硬编码
        budget = (agent_run.run_summary or {}).get("max_steps", AGENT_MAX_STEPS)
        reply = f"{reply}\n\n已达到连续工作轮次上限（{budget} 轮），请继续发消息让我接着处理。"
    if agent_run.stop_message and agent_run.stop_message not in reply:
        reply = f"{reply}\n\n{agent_run.stop_message}"
    return reply


def _persist_assistant_run(
    db: Session,
    conversation: AIConversation,
    agent_run: "AgentRunResult",
    reply: str,
    pending: list,
    resumed_from_id: int | None = None,
    interrupted: bool = False,
    elapsed_ms: int | None = None,
) -> AIMessage:
    """落库 assistant 消息（含 tool_results / pending_action_ids / agent_run / 可选 resume checkpoint）。

    chat 与 stream 端点共用，保证两者写出相同 DB 状态。
    """
    resume_meta = None
    if agent_run.resume_checkpoint is not None:
        resume_meta = dict(agent_run.resume_checkpoint)
        resume_meta["pending_action_ids"] = [action.id for action in pending]
    assistant_meta: dict = {
        "tool_results": agent_run.tool_results,
        "pending_action_ids": [action.id for action in pending],
        "agent_run": agent_run.run_summary,
    }
    if resumed_from_id is not None:
        assistant_meta["resumed_from"] = resumed_from_id
    if interrupted:
        assistant_meta["interrupted"] = True
    if resume_meta is not None:
        assistant_meta["resume"] = resume_meta
    if agent_run.tool_chain:
        assistant_meta["tool_chain"] = agent_run.tool_chain
    # 阶段 2：本次 run 累计 token 用量 + 耗时（历史消息刷新后仍可见）
    if agent_run.usage and agent_run.usage.get("total_tokens", 0) > 0:
        assistant_meta["usage"] = agent_run.usage
    if elapsed_ms is not None:
        assistant_meta["elapsed_ms"] = int(elapsed_ms)
    # 阶段 3：思维链（agent_run.reasoning 由循环按 config.show_reasoning 闸门产出，此处非空即落库）
    if agent_run.reasoning:
        assistant_meta["reasoning"] = agent_run.reasoning[:8000]
    # 阶段 C1：plan 模式计划卡片（agent 调用 propose_plan 产出，供前端 PlanCard 渲染 + approve/reject）
    if agent_run.plan_card:
        assistant_meta["plan_card"] = agent_run.plan_card
    # 阶段 C2：工作清单快照（最后一次 update_work_plan 产出）
    if agent_run.work_plan:
        assistant_meta["work_plan"] = agent_run.work_plan
    assistant_msg = AIMessage(
        conversation_id=conversation.id,
        role="assistant",
        content=reply,
        meta=json.dumps(assistant_meta, ensure_ascii=False),
    )
    db.add(assistant_msg)
    conversation.updated_at = datetime.now()
    db.commit()
    return assistant_msg


def pending_action_response(db: Session, action) -> AIPendingActionResponse:
    data = AIPendingActionResponse.model_validate(action)
    data.preview = ai_action_service.action_preview(db, action)
    return data


def message_meta(message: AIMessage) -> dict:
    try:
        data = json.loads(message.meta or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def conversation_summary(conversation: AIConversation) -> AIConversationSummaryResponse:
    messages = list(conversation.messages or [])
    last = next((message for message in reversed(messages) if message.content), None)
    updated_at = conversation.updated_at or conversation.created_at
    return AIConversationSummaryResponse(
        id=conversation.id,
        title=conversation.title,
        last_message=(last.content[:120] if last else ""),
        message_count=len(messages),
        created_at=conversation.created_at,
        updated_at=updated_at,
    )


def conversation_message_response(db: Session, message: AIMessage) -> AIConversationMessageResponse:
    meta = message_meta(message)
    pending = []
    for action_id in meta.get("pending_action_ids", []):
        action = db.get(AIPendingAction, action_id)
        if action is not None:
            pending.append(pending_action_response(db, action))
    # meta 白名单：只透出前端展示需要的键；内部键（pending_action_ids / tool_results 等）不下发
    # 阶段 C1/C2：plan_card（PlanCard 渲染）与 work_plan（工作清单）加入白名单
    public_meta = {
        key: meta[key]
        for key in ("usage", "elapsed_ms", "reasoning", "plan_card", "work_plan")
        if meta.get(key)
    }
    return AIConversationMessageResponse(
        id=message.id,
        role=message.role,
        content=message.content,
        tool_results=meta.get("tool_results", []) if isinstance(meta.get("tool_results", []), list) else [],
        pending_actions=pending,
        meta=public_meta,
        created_at=message.created_at,
    )


@router.get("/configs", response_model=list[AIConfigResponse])
def list_configs(db: Session = Depends(get_db)):
    return ai_config_service.list_configs(db)


@router.post(
    "/configs", response_model=AIConfigResponse, status_code=status.HTTP_201_CREATED
)
def create_config(payload: AIConfigCreate, db: Session = Depends(get_db)):
    return ai_config_service.create_config(db, payload)


@router.put("/configs/{config_id}", response_model=AIConfigResponse)
def update_config(
    config_id: int, payload: AIConfigUpdate, db: Session = Depends(get_db)
):
    config = ai_config_service.update_config(db, config_id, payload)
    if config is None:
        raise HTTPException(status_code=404, detail="AI 配置不存在")
    return config


@router.post("/configs/{config_id}/enable", response_model=AIConfigResponse)
def enable_config(config_id: int, db: Session = Depends(get_db)):
    config = ai_config_service.enable_config(db, config_id)
    if config is None:
        raise HTTPException(status_code=404, detail="AI 配置不存在")
    return config


@router.post("/configs/{config_id}/test")
async def test_config(config_id: int, db: Session = Depends(get_db)):
    config = db.get(AIConfig, config_id)
    if config is None:
        raise HTTPException(status_code=404, detail="AI 配置不存在")
    req = ai_client.build_provider_request(
        provider=config.provider,
        model=config.model,
        api_key=config.api_key,
        messages=[{"role": "user", "content": "请回复：连接成功"}],
        system_prompt="你是连接测试助手，只需要简短回复。",
        extra_headers=ai_config_service.headers_from_json(config.extra_headers),
        base_url=config.base_url,
        full_url=config.full_url,
        proxy_url=config.proxy_url,
        native_web_search_enabled=bool(
            config.native_web_search_enabled or config.search_enhancement_enabled
        ),
        native_web_search_options=ai_config_service.options_from_json(
            config.native_web_search_options
        ),
    )
    try:
        await ai_client.call_provider(req)
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=provider_failure_detail("模型连接", exc)
        ) from exc
    return {"ok": True, "message": "模型连接测试成功"}


@router.post("/models", response_model=AIModelsResponse)
async def list_models(payload: AIModelsRequest, db: Session = Depends(get_db)):
    config = db.get(AIConfig, payload.config_id) if payload.config_id else None
    provider = payload.provider or (config.provider if config else None)
    api_key = payload.api_key or (config.api_key if config else None)
    base_url = (
        payload.base_url
        if payload.base_url is not None
        else config.base_url if config else None
    )
    full_url = (
        payload.full_url
        if payload.full_url is not None
        else config.full_url if config else None
    )
    proxy_url = (
        payload.proxy_url
        if payload.proxy_url is not None
        else config.proxy_url if config else None
    )
    extra_headers = (
        ai_config_service.merge_masked_headers(config, payload.extra_headers)
        if payload.extra_headers and config
        else payload.extra_headers
        if payload.extra_headers
        else ai_config_service.headers_from_json(config.extra_headers) if config else {}
    )
    if not provider or not api_key:
        raise HTTPException(status_code=400, detail="需要 provider 和 API key 才能获取模型列表")
    req = ai_client.build_models_request(
        provider=provider,
        api_key=api_key,
        extra_headers=extra_headers,
        base_url=base_url,
        full_url=full_url,
        proxy_url=proxy_url,
    )
    try:
        data = await ai_client.call_models(req)
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=provider_failure_detail("模型列表获取", exc)
        ) from exc
    return AIModelsResponse(models=ai_client.extract_model_ids(data))


@router.post(
    "/attachments",
    response_model=AIChatAttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_chat_attachment(file: UploadFile = UploadFileParam(...)):
    return ai_attachment_service.save_upload(file)


@router.get("/conversations", response_model=list[AIConversationSummaryResponse])
def list_conversations(
    limit: int = Query(50, ge=1, le=50),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(AIConversation)
        .order_by(AIConversation.updated_at.desc(), AIConversation.id.desc())
        .limit(limit)
        .all()
    )
    return [conversation_summary(conversation) for conversation in rows]


@router.get("/conversations/{conversation_id}", response_model=AIConversationDetailResponse)
def get_conversation(conversation_id: int, db: Session = Depends(get_db)):
    conversation = db.get(AIConversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="AI 会话不存在")
    summary = conversation_summary(conversation)
    return AIConversationDetailResponse(
        **summary.model_dump(),
        messages=[
            conversation_message_response(db, message)
            for message in conversation.messages
            if message.role in {"user", "assistant", "system"}
        ],
    )


@router.patch("/conversations/{conversation_id}", response_model=AIConversationSummaryResponse)
def rename_conversation(
    conversation_id: int, payload: AIConversationRename, db: Session = Depends(get_db)
):
    conversation = db.get(AIConversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="AI 会话不存在")
    title = payload.title.strip()
    if title:
        conversation.title = title
        db.commit()
        db.refresh(conversation)
    return conversation_summary(conversation)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: int, db: Session = Depends(get_db)):
    conversation = db.get(AIConversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="AI 会话不存在")
    db.delete(conversation)
    db.commit()


@router.get("/skills", response_model=list[AISkillResponse])
def list_skills(db: Session = Depends(get_db)):
    return ai_skill_service.list_skills(db)


@router.post("/skills", response_model=AISkillResponse, status_code=status.HTTP_201_CREATED)
def create_skill(payload: AISkillCreate, db: Session = Depends(get_db)):
    try:
        return ai_skill_service.create_skill(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/skills/disable-all", status_code=status.HTTP_204_NO_CONTENT)
def disable_all_skills(db: Session = Depends(get_db)):
    """停用全部用户 skill，清空所有配置的 active_skill_id 指针。"""
    ai_skill_service.disable_all_skills(db)


@router.put("/skills/{skill_id}", response_model=AISkillResponse)
def update_skill(skill_id: int, payload: AISkillUpdate, db: Session = Depends(get_db)):
    try:
        skill = ai_skill_service.update_skill(db, skill_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if skill is None:
        raise HTTPException(status_code=404, detail="AI skill 不存在")
    return skill


@router.delete("/skills/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_skill(skill_id: int, db: Session = Depends(get_db)):
    result = ai_skill_service.delete_skill(db, skill_id)
    if result is None:
        raise HTTPException(status_code=404, detail="AI skill 不存在")
    if result is False:
        raise HTTPException(status_code=409, detail="内置 skill 不可删除")


@router.post("/skills/{skill_id}/enable", response_model=AISkillResponse)
def enable_skill(skill_id: int, db: Session = Depends(get_db)):
    try:
        skill = ai_skill_service.enable_skill(db, skill_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if skill is None:
        raise HTTPException(status_code=404, detail="AI skill 不存在")
    return skill


@router.post("/skills/import", response_model=AISkillResponse, status_code=status.HTTP_201_CREATED)
def import_skill(payload: AISkillImport, db: Session = Depends(get_db)):
    try:
        return ai_skill_service.import_skill(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/actions/{action_id}/confirm")
def confirm_action(action_id: int, db: Session = Depends(get_db)):
    action, token, error = ai_action_service.confirm_action(db, action_id)
    if action is None:
        raise HTTPException(status_code=404, detail=error)
    if error:
        raise HTTPException(status_code=409, detail=error)
    return {
        "action": pending_action_response(db, action),
        "confirm_token": token,
    }


@router.post("/actions/{action_id}/reject")
def reject_action(action_id: int, db: Session = Depends(get_db)):
    action, error = ai_action_service.reject_action(db, action_id)
    if action is None:
        raise HTTPException(status_code=404, detail=error)
    if error:
        raise HTTPException(status_code=409, detail=error)
    return {"action": pending_action_response(db, action)}


@router.post("/actions/{action_id}/execute")
def execute_action(
    action_id: int, payload: AIActionExecute, db: Session = Depends(get_db)
):
    ok, message = ai_action_service.execute_action(
        db, action_id, payload.confirm_token
    )
    if not ok and "token" in message:
        raise HTTPException(status_code=403, detail=message)
    if not ok:
        raise HTTPException(status_code=409, detail=message)
    return {"ok": True, "message": message}


@router.post("/chat", response_model=AIChatResponse)
async def chat(payload: AIChatRequest, db: Session = Depends(get_db)):
    config = ai_config_service.get_enabled_config(db)
    if config is None:
        raise HTTPException(status_code=400, detail="未启用 AI 配置")

    conversation, user_text, messages = _prepare_chat_context(
        db, payload.message, payload.attachments, payload.conversation_id
    )
    # 阶段 B3：长会话压缩（超阈值把旧消息压成摘要，失败静默降级）
    messages = await _apply_compaction(db, conversation, config, messages)
    try:
        agent_run = await run_agent_loop(
            db, config, messages, user_text, conversation_id=conversation.id,
            max_steps=payload.max_steps, mode=payload.mode or "chat",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=provider_failure_detail("模型请求", exc)
        ) from exc

    pending = _materialize_pending_actions(
        db, conversation.id, agent_run.final_plan["dangerous_actions"]
    )
    reply = _compose_assistant_reply(agent_run, agent_run.tool_results)
    _persist_assistant_run(db, conversation, agent_run, reply, pending)

    return AIChatResponse(
        conversation_id=conversation.id,
        assistant_name=ai_prompt_service.resolve_assistant_name(db, config),
        reply=reply,
        tool_results=agent_run.tool_results,
        pending_actions=[
            pending_action_response(db, action) for action in pending
        ],
        usage=agent_run.usage,
    )


def _sse(event: str, data: dict) -> str:
    """格式化 SSE 帧：event: <name>\\ndata: <json>\\n\\n"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _prepare_chat_context(
    db: Session, message: str, attachments: list, conversation_id: int | None
) -> tuple[AIConversation, str, list[dict]]:
    """chat 与 stream 共用的前置：建会话、落用户消息、组装 messages（含附件）。

    返回 (conversation, user_text, messages)。与 /ai/chat 端点逻辑保持一致。
    """
    attachment_ids = [a.id for a in attachments]
    model_attachments = ai_attachment_service.build_model_attachments(attachment_ids)
    user_text = (message or "").strip() or "请分析这些附件。"
    stored_user_content = user_text
    if model_attachments:
        attachment_lines = [
            f"- {item.get('filename')} ({item.get('mime_type')}, 附件 ID: {item.get('id')})"
            for item in model_attachments
        ]
        stored_user_content = f"{user_text}\n\n[对话附件]\n" + "\n".join(attachment_lines)

    conversation = db.get(AIConversation, conversation_id) if conversation_id else None
    if conversation is None:
        conversation = AIConversation(title=user_text[:60] or "新的对话")
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    user_msg = AIMessage(
        conversation_id=conversation.id,
        role="user",
        content=stored_user_content,
        meta=json.dumps({"attachment_ids": attachment_ids}, ensure_ascii=False),
    )
    db.add(user_msg)
    db.commit()

    history = (
        db.query(AIMessage)
        .filter(AIMessage.conversation_id == conversation.id)
        .order_by(AIMessage.id)
        .all()
    )
    messages = build_replay_messages(history)
    if model_attachments and messages:
        messages[-1] = {
            "role": "user",
            "content": user_text,
            "attachments": model_attachments,
        }
    return conversation, user_text, messages


async def _apply_compaction(
    db: Session, conversation: AIConversation, config: AIConfig, messages: list[dict]
) -> list[dict]:
    """阶段 B3：触发长会话压缩，并在产生摘要时把摘要注入 messages 头部。

    压缩成功后旧消息被标记 compacted，重放时自然不再包含；摘要以 user/assistant 对注入，
    让模型「记得」历史要点。压缩失败（provider 异常）静默降级，messages 原样返回。
    """
    try:
        await ai_compaction_service.maybe_compact(db, conversation, config)
    except Exception:
        logger.warning("会话 %s 压缩调用异常，已忽略", conversation.id, exc_info=True)
        return messages
    summary = ai_compaction_service.summary_for_replay(conversation)
    if not summary or not messages:
        return messages
    return [
        {"role": "user", "content": f"【此前对话要点摘要】\n{summary}"},
        {"role": "assistant", "content": "好的，我已了解之前的对话要点，请继续。"},
        *messages,
    ]


# ---- 阶段 6：上下文回放修复 ----
REPLAY_TOOL_CONTENT_LIMIT = 1000
REPLAY_MAX_ROUNDS = 20
REPLAY_MAX_MESSAGES = 60


def _expand_assistant_for_replay(meta: dict, content: str) -> list[dict]:
    """把带 meta 的 assistant 消息展开为完整 tool 链（assistant+tool_calls + 各 tool 消息）。

    优先用 meta.resume checkpoint（最完整：含 assistant_tool_calls + tool_messages）；
    否则用 meta.tool_results 反推（重建 tool_calls + tool 结果）。
    tool content 截到 REPLAY_TOOL_CONTENT_LIMIT，避免上下文爆炸。
    老数据/链不完整 → 返回单条纯 content（降级）。
    """
    if not isinstance(meta, dict) or not meta:
        return [{"role": "assistant", "content": content}] if content else []

    # 最优先：meta.tool_chain（本次 run 真实 tool 交互序列，含 call_id），完整展开。
    # 正常完成的轮次也会写入 tool_chain，解决此前仅暂停轮可回放导致的跨轮失忆。
    tool_chain = meta.get("tool_chain")
    if isinstance(tool_chain, list) and tool_chain:
        expanded_chain: list[dict] = []
        for chain_msg in tool_chain:
            if not isinstance(chain_msg, dict):
                continue
            if chain_msg.get("role") == "assistant":
                expanded_chain.append({
                    "role": "assistant",
                    "content": chain_msg.get("content", ""),
                    "tool_calls": chain_msg.get("tool_calls") or [],
                })
            elif chain_msg.get("role") == "tool":
                tc_content = str(chain_msg.get("content", ""))
                if len(tc_content) > REPLAY_TOOL_CONTENT_LIMIT:
                    tc_content = tc_content[:REPLAY_TOOL_CONTENT_LIMIT] + "...[已截断]"
                expanded_chain.append({
                    "role": "tool",
                    "tool_call_id": str(chain_msg.get("tool_call_id", "")),
                    "name": str(chain_msg.get("name", "")),
                    "content": tc_content,
                })
        if expanded_chain:
            return expanded_chain

    # 次优：resume checkpoint 自带完整 tool 链（暂停轮）
    checkpoint = meta.get("resume")
    if isinstance(checkpoint, dict):
        tool_calls = checkpoint.get("assistant_tool_calls") or []
        tool_messages = checkpoint.get("tool_messages") or []
        if tool_calls and tool_messages:
            expanded = [
                {
                    "role": "assistant",
                    "content": str(checkpoint.get("assistant_text") or content),
                    "tool_calls": [
                        {
                            "id": str(tc.get("id", "")),
                            "name": str(tc.get("name", "")),
                            "arguments": tc.get("arguments") or {},
                        }
                        for tc in tool_calls
                    ],
                }
            ]
            for tm in tool_messages:
                if not isinstance(tm, dict):
                    continue
                tm_content = str(tm.get("content", ""))
                if len(tm_content) > REPLAY_TOOL_CONTENT_LIMIT:
                    tm_content = tm_content[:REPLAY_TOOL_CONTENT_LIMIT] + "...[已截断]"
                expanded.append(
                    {
                        "role": "tool",
                        "tool_call_id": str(tm.get("tool_call_id", "")),
                        "name": str(tm.get("name", "")),
                        "content": tm_content,
                    }
                )
            return expanded

    # 退路：从 tool_results 反推（无 tool_calls id 时不可靠，仅当有 tool_results 时尝试）
    tool_results = meta.get("tool_results")
    if isinstance(tool_results, list) and tool_results:
        # tool_results 形如 [{"tool":name,"args":{},"result":{}}]
        # 重建需要 call_id；tool_results 不含 call_id，故无法可靠展开为 tool 消息
        # （provider 要求 tool 消息的 tool_call_id 与 assistant.tool_calls 对齐）。
        # 降级：仅保留 content，避免孤儿 tool 消息导致 400。
        return [{"role": "assistant", "content": content}] if content else []

    return [{"role": "assistant", "content": content}] if content else []


def build_replay_messages(history: list) -> list[dict]:
    """从历史消息重建 provider 消息：按「轮」截断，assistant 带 tool 链时展开。

    一轮 = 一条 user 消息 + 紧随其后的 assistant（含 tool 链）+ 可能的后续 assistant。
    从最新往回保留 REPLAY_MAX_ROUNDS 轮，总消息数 cap REPLAY_MAX_MESSAGES，
    绝不产生孤儿 tool 消息（tool 消息必紧跟其 assistant，截断在轮边界）。
    """
    # 1) 展开每条历史消息为 provider 消息序列
    expanded: list[list[dict]] = []
    for m in history:
        # 阶段 B3：已被压缩纳入摘要的消息跳过（防上下文爆炸）；compacted 列旧数据默认 False
        if bool(getattr(m, "compacted", False)):
            continue
        role = getattr(m, "role", None)
        if role == "user":
            content = getattr(m, "content", "") or ""
            if content:
                expanded.append([{"role": "user", "content": content}])
        elif role == "assistant":
            content = getattr(m, "content", "") or ""
            meta = message_meta(m) if hasattr(m, "meta") else {}
            msgs = _expand_assistant_for_replay(meta, content)
            if msgs:
                expanded.append(msgs)
        # 其他 role（system/tool 直接落库的）跳过——tool 消息由 assistant 展开

    if not expanded:
        return []

    # 2) 按「轮」从最新往回保留：一轮 = 一条 user 起头 + 其后所有非 user 消息
    #    expanded 中每个元素是一条「原始消息」的展开；user 元素单独成轮起头。
    #    从末尾往回聚合：遇到 user 元素则开始新轮，直到累计 REPLAY_MAX_ROUNDS 轮。
    rounds: list[list[list[dict]]] = []  # 每轮是 expanded 元素的子列表
    current_round: list[list[dict]] = []
    for element in reversed(expanded):
        is_user_start = element and element[0].get("role") == "user"
        if is_user_start and current_round:
            # 当前轮已累积，遇到新 user → 结束当前轮，开始新轮
            rounds.append(current_round)
            current_round = []
            if len(rounds) >= REPLAY_MAX_ROUNDS:
                break
        current_round.append(element)
    if current_round and len(rounds) < REPLAY_MAX_ROUNDS:
        rounds.append(current_round)

    # 3) 展平（已是最新的在前反转过，需还原时间顺序）并 cap 总消息数
    selected = [el for round_msgs in reversed(rounds) for el in reversed(round_msgs)]
    flat: list[dict] = [msg for element in selected for msg in element]
    # 从最新的往回保留，不超过 REPLAY_MAX_MESSAGES；但必须在轮边界切（不能切到 tool 消息孤儿）
    # 由于 selected 已按轮聚合，且 tool 消息紧随其 assistant，从尾部 cap 不会产生孤儿。
    if len(flat) > REPLAY_MAX_MESSAGES:
        # 从头部丢弃（保留最新），但确保头部不是 tool 消息（避免孤儿）
        drop = len(flat) - REPLAY_MAX_MESSAGES
        while drop < len(flat) and flat[drop].get("role") == "tool":
            drop += 1
        flat = flat[drop:]
    return flat


async def _stream_agent_run(
    db: Session,
    config: AIConfig,
    conversation: AIConversation,
    user_text: str,
    messages: list[dict],
    assistant_name: str,
    *,
    resumed: bool = False,
    resumed_from_id: int | None = None,
    run_id: str | None = None,
    cancelled: asyncio.Event | None = None,
    checkpoint_msg: AIMessage | None = None,
    max_steps: int | None = None,
    mode: str = "chat",
) -> AsyncIterator[str]:
    """驱动 stream_native_agent_loop，把事件帧格式化为 SSE 字符串 yield。

    流结束（terminal/error）后落库 assistant 消息，最后发 done 帧作为权威收敛。
    run_id/cancelled 用于阶段 5 中断链路：调用方在 _register_run 注册事件并传入。
    """
    rid = run_id or uuid4().hex
    yield _sse(
        "meta",
        {
            "conversation_id": conversation.id,
            "assistant_name": assistant_name,
            "run_id": rid,
            "resumed": resumed,
        },
    )
    agent_run: AgentRunResult | None = None
    interrupted = False
    # 阶段 2：记录本次 run 起始时刻，done 帧/落库带上真实耗时
    run_start_ts = datetime.now()
    try:
        async for frame in stream_native_agent_loop(
            db, config, messages, user_text,
            conversation_id=conversation.id, cancelled=cancelled, max_steps=max_steps,
            mode=mode,
        ):
            event = frame.get("event", "")
            data = frame.get("data") or {}
            if event == "terminal":
                agent_run = data.get("agent_run")
                interrupted = bool(data.get("cancelled"))
            elif event == "error":
                # 落库部分结果（若有）后发 error 帧
                yield _sse("error", {"message": data.get("message", ""), "fatal": True})
                return
            else:
                yield _sse(event, data)
    except Exception as exc:
        detail = provider_failure_detail("模型请求" if not resumed else "续跑模型请求", exc)
        logger.exception("_stream_agent_run 异常 rid=%s: %s", rid, detail)
        yield _sse("error", {"message": detail, "fatal": True})
        return

    if agent_run is None:
        logger.warning("_stream_agent_run 未收到模型响应 rid=%s", rid)
        yield _sse("error", {"message": "未收到模型响应", "fatal": True})
        return

    pending = _materialize_pending_actions(
        db, conversation.id, agent_run.final_plan["dangerous_actions"]
    )
    reply = _compose_assistant_reply(agent_run, agent_run.tool_results)
    if interrupted:
        reply = f"{reply}\n\n[已中断]" if reply else "[已中断]"
    elapsed_ms = int((datetime.now() - run_start_ts).total_seconds() * 1000)
    _persist_assistant_run(
        db, conversation, agent_run, reply, pending,
        resumed_from_id=resumed_from_id, interrupted=interrupted, elapsed_ms=elapsed_ms,
    )
    # 续跑成功落库后清除原 checkpoint（provider 失败时保留，以便重试）
    if checkpoint_msg is not None and "resume" in message_meta(checkpoint_msg):
        ck_meta = message_meta(checkpoint_msg)
        ck_meta.pop("resume", None)
        checkpoint_msg.meta = json.dumps(ck_meta, ensure_ascii=False)
        db.commit()

    yield _sse(
        "done",
        {
            "reply": reply,
            "tool_results": agent_run.tool_results,
            "pending_actions": [
                pending_action_response(db, action).model_dump(mode="json")
                for action in pending
            ],
            "reached_limit": agent_run.reached_limit,
            "cancelled": interrupted,
            # 阶段 2：本次 run 累计 usage + 耗时（provider 不回 usage 时 total_tokens=0，前端不展示）
            "usage": agent_run.usage,
            "elapsed_ms": elapsed_ms,
            # 阶段 3：思维链（provider 已给出的，非空才下发；前端折叠展示）
            "reasoning": agent_run.reasoning or "",
        },
    )
    logger.info(
        "_stream_agent_run done rid=%s conv=%s interrupted=%s elapsed_ms=%s tokens=%s pending=%d",
        rid, conversation.id, interrupted, elapsed_ms,
        (agent_run.usage or {}).get("total_tokens", 0), len(pending),
    )


@router.post("/chat/stream")
async def chat_stream(payload: AIChatRequest, request: Request):
    """SSE 流式版 /ai/chat：事件协议见 CODING_PLAN_AGENT_UX.md 阶段 4。

    返回 StreamingResponse(text/event-stream)；用独立 DB 会话（StreamingResponse
    生命周期长于请求依赖）。client 断开时 httpx stream 自然中止，已累积部分会落库为 interrupted 消息。
    """
    db = SessionLocal()
    try:
        config = ai_config_service.get_enabled_config(db)
        if config is None:
            return StreamingResponse(
                iter([_sse("error", {"message": "未启用 AI 配置", "fatal": True})]),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        conversation, user_text, messages = _prepare_chat_context(
            db, payload.message, payload.attachments, payload.conversation_id
        )
        assistant_name = ai_prompt_service.resolve_assistant_name(db, config)
        # 提前 commit 会话/用户消息，确保 stream 消费前已落库
        db.commit()
        # 阶段 B3：长会话压缩（超阈值把旧消息压成摘要，失败静默降级，不阻断流式）
        messages = await _apply_compaction(db, conversation, config, messages)
    except Exception as exc:
        db.close()
        return StreamingResponse(
            iter([_sse("error", {"message": provider_failure_detail("初始化", exc), "fatal": True})]),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    run_id = uuid4().hex
    cancel_event = _register_run(run_id)
    logger.info("chat_stream 端点 run=%s conv=%s provider=%s", run_id, conversation.id, config.provider)

    async def event_source():
        try:
            async for chunk in _stream_agent_run(
                db, config, conversation, user_text, messages, assistant_name,
                run_id=run_id, cancelled=cancel_event, max_steps=payload.max_steps,
                mode=payload.mode or "chat",
            ):
                if await request.is_disconnected():
                    logger.info("chat_stream 客户端断开 run=%s（前端已停止）", run_id)
                    break
                yield chunk
        finally:
            _release_run(run_id)
            db.close()

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat/resume/stream")
async def resume_chat_stream(payload: AIChatResumeRequest, request: Request):
    """SSE 流式版 /ai/chat/resume：续跑 agent 循环并流式产出。

    与 JSON 版语义一致：找最后一条 meta.resume，pending 全结案才续跑，否则发 done{resumed:false}。
    """
    db = SessionLocal()
    try:
        config = ai_config_service.get_enabled_config(db)
        if config is None:
            return StreamingResponse(
                iter([_sse("error", {"message": "未启用 AI 配置", "fatal": True})]),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        conversation = db.get(AIConversation, payload.conversation_id)
        if conversation is None:
            return StreamingResponse(
                iter([_sse("error", {"message": "AI 会话不存在", "fatal": True})]),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        assistant_name = ai_prompt_service.resolve_assistant_name(db, config)

        resume_msg = (
            db.query(AIMessage)
            .filter(
                AIMessage.conversation_id == conversation.id,
                AIMessage.role == "assistant",
            )
            .order_by(AIMessage.id.desc())
            .first()
        )
        meta = message_meta(resume_msg) if resume_msg else {}
        checkpoint = meta.get("resume")
        if not checkpoint:
            return StreamingResponse(
                iter([_sse("done", {"resumed": False, "waiting": 0})]),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        pending_ids = [_coerce_resume_int(pid) for pid in (checkpoint.get("pending_action_ids") or [])]
        pending_ids = [pid for pid in pending_ids if pid is not None]
        actions = [db.get(AIPendingAction, pid) for pid in pending_ids]
        waiting = [a for a in actions if a and a.status in {"pending", "confirmed"}]
        if waiting:
            return StreamingResponse(
                iter([_sse("done", {"resumed": False, "waiting": len(waiting)})]),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        user_text = str(checkpoint.get("user_text") or "")
        working_messages = _build_resume_working_messages(db, conversation, checkpoint, resume_msg)
        resumed_from_id = resume_msg.id if resume_msg else None
        # 不在此清除 checkpoint：留给 _stream_agent_run 成功落库后清除，
        # provider 失败时保留以便用户重试续跑。
    except Exception as exc:
        db.close()
        return StreamingResponse(
            iter([_sse("error", {"message": provider_failure_detail("初始化", exc), "fatal": True})]),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    run_id = uuid4().hex
    cancel_event = _register_run(run_id)

    async def event_source():
        try:
            async for chunk in _stream_agent_run(
                db, config, conversation, user_text, working_messages, assistant_name,
                resumed=True, resumed_from_id=resumed_from_id,
                run_id=run_id, cancelled=cancel_event, checkpoint_msg=resume_msg,
            ):
                if await request.is_disconnected():
                    break
                yield chunk
        finally:
            _release_run(run_id)
            db.close()

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class AIChatCancelRequest(BaseModel):
    run_id: str


@router.post("/chat/cancel")
def cancel_chat(payload: AIChatCancelRequest):
    """取消进行中的流式 agent run：set 对应 asyncio.Event，循环在下个步边界停止。

    幂等：未知 run_id 返回 ok:false（前端停止按钮无脑调即可，无需判态）。
    """
    event = _active_runs.get(payload.run_id)
    if event is None:
        return {"ok": False, "message": "运行已结束或不存在"}
    event.set()
    return {"ok": True, "message": "已请求中断"}


def _resume_outcome_content(action: AIPendingAction) -> str:
    """根据 pending action 的最终结局，生成回灌给模型的 tool 消息内容。"""
    if action.status == "executed":
        return json.dumps(
            {"ok": True, "executed": True, "message": f"操作已执行：{action.summary}"},
            ensure_ascii=False,
        )
    if action.status == "rejected":
        return json.dumps(
            {
                "ok": False,
                "rejected": True,
                "error": "用户拒绝了该操作，请不要重试同一操作",
            },
            ensure_ascii=False,
        )
    if action.status == "expired":
        return json.dumps(
            {"ok": False, "error": "操作已过期未确认"}, ensure_ascii=False
        )
    # 兜底（理论上不会到这里）
    return json.dumps({"ok": False, "error": f"操作状态异常：{action.status}"}, ensure_ascii=False)


def _build_resume_working_messages(
    db: Session,
    conversation: AIConversation,
    checkpoint: dict,
    resume_msg: AIMessage | None,
) -> list[dict]:
    """重建续跑上下文：历史消息（仅 content，保守不展开历史 tool 链避免孤儿消息）
    + checkpoint 尾部（assistant tool_calls + tool 消息，按结局替换 + 暂缓 safe 补执行）。

    关键：携带 checkpoint 的 assistant 消息本身已在历史中（仅 content），必须从历史切片剔除，
    否则会出现「assistant(content) + assistant(content+tool_calls)」连续两条 assistant 消息，
    Claude 等协议会拒绝，且语义错误。checkpoint 尾部会以带 tool_calls 的形态重新追加。
    """
    history = (
        db.query(AIMessage)
        .filter(AIMessage.conversation_id == conversation.id)
        .order_by(AIMessage.id)
        .all()
    )
    resume_msg_id = resume_msg.id if resume_msg is not None else None
    # 续跑产生的新 assistant 消息尚未落库；历史取 user/assistant 的 content（保守策略），
    # 并剔除 checkpoint 消息自身（由尾部带 tool_calls 重建，避免重复 assistant 消息）。
    messages = [
        {"role": m.role, "content": m.content}
        for m in history
        if m.role in {"user", "assistant"}
        and m.content
        and m.id != resume_msg_id
    ][-20:]

    # checkpoint 尾部：assistant 本轮 tool_calls + tool 结果消息
    assistant_tool_calls = checkpoint.get("assistant_tool_calls") or []
    tool_messages = list(checkpoint.get("tool_messages") or [])

    # 1) 按 checkpoint.pending_action_ids 的结局替换对应 tool 消息内容
    pending_ids = [_coerce_resume_int(pid) for pid in (checkpoint.get("pending_action_ids") or [])]
    action_by_id = {
        action.id: action
        for action in (
            db.get(AIPendingAction, pid) for pid in pending_ids if pid is not None
        )
        if action is not None
    }
    # 建立 call_id → pending action 的映射：assistant_tool_calls 顺序与 tool_messages 顺序一致，
    # dangerous 调用对应 pending action（按 dangerous_actions 落库顺序）。这里用更稳健的方式：
    # 遍历 assistant_tool_calls，对 confirm 类工具/MCP 非免确认工具，按 pending_ids 顺序匹配。
    # 但 checkpoint 已记录 tool_messages 的 call_id，且 pending action 的 tool_result 在 pending 时
    # 写的是 pending 占位。我们用 assistant_tool_calls 的顺序与 pending_ids 顺序对齐（两者同序）。
    pending_idx = 0
    call_id_to_pending: dict[str, AIPendingAction] = {}
    for call in assistant_tool_calls:
        name = str(call.get("name", ""))
        td = tool_registry.get(name)
        is_mcp = name.startswith("mcp__")
        is_dangerous = (td is not None and td.safety == "confirm") or (
            is_mcp and not _resume_mcp_auto_approved(db, name)
        )
        if is_dangerous and pending_idx < len(pending_ids):
            pid = pending_ids[pending_idx]
            if pid is not None and pid in action_by_id:
                call_id_to_pending[str(call.get("id", ""))] = action_by_id[pid]
            pending_idx += 1

    # 2) 暂缓的 safe 工具：补执行，用真实结果替换 pending 占位内容
    paused_calls = checkpoint.get("paused_tool_calls") or []
    skip_signatures = set()  # 续跑首轮不复用主循环的 skip 集合
    paused_results_by_call_id: dict[str, dict] = {}
    for call in paused_calls:
        outcome = _dispatch_native_tool_call(
            db,
            call,
            skip_signatures,
            str(checkpoint.get("assistant_text") or ""),
        )
        paused_results_by_call_id[str(call.get("id", ""))] = outcome["tool_result"]

    # 3) 组装最终 tool_messages：dangerous 用结局替换，paused safe 用补执行结果替换
    resolved_tool_messages: list[dict] = []
    for msg in tool_messages:
        call_id = str(msg.get("tool_call_id", ""))
        new_msg = dict(msg)
        if call_id in call_id_to_pending:
            new_msg["content"] = _resume_outcome_content(call_id_to_pending[call_id])
        elif call_id in paused_results_by_call_id:
            result = paused_results_by_call_id[call_id]
            payload = json.dumps(result.get("result", {}), ensure_ascii=False, default=str)
            if len(payload) > AGENT_OBSERVATION_CHAR_LIMIT:
                payload = payload[:AGENT_OBSERVATION_CHAR_LIMIT] + "...[已截断]"
            new_msg["content"] = payload
        resolved_tool_messages.append(new_msg)

    messages.extend(
        [
            *compact_attachments_for_followup(messages),
            {
                "role": "assistant",
                "content": str(checkpoint.get("assistant_text") or ""),
                "tool_calls": assistant_tool_calls,
            },
            *resolved_tool_messages,
        ]
    )
    return messages


def _coerce_resume_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resume_mcp_auto_approved(db: Session, namespaced_name: str) -> bool:
    parsed = mcp_service.parse_namespaced(namespaced_name)
    if parsed is None:
        return False
    server_id, _ = parsed
    return mcp_service.is_auto_approved(db, server_id, namespaced_name)


@router.post("/chat/resume", response_model=AIChatResponse)
async def resume_chat(payload: AIChatResumeRequest, db: Session = Depends(get_db)):
    """确认/拒绝后续跑：找到该会话最后一条带 meta.resume 的 assistant 消息，
    若其 pending_action_ids 全部结案则续跑 agent 循环，否则返回 resumed:false。

    幂等：续跑成功后清除原 checkpoint；无 checkpoint 或仍在等待时返回 resumed:false，前端静默。
    """
    config = ai_config_service.get_enabled_config(db)
    if config is None:
        raise HTTPException(status_code=400, detail="未启用 AI 配置")

    conversation = db.get(AIConversation, payload.conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="AI 会话不存在")

    # 找最后一条带 resume checkpoint 的 assistant 消息
    resume_msg = (
        db.query(AIMessage)
        .filter(
            AIMessage.conversation_id == conversation.id,
            AIMessage.role == "assistant",
        )
        .order_by(AIMessage.id.desc())
        .first()
    )
    meta = message_meta(resume_msg) if resume_msg else {}
    checkpoint = meta.get("resume")
    if not checkpoint:
        return AIChatResponse(
            conversation_id=conversation.id,
            assistant_name=ai_prompt_service.resolve_assistant_name(db, config),
            reply="",
            resumed=False,
        )

    pending_ids = [_coerce_resume_int(pid) for pid in (checkpoint.get("pending_action_ids") or [])]
    pending_ids = [pid for pid in pending_ids if pid is not None]
    actions = [db.get(AIPendingAction, pid) for pid in pending_ids]
    waiting = [a for a in actions if a and a.status in {"pending", "confirmed"}]
    if waiting:
        return AIChatResponse(
            conversation_id=conversation.id,
            assistant_name=ai_prompt_service.resolve_assistant_name(db, config),
            reply="",
            resumed=False,
        )

    # 重建续跑上下文并续跑
    user_text = str(checkpoint.get("user_text") or "")
    working_messages = _build_resume_working_messages(db, conversation, checkpoint, resume_msg)
    try:
        agent_run = await run_agent_loop(
            db, config, working_messages, user_text, conversation_id=conversation.id
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=provider_failure_detail("续跑模型请求", exc)
        ) from exc

    pending = _materialize_pending_actions(
        db, conversation.id, agent_run.final_plan["dangerous_actions"]
    )
    reply = _compose_assistant_reply(agent_run, agent_run.tool_results)

    # 清除原 checkpoint（续跑已消费），避免重复续跑
    meta.pop("resume", None)
    if resume_msg is not None:
        resume_msg.meta = json.dumps(meta, ensure_ascii=False)

    _persist_assistant_run(
        db, conversation, agent_run, reply, pending,
        resumed_from_id=resume_msg.id if resume_msg else None,
    )

    return AIChatResponse(
        conversation_id=conversation.id,
        assistant_name=ai_prompt_service.resolve_assistant_name(db, config),
        reply=reply,
        tool_results=agent_run.tool_results,
        pending_actions=[pending_action_response(db, action) for action in pending],
        resumed=True,
        usage=agent_run.usage,
    )


# ---- 阶段 C1：Plan Mode 批准/拒绝 ----


def _load_plan_card_message(db: Session, message_id: int) -> AIMessage | None:
    """找到带 plan_card 的 assistant 消息；校验存在且计划仍为 pending。"""
    msg = db.get(AIMessage, message_id)
    if msg is None:
        return None
    try:
        meta = json.loads(msg.meta or "{}")
    except (TypeError, ValueError):
        return None
    pc = meta.get("plan_card")
    if not isinstance(pc, dict):
        return None
    return msg


def _prepare_plan_approve_context(db: Session, message_id: int, steps_payload) -> tuple:
    """阶段 FU-2.1：approve 的共享前置——加载 plan 卡片、标记 approved、构造执行指令、准备会话上下文。

    返回 (config, conversation, user_text, messages) 或在配置/计划缺失时抛 HTTPException。
    steps_payload 为 None 时用原始 steps；非 None 时用用户编辑后的 steps。
    """
    config = ai_config_service.get_enabled_config(db)
    if config is None:
        raise HTTPException(status_code=400, detail="未启用 AI 配置")
    msg = _load_plan_card_message(db, message_id)
    if msg is None:
        raise HTTPException(status_code=404, detail="计划消息不存在或不含计划卡片")
    # 防重复批准：已 approved/rejected 的计划不再执行
    try:
        meta = json.loads(msg.meta or "{}")
    except (TypeError, ValueError):
        meta = {}
    pc = meta.get("plan_card") or {}
    if pc.get("status") in {"approved", "rejected"}:
        raise HTTPException(status_code=409, detail=f"计划已{ '批准' if pc.get('status') == 'approved' else '拒绝' }，不可重复操作")
    # 用户可编辑 steps；否则用原始 steps（统一成 dict 列表）
    if steps_payload:
        steps = [s.model_dump() for s in steps_payload]
    else:
        steps = [dict(s) for s in (pc.get("steps") or [])]
    # 标记计划已批准（防止重复批准）
    pc["status"] = "approved"
    meta["plan_card"] = pc
    msg.meta = json.dumps(meta, ensure_ascii=False)
    db.commit()
    # 构造执行指令注入会话
    lines = [f"- {s.get('action', '')}（工具：{s.get('tool', '')}）" for s in steps]
    instruction = (
        f"请按以下已批准的计划执行（共 {len(steps)} 步）：\n" + "\n".join(lines)
        + "\n\n请逐步执行，涉及写操作时正常走确认流程。"
    )
    conversation, user_text, messages = _prepare_chat_context(
        db, instruction, [], msg.conversation_id
    )
    return config, conversation, user_text, messages


@router.post("/plan/{message_id}/approve", response_model=AIChatResponse)
async def approve_plan(message_id: int, payload: AIPlanApproveRequest, db: Session = Depends(get_db)):
    """批准计划（非流式，降级通道）：把（用户可编辑的）steps 作为新用户指令注入会话，
    切回 chat 模式复跑 agent 循环。流式版见 /plan/{message_id}/approve/stream。

    不直接执行 steps——而是构造一条明确的「按以下计划执行：…」用户消息，让 agent 在 chat 模式下
    正常调用写工具（走既有的 confirm 闸门）。这样计划执行复用全部既有安全不变量。
    """
    config, conversation, user_text, messages = _prepare_plan_approve_context(
        db, message_id, payload.steps
    )
    messages = await _apply_compaction(db, conversation, config, messages)
    try:
        agent_run = await run_agent_loop(
            db, config, messages, user_text, conversation_id=conversation.id, mode="chat",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=provider_failure_detail("计划执行", exc)
        ) from exc
    pending = _materialize_pending_actions(
        db, conversation.id, agent_run.final_plan["dangerous_actions"]
    )
    reply = _compose_assistant_reply(agent_run, agent_run.tool_results)
    _persist_assistant_run(db, conversation, agent_run, reply, pending)
    db.commit()
    return AIChatResponse(
        conversation_id=conversation.id,
        assistant_name=ai_prompt_service.resolve_assistant_name(db, config),
        reply=reply,
        tool_results=agent_run.tool_results,
        pending_actions=[pending_action_response(db, action) for action in pending],
        usage=agent_run.usage,
    )


@router.post("/plan/{message_id}/approve/stream")
async def approve_plan_stream(message_id: int, payload: AIPlanApproveRequest, request: Request):
    """阶段 FU-2.1：批准计划的 SSE 流式版。

    复用 approve 的前置逻辑（_prepare_plan_approve_context），执行段改调 _stream_agent_run，
    SSE 事件词汇与 /ai/chat/stream 完全一致（同一套前端 onEvent 消费端）。
    客户端断开时 httpx stream 自然中止，已累积部分落库为 interrupted 消息。
    """
    db = SessionLocal()
    try:
        config, conversation, user_text, messages = _prepare_plan_approve_context(
            db, message_id, payload.steps
        )
        assistant_name = ai_prompt_service.resolve_assistant_name(db, config)
        db.commit()
        messages = await _apply_compaction(db, conversation, config, messages)
    except HTTPException as exc:
        db.close()
        return StreamingResponse(
            iter([_sse("error", {"message": exc.detail, "fatal": True})]),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    except Exception as exc:
        db.close()
        return StreamingResponse(
            iter([_sse("error", {"message": provider_failure_detail("计划执行初始化", exc), "fatal": True})]),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    run_id = uuid4().hex
    cancel_event = _register_run(run_id)
    logger.info("plan_approve_stream 端点 run=%s conv=%s", run_id, conversation.id)

    async def event_source():
        try:
            async for chunk in _stream_agent_run(
                db, config, conversation, user_text, messages, assistant_name,
                run_id=run_id, cancelled=cancel_event, mode="chat",
            ):
                if await request.is_disconnected():
                    logger.info("plan_approve_stream 客户端断开 run=%s", run_id)
                    break
                yield chunk
        finally:
            _release_run(run_id)
            db.close()

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/plan/{message_id}/reject")
def reject_plan(message_id: int, payload: AIPlanRejectRequest, db: Session = Depends(get_db)):
    """拒绝计划：标记计划为 rejected，记录理由。不执行任何步骤。"""
    msg = _load_plan_card_message(db, message_id)
    if msg is None:
        raise HTTPException(status_code=404, detail="计划消息不存在或不含计划卡片")
    try:
        meta = json.loads(msg.meta or "{}")
    except (TypeError, ValueError):
        meta = {}
    pc = meta.get("plan_card") or {}
    pc["status"] = "rejected"
    if payload.reason:
        pc["reject_reason"] = payload.reason[:200]
    meta["plan_card"] = pc
    msg.meta = json.dumps(meta, ensure_ascii=False)
    db.commit()
    return {"ok": True, "status": "rejected", "message_id": message_id}


# ---- 阶段 D1：工具「始终允许」授权管理 ----


@router.get("/grants", response_model=list[AIToolGrantResponse])
def list_grants(db: Session = Depends(get_db)):
    """列出所有授权规则（设置面板授权管理页用）。"""
    return ai_grant_service.list_grants(db)


@router.post("/grants", response_model=AIToolGrantResponse, status_code=status.HTTP_201_CREATED)
def create_grant(payload: AIToolGrantCreate, db: Session = Depends(get_db)):
    """创建一条「始终允许」规则。确认卡片「以后都允许」勾选时调用。"""
    return ai_grant_service.create_grant(db, payload.tool_name, payload.arg_pattern)


@router.delete("/grants/{grant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_grant(grant_id: int, db: Session = Depends(get_db)):
    """删除一条授权规则。"""
    if not ai_grant_service.delete_grant(db, grant_id):
        raise HTTPException(status_code=404, detail="授权规则不存在")
    return None


# ---- AI 日报/周报 ----
@router.post("/reports/generate", response_model=AIReportResponse)
async def generate_report(
    payload: AIReportGenerateRequest, db: Session = Depends(get_db)
):
    config = ai_config_service.get_enabled_config(db)
    if config is None:
        raise HTTPException(status_code=400, detail="未启用 AI 配置")
    try:
        return await ai_report_service.generate_report(
            db, config, payload.report_type, payload.target_date
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=provider_failure_detail("生成报告", exc)
        ) from exc


@router.post("/autopilot/run")
async def autopilot_run(db: Session = Depends(get_db)):
    """秘书自动档：每天一次，AI 主动排程 + 拆解（需知时代理模式 + 功能管理开启 + AI 配置）。"""
    if ai_prompt_service.assistant_mode(db) != "agent":
        raise HTTPException(status_code=403, detail="秘书自动档是「知时代理」专属能力，请在助手中切换到知时代理")
    if not app_setting_service.feature_enabled(db, "feature_autopilot_enabled"):
        raise HTTPException(status_code=403, detail="秘书自动档未开启，可在功能管理中开启")
    config = ai_config_service.get_enabled_config(db)
    if config is None:
        return {"ran": False, "reason": "未启用 AI 配置", "actions": [], "message": ""}
    return await autopilot_service.run_autopilot(db, config)


@router.get("/briefing/today", response_model=AIReportResponse)
async def briefing_today(db: Session = Depends(get_db)):
    """每日晨报：当天幂等；有 AI 配置用模型生成，否则降级为规则文案。"""
    config = ai_config_service.get_enabled_config(db)
    report, _created = await ai_report_service.get_or_create_briefing(db, config)
    return report


@router.get("/reports", response_model=list[AIReportResponse])
def list_reports(
    report_type: str | None = Query(default=None), db: Session = Depends(get_db)
):
    return ai_report_service.list_reports(db, report_type)


@router.get("/reports/{report_id}", response_model=AIReportResponse)
def get_report(report_id: int, db: Session = Depends(get_db)):
    report = ai_report_service.get_report(db, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    return report


@router.delete("/reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report(report_id: int, db: Session = Depends(get_db)):
    if not ai_report_service.delete_report(db, report_id):
        raise HTTPException(status_code=404, detail="报告不存在")
