"""工具注册表（单一数据源）：工具名/描述/安全分级/功能开关门控。
工具函数签名：async def fn(ctx: RunContext[AgentDeps], **params) -> str（返回模型可读文本）。
本文件只登记元数据；函数实体在 atomic_read/atomic_write。"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    safety: str          # readonly / safe / confirm（不可豁免高危由 permissions.IRREVOCABLE_TOOLS 表达）
    feature_flag: str | None   # None = 不受功能开关键门控
    fn: Callable


_REGISTRY: list[ToolSpec] = []


def register(spec: ToolSpec) -> None:
    _REGISTRY.append(spec)


def get_spec(name: str) -> ToolSpec | None:
    return next((s for s in _REGISTRY if s.name == name), None)


def specs_for(db) -> list[ToolSpec]:
    """功能开关放行后的完整清单（组装 Agent 时调用）。"""
    from zhishi.domain import settingsvc
    return [s for s in _REGISTRY
            if s.feature_flag is None or settingsvc.feature_enabled(db, s.feature_flag)]


def readonly_names() -> set[str]:
    return {s.name for s in _REGISTRY if s.safety == "readonly"}


REGISTRY = _REGISTRY  # 只读视图；注册发生在 atomic_read/atomic_write import 时
