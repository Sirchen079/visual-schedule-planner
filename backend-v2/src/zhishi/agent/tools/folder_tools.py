"""对话文件夹工具：AI 只读访问当前会话附加的本地文件夹（附加即读取授权，移除即撤销）。
全部 ToolSpec(feature_flag=FOLDER_FLAG) 门控（settingsvc.DEFAULTS 默认开），不进 CORE_TOOLS，
靠 search_tools 发现。错误一律返回 {"ok": false, "error": …} JSON，不 raise（session_tools 风格）。"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from zhishi.agent.tools.registry import ToolSpec, register
from zhishi.domain.models import AIConversationFolder

FOLDER_FLAG = "feature_folder_tools_enabled"
# 全部四个工具的最终名单（后续任务逐个注册）；守卫用：整体不进 CORE_TOOLS
FOLDER_TOOLS = {"list_folders", "list_folder_files", "read_folder_file", "search_folder_files"}


def _cid(ctx) -> int | None:
    """当前会话 id（session_tools 同款取法）；无上下文返回 None。"""
    return getattr(getattr(ctx, 'deps', None), 'conversation_id', None)


def list_folders(db: Session, ctx=None) -> str:
    """列当前对话附加的本地文件夹（名称与根路径）。"""
    cid = _cid(ctx)
    if cid is None:
        return json.dumps({"ok": False, "error": "没有当前会话上下文"}, ensure_ascii=False)
    rows = list(db.scalars(select(AIConversationFolder)
                           .where(AIConversationFolder.conversation_id == cid)
                           .order_by(AIConversationFolder.id)))
    if not rows:
        return json.dumps({"ok": False, "folders": [],
                           "error": "当前对话尚未附加本地文件夹；请提示用户在会话中附加文件夹"
                                    "（附加即读取授权，移除即撤销）后再试。"},
                          ensure_ascii=False)
    folders = [{"id": r.id, "label": r.label, "root_path": r.root_path} for r in rows]
    return json.dumps({"ok": True, "conversation_id": cid, "count": len(folders), "folders": folders,
                       "note": "只能读取这些文件夹内的文件；需要新增附加时请用户操作。"},
                      ensure_ascii=False)


_FOLDER_SPECS = [
    ToolSpec("list_folders", list_folders.__doc__ or "", "readonly", FOLDER_FLAG, list_folders),
]


def _install() -> None:
    for spec in _FOLDER_SPECS:
        register(spec)


_install()
