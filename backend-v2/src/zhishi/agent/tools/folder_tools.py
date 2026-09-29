"""对话文件夹工具：AI 只读访问当前会话附加的本地文件夹（附加即读取授权，移除即撤销）。
全部 ToolSpec(feature_flag=FOLDER_FLAG) 门控（settingsvc.DEFAULTS 默认开），不进 CORE_TOOLS，
靠 search_tools 发现。错误一律返回 {"ok": false, "error": …} JSON，不 raise（session_tools 风格）。"""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from zhishi.agent.tools.registry import ToolSpec, register
from zhishi.domain import folder_files
from zhishi.domain.folder_files import FolderPathError
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


def _err(message: str) -> str:
    """工具错误统一 JSON（不 raise，session_tools 风格）。"""
    return json.dumps({"ok": False, "error": message}, ensure_ascii=False)


def _resolve_folder(db: Session, ctx, folder: str):
    """把 folder 参数（label 精确优先，否则 root_path 子串）解析为当前会话的唯一附加根。
    返回 (row, None) 或 (None, 错误 JSON)；歧义报候选清单，磁盘目录已删给移除提示。"""
    cid = _cid(ctx)
    if cid is None:
        return None, _err("没有当前会话上下文")
    rows = list(db.scalars(select(AIConversationFolder)
                           .where(AIConversationFolder.conversation_id == cid)
                           .order_by(AIConversationFolder.id)))
    if not rows:
        return None, _err("当前对话尚未附加本地文件夹；请提示用户在会话中附加文件夹（附加即读取授权）后再试")
    exact = [r for r in rows if r.label == folder]
    if len(exact) == 1:
        row = exact[0]
    else:
        hits = [r for r in rows if folder and folder in r.root_path]
        if len(hits) != 1:
            listing = "；".join(f"{r.label} → {r.root_path}" for r in rows)
            return None, _err(f"folder 参数「{folder}」无法唯一解析（{'多' if len(hits) > 1 else '零'}命中），"
                              f"当前附加：{listing}；请用完整 label 或 root_path 再试")
        row = hits[0]
    if not Path(row.root_path).is_dir():
        return None, _err(f"文件夹已不存在（{row.root_path}），可让用户在输入区移除该附件后再试")
    return row, None


def list_folder_files(db: Session, folder: str, subdir: str = "", page: int = 1, ctx=None) -> str:
    """列附加文件夹的目录内容（文件与子目录、大小），500 条/页。"""
    row, err = _resolve_folder(db, ctx, folder)
    if err:
        return err
    try:
        folder_files.resolve_under_root(Path(row.root_path), subdir)
        data = folder_files.list_entries(Path(row.root_path), subdir, page)
    except FolderPathError:
        return _err(f"subdir 越权：只允许附加根（{row.root_path}）内的相对路径")
    except OSError as exc:
        return _err(f"列目录失败：{exc}")
    return json.dumps({"ok": True, "folder": row.label, **data,
                       "note": "条目含子目录（is_dir=true）；把 rel_path 传入 subdir 只看该子树，"
                               "用 read_folder_file 读取文件。"},
                      ensure_ascii=False)


def read_folder_file(db: Session, folder: str, path: str, start_line: int = 1,
                     max_lines: int = 200, ctx=None) -> str:
    """读附加文件夹内一个文件的文本（永远实时读磁盘）：按行分页，默认 200 行、上限 500。"""
    row, err = _resolve_folder(db, ctx, folder)
    if err:
        return err
    rel = (path or "").strip()
    if not rel:
        return _err("path 不能为空；填相对根目录的文件路径，可先用 list_folder_files 查看")
    try:
        target = folder_files.resolve_under_root(Path(row.root_path), rel)
    except FolderPathError:
        return _err(f"path 越权：只允许附加根（{row.root_path}）内的相对路径")
    if not target.is_file():
        return _err(f"文件不存在或不是普通文件：{rel}（目录用 list_folder_files 查看）")
    ext = target.suffix.lower()
    if ext in folder_files.BINARY_EXTS:
        return _err(f"{rel} 是二进制/媒体文件（{ext}），无法按文本读取")
    if ext in folder_files.READ_DOC_EXTS:
        # 文档走 parse_file 纯内存解析，绝不写 sidecar
        try:
            text = folder_files.read_doc_markdown(target)
        except Exception as exc:   # 解析库对损坏/加密文档可能抛任意异常；红线：工具不 raise
            return _err(f"文档解析失败：{exc}")
        return json.dumps({"ok": True, "rel_path": rel, "kind": "document", "content": text,
                           "next_call": None,
                           "note": "文档已整体解析为 Markdown 返回，无需翻页；扫描版 PDF 无文本层时内容里有说明。"},
                          ensure_ascii=False)
    try:
        text = folder_files.read_text_bounded(target)
    except folder_files.FileTooLargeError as exc:
        return _err(str(exc))
    except OSError as exc:   # 权限拒绝等 OS 错误透传为清晰错误文本
        return _err(f"读取失败：{exc}")
    lines = text.splitlines()
    total = len(lines)
    max_lines = max(1, min(int(max_lines or folder_files.MAX_LINES_DEFAULT), folder_files.MAX_LINES_LIMIT))
    start = max(1, int(start_line or 1))
    end = min(total, start + max_lines - 1)
    return json.dumps({"ok": True, "rel_path": rel,
                       "start_line": start, "end_line": end, "total_lines": total,
                       "content": "\n".join(lines[start - 1:end]),
                       "next_call": {"tool": "read_folder_file",
                                     "args": {"folder": folder, "path": rel,
                                              "start_line": end + 1, "max_lines": max_lines}}
                       if end < total else None,
                       "note": "按行分页实时读取；需要后面的行时按 next_call 续读，不把开头当作全文。"},
                      ensure_ascii=False)


_FOLDER_SPECS = [
    ToolSpec("list_folders", list_folders.__doc__ or "", "readonly", FOLDER_FLAG, list_folders),
    ToolSpec("list_folder_files", list_folder_files.__doc__ or "", "readonly", FOLDER_FLAG,
             list_folder_files),
    ToolSpec("read_folder_file", read_folder_file.__doc__ or "", "readonly", FOLDER_FLAG,
             read_folder_file),
]


def _install() -> None:
    for spec in _FOLDER_SPECS:
        register(spec)


_install()
