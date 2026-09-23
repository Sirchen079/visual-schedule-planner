"""长期记忆工具：AI 自主读写一条条独立记忆（LLM wiki 模式），用户在设置里可审可改。
全部 ToolSpec(feature_flag='feature_memory_enabled') 门控（settingsvc.DEFAULTS 默认开），
不进 CORE_TOOLS，靠 search_tools 发现。校验失败 raise ModelRetry——错误原文回给模型，
"校验即教学"：拒绝时说清原因和改法，教学话术放这里而非 docstring（省工具 schema 预算）。"""
from __future__ import annotations

import difflib
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from zhishi.agent.tools.registry import ToolSpec, register
from zhishi.domain.models import AIMemory

MEMORY_KINDS = ("profile", "preference", "decision", "fact", "project")
MAX_MEMORY_CHARS = 300
MAX_MEMORIES = 200
SEARCH_LIMIT = 20
# 注入与开关判断共用：>='' 恒真（脏值视为开），仅显式 'false' 关闭
MEMORY_FLAG = "feature_memory_enabled"


def memory_enabled(db: Session) -> bool:
    """长期记忆总开关：缺失视为开（与 feature_enabled 的「缺失=关」语义不同）。"""
    from zhishi.domain import settingsvc

    return settingsvc.get_setting(db, MEMORY_FLAG) != "false"


def _reject(reason: str) -> None:
    from pydantic_ai.exceptions import ModelRetry

    raise ModelRetry(f"记忆未保存，请修正后重新调用：{reason}")


def _check_content(content: str) -> str:
    content = (content or "").strip()
    if not content:
        _reject("content 不能为空；请把要记的事实写成一句完整的话")
    if len(content) > MAX_MEMORY_CHARS:
        _reject(f"content 过长（{len(content)} 字），上限 {MAX_MEMORY_CHARS}；"
                "一条记忆只写一个独立事实，拆成多条分别保存")
    return content


def _check_kind(kind: str) -> str:
    if kind not in MEMORY_KINDS:
        _reject(f"kind 必须是 {'/'.join(MEMORY_KINDS)} 之一；"
                "profile=用户画像 preference=偏好 decision=决定 fact=事实 project=项目背景")
    return kind


def _find_similar(db: Session, content: str, exclude_id: int | None = None) -> AIMemory | None:
    """查重：content 高度相似（含大小写/首尾空白差异）即视为同一条，避免记忆膨胀。"""
    for row in db.scalars(select(AIMemory)).all():
        if exclude_id is not None and row.id == exclude_id:
            continue
        if difflib.SequenceMatcher(None, row.content, content).ratio() >= 0.85:
            return row
    return None


def save_memory(db: Session, kind: str, content: str, keywords: str = "", ctx=None) -> str:
    """记下值得长期记住的一条信息（用户偏好、明确决定、长期事实或项目背景，低风险直写）。
    keywords 填空格分隔的检索词；写入前自动查重，已存在类似记忆会被拒绝。"""
    kind = _check_kind(kind)
    content = _check_content(content)
    similar = _find_similar(db, content)
    if similar is not None:
        _reject(f"已有类似记忆 #{similar.id}：「{similar.content[:80]}」；"
                "信息有变化应改调 update_memory(memory_id, content) 更新该条，不要重复保存")
    total = db.scalar(select(func.count()).select_from(AIMemory)) or 0
    if total >= MAX_MEMORIES:
        _reject(f"记忆总数已达上限 {MAX_MEMORIES}；请先 search_memory 找出过时或重复的条目，"
                "用 update_memory 合并、forget_memory 清理后再保存")
    row = AIMemory(kind=kind, content=content,
                   keywords=(keywords or "").strip(), source="ai",
                   source_conversation_id=getattr(getattr(ctx, "deps", None), "conversation_id", None))
    db.add(row)
    db.commit()
    return json.dumps({"ok": True, "id": row.id, "kind": kind, "total": total + 1,
                       "note": "已记住；同一事实更新时改调 update_memory，不再需要时用 forget_memory 删除。"},
                      ensure_ascii=False)


