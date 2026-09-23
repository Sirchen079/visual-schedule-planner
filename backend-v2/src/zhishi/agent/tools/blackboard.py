"""「黑板」展示工具：AI 生成自包含 HTML 示意页，前端在专属面板用沙箱 iframe 渲染。
纯展示元数据（同 update_work_plan 一类）：安全级 safe，不触碰业务数据；
内容持久化在会话 meta_json['blackboard']，重开会话可恢复。"""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy.orm import Session

from zhishi.agent.tools.registry import ToolSpec, register

MAX_BLACKBOARD_CHARS = 300_000


def show_blackboard(db: Session, html: str, title: str = "", ctx=None) -> str:
    """在「黑板」面板向用户展示一个自包含 HTML 示意页（纯展示，低风险直写）。
    样式脚本全部内联、不引外部资源；每次调用整页替换，title 概括主题。普通 Markdown 别用本工具。"""
    from zhishi.agent.session_store import metadata

    html = (html or "").strip()
    if not html:
        raise ValueError("html 不能为空")
    if len(html) > MAX_BLACKBOARD_CHARS:
        raise ValueError(f"html 过长（{len(html)} 字符），上限 {MAX_BLACKBOARD_CHARS}；请精简或拆分说明")
    title = (title or "").strip() or "AI 黑板"
    value = {"title": title, "html": html, "updated_at": datetime.now().isoformat(timespec="seconds")}
    cid = getattr(getattr(ctx, 'deps', None), 'conversation_id', None)
    if cid is not None:
        from zhishi.domain.models import AIConversation

        conversation = db.get(AIConversation, cid, populate_existing=True)
        if conversation is not None:
            meta = metadata(conversation.meta_json)
            meta['blackboard'] = value
            conversation.meta_json = json.dumps(meta, ensure_ascii=False)
            db.commit()
    emit = getattr(getattr(ctx, 'deps', None), 'emit', None)
    if emit is not None:
        from zhishi.agent.events import BlackboardUpdated

        emit.put_nowait(BlackboardUpdated(title=title, html=html).model_dump())
    return json.dumps({"ok": True, "title": title, "chars": len(html),
                       "note": "已在黑板面板展示；再次调用会整页替换。"}, ensure_ascii=False)


_BLACKBOARD_SPECS = [
    ToolSpec("show_blackboard", show_blackboard.__doc__ or "", "safe", None, show_blackboard),
]


def _install() -> None:
    for spec in _BLACKBOARD_SPECS:
        register(spec)


_install()
