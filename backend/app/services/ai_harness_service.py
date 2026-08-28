from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from typing import Any


def tool_call_signature(name: str, args: dict[str, Any]) -> str:
    return json.dumps(
        {"name": name, "args": args},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )


def _is_real_failure(result: Any) -> bool:
    """ok=False 且非 pending（待确认不算失败，避免误报与误触重试预算）。"""
    return (
        isinstance(result, dict)
        and result.get("ok") is False
        and not result.get("pending")
    )


def failed_tool_signatures(tool_results: list[dict[str, Any]]) -> Counter[str]:
    signatures: Counter[str] = Counter()
    for item in tool_results:
        result = item.get("result")
        if not _is_real_failure(result):
            continue
        signatures[
            tool_call_signature(str(item.get("tool", "")), dict(item.get("args", {})))
        ] += 1
    return signatures


def failed_retry_budget_message(
    failures: Counter[str],
    tool_results: list[dict[str, Any]],
    retry_limit: int,
) -> str:
    if not failures:
        return ""
    signature, count = failures.most_common(1)[0]
    if count <= retry_limit:
        return ""
    last_error = ""
    for item in reversed(tool_results):
        result = item.get("result")
        if not _is_real_failure(result):
            continue
        current_signature = tool_call_signature(
            str(item.get("tool", "")), dict(item.get("args", {}))
        )
        if current_signature == signature:
            last_error = str(result.get("error") or "")
            break
    detail = f"最近错误：{last_error}" if last_error else "请补充必要信息或调整请求后继续。"
    return f"同一工具调用已超过重试预算（最多允许 {retry_limit} 次修正重试）。{detail}"


def step_observations(step_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    observations = []
    for item in step_results:
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        observations.append(
            {
                "tool": item.get("tool", ""),
                "ok": bool(result.get("ok")),
                "skipped": bool(result.get("skipped")),
                "error": result.get("error"),
                "message": result.get("message"),
            }
        )
    return observations


def build_run_summary(
    *,
    run_id: str,
    objective: str,
    started_at: datetime,
    steps: list[dict[str, Any]],
    final_plan: dict[str, Any],
    tool_results: list[dict[str, Any]],
    done_reason: str,
    stop_message: str,
    max_steps: int,
    retry_limit: int,
) -> dict[str, Any]:
    failures = [
        {
            "tool": item.get("tool", ""),
            "args": item.get("args", {}),
            "error": item["result"].get("error"),
        }
        for item in tool_results
        if _is_real_failure(item.get("result"))
    ]
    return {
        "run_id": run_id,
        "objective": objective,
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "max_steps": max_steps,
        "tool_retry_limit": retry_limit,
        "done_reason": done_reason,
        "stop_message": stop_message,
        "plan": final_plan.get("plan") if isinstance(final_plan.get("plan"), dict) else {},
        "steps": steps,
        "failures": failures,
    }