def update_memory(db: Session, memory_id: int, content: str, keywords: str | None = None) -> str:
    """更新一条已有记忆的内容（过时、用户改了主意时用，低风险直写）。
    keywords 留空表示沿用原检索词；只改内容传新 content 即可。"""
    row = db.get(AIMemory, memory_id)
    if row is None:
        _reject(f"记忆 #{memory_id} 不存在；先 search_memory 或 list 确认真实 id，"
                "id 来自 save_memory/search_memory 的返回")
    content = _check_content(content)
    similar = _find_similar(db, content, exclude_id=memory_id)
    if similar is not None:
        _reject(f"内容与已有记忆 #{similar.id} 高度相似；应 forget_memory 删除其一，不要保留两条重复记忆")
    row.content = content
    if keywords is not None and keywords.strip():
        row.keywords = keywords.strip()
    db.commit()
    return json.dumps({"ok": True, "id": row.id, "updated_at": row.updated_at.isoformat(timespec="seconds"),
                       "note": "已更新，新信息将随下次对话注入。"}, ensure_ascii=False)


def forget_memory(db: Session, memory_id: int) -> str:
    """删除一条不再正确或用户要求忘掉的记忆（物理删除，低风险直写）。
    用户明确要求「忘掉/删掉」某条记忆时使用；信息只是过时优先 update_memory 修正。"""
    row = db.get(AIMemory, memory_id)
    if row is None:
        _reject(f"记忆 #{memory_id} 不存在或已删除；先 search_memory 确认真实 id")
    db.delete(row)
    db.commit()
    return json.dumps({"ok": True, "id": memory_id, "note": "已删除该记忆，后续对话不再注入。"},
                      ensure_ascii=False)


def search_memory(db: Session, query: str) -> str:
    """按关键词检索长期记忆（只读），用于回忆注入块之外的旧信息。
    query 填 1-4 个空格分隔的短关键词（人名/项目名/偏好词），命中按相关度返回。"""
    query = (query or "").strip()
    if not query:
        _reject("query 不能为空；给 1-4 个空格分隔的短关键词，如「导师 论文方向」")
    tokens = query.lower().split()
    scored: list[tuple[int, AIMemory]] = []
    for row in db.scalars(select(AIMemory)).all():
        text = f"{row.keywords} {row.kind} {row.content}".lower()
        hits = sum(1 for t in tokens if t in text)
        if hits:
            scored.append((hits, row))
    scored.sort(key=lambda pair: (-pair[0], -pair[1].updated_at.timestamp()))
    hits = [{"id": r.id, "kind": r.kind, "content": r.content, "updated_at": r.updated_at.isoformat(timespec="seconds")}
            for _, r in scored[:SEARCH_LIMIT]]
    return json.dumps({"ok": True, "query": query, "count": len(hits), "memories": hits,
                       "note": "没有命中不代表没有相关记忆，可换关键词再试。" if not hits else ""},
                      ensure_ascii=False)


def recent_memories(db: Session, limit: int = 30) -> list[AIMemory]:
    """按 updated_at 取最近 limit 条记忆（prompts 注入块与设置页共用）。"""
    return list(db.scalars(select(AIMemory).order_by(AIMemory.updated_at.desc(), AIMemory.id.desc())
                           .limit(limit)).all())


def memory_count(db: Session) -> int:
    """记忆总数（注入块判断是否提示可检索、设置页展示用）。"""
    return db.scalar(select(func.count()).select_from(AIMemory)) or 0


_MEMORY_SPECS = [
    ToolSpec("save_memory", save_memory.__doc__ or "", "safe", MEMORY_FLAG, save_memory),
    ToolSpec("update_memory", update_memory.__doc__ or "", "safe", MEMORY_FLAG, update_memory),
    ToolSpec("forget_memory", forget_memory.__doc__ or "", "safe", MEMORY_FLAG, forget_memory),
    ToolSpec("search_memory", search_memory.__doc__ or "", "readonly", MEMORY_FLAG, search_memory),
]


def _install() -> None:
    for spec in _MEMORY_SPECS:
        register(spec)


_install()
