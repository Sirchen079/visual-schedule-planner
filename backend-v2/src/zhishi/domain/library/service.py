# src/zhishi/domain/library/service.py
"""资料库：文件落盘（防重名）+ 链接资源 + 任务关联 + 回收站。
extracted_text/parse_status 由 M3 解析管道回填，本层只留列。"""
from __future__ import annotations
import hashlib
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from zhishi.domain.models import LibraryFile, Task
from zhishi.domain.library.schemas import LinkCreate

_SAFE = re.compile(r"[^\w.\-\u4e00-\u9fff]+")


def _safe_name(filename: str) -> str:
    return _SAFE.sub("_", filename).strip("_") or "file"


def _unique_path(storage_root: Path, filename: str) -> Path:
    storage_root.mkdir(parents=True, exist_ok=True)
    safe = _safe_name(filename)
    stem, dot, ext = safe.rpartition(".")
    digest = uuid.uuid4().hex
    return storage_root / f"{stem[:100]}_{digest}.{ext[:20]}" if dot else storage_root / f"{safe[:100]}_{digest}"


def save_upload(db: Session, *, storage_root: Path, upload: UploadFile, notes: str = "") -> LibraryFile:
    data = upload.file.read()
    path = _unique_path(storage_root, upload.filename or "unnamed")
    path.write_bytes(data)
    row = LibraryFile(original_name=upload.filename or "unnamed",
                      storage_path=str(path.relative_to(storage_root.parent)),
                      size=len(data), mime_type=upload.content_type or "application/octet-stream",
                      content_sha256=hashlib.sha256(data).hexdigest(),
                      notes=notes)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def save_local_file(db: Session, *, storage_root: Path, source: Path, notes: str = "") -> LibraryFile:
    path = _unique_path(storage_root, source.name)
    data = source.read_bytes()
    path.write_bytes(data)
    row = LibraryFile(original_name=source.name,
                      storage_path=str(path.relative_to(storage_root.parent)),
                      size=len(data), content_sha256=hashlib.sha256(data).hexdigest(), notes=notes)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def save_link(db: Session, **fields) -> LibraryFile:
    """字段即 LinkCreate 字段（title/url/notes/resource_type）。"""
    payload = LinkCreate(**fields)
    if not payload.url.startswith(("http://", "https://")):
        raise ValueError("链接必须以 http(s):// 开头")
    row = LibraryFile(original_name=payload.title, storage_path=payload.url, size=0,
                      mime_type="text/uri-list", notes=payload.notes,
                      source_url=payload.url, resource_type=payload.resource_type)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_files(db: Session, q: str | None = None) -> list[LibraryFile]:
    stmt = select(LibraryFile).where(LibraryFile.deleted_at.is_(None))
    if q:
        stmt = stmt.where(LibraryFile.original_name.contains(q))
    return list(db.scalars(stmt.order_by(LibraryFile.uploaded_at.desc())))


def get_file(db: Session, file_id: int) -> LibraryFile:
    row = db.get(LibraryFile, file_id)
    if row is None or row.deleted_at is not None:
        raise LookupError(f"file {file_id} 不存在")
    return row


def list_trash(db: Session) -> list[LibraryFile]:
    return list(db.scalars(select(LibraryFile).where(LibraryFile.deleted_at.is_not(None))
                           .order_by(LibraryFile.deleted_at.desc())))


def soft_delete(db: Session, file_id: int) -> None:
    get_file(db, file_id).deleted_at = datetime.now()
    db.commit()


def restore(db: Session, file_id: int) -> LibraryFile:
    row = db.get(LibraryFile, file_id)  # 回收站流程：文件已软删，须含已删行
    if row is None:
        raise LookupError(f"file {file_id} 不存在")
    row.deleted_at = None
    db.commit()
    db.refresh(row)
    return row


def purge(db: Session, file_id: int, *, storage_root: Path | None = None) -> None:
    row = db.get(LibraryFile, file_id)  # 回收站流程：文件已软删，须含已删行
    if row is None:
        raise LookupError(f"file {file_id} 不存在")
    if storage_root is not None and row.resource_type == "file":
        target = storage_root.parent / row.storage_path
        target.unlink(missing_ok=True)
    # M3：先解除任务关联（FK 开启下直接删文件会被 task_file 阻断）；
    # 走集合 remove 保持 ORM 关联行删除与内存一致
    for t in db.scalars(select(Task).where(Task.files.any(LibraryFile.id == file_id))):
        t.files.remove(row)
    db.delete(row)
    db.commit()


def attach_to_task(db: Session, task_id: int, file_id: int) -> None:
    task = db.get(Task, task_id)
    file = get_file(db, file_id)
    if task is None or task.deleted_at is not None:
        raise LookupError(f"task {task_id} 不存在")
    if file not in task.files:
        task.files.append(file)
        db.commit()


def detach_from_task(db: Session, task_id: int, file_id: int) -> None:
    task = db.get(Task, task_id)
    if task is None:
        raise LookupError(f"task {task_id} 不存在")
    file = db.get(LibraryFile, file_id)
    if file in task.files:
        task.files.remove(file)
        db.commit()


def update_notes(db: Session, file_id: int, notes: str) -> LibraryFile:
    row = get_file(db, file_id)
    row.notes = notes
    db.commit()
    db.refresh(row)
    return row


def list_task_files(db: Session, task_id: int) -> list[LibraryFile]:
    task = db.scalar(select(Task).where(Task.id == task_id).options(selectinload(Task.files)))
    return list(task.files) if task else []


def ensure_parsed(db: Session, file: LibraryFile, *, storage_root: Path) -> "ParsedDoc":
    """解析一次持久化（extracted_text=ParsedDoc JSON），后续零成本读取。
    image→needs_vision；unsupported→failed（附可读原因）；解析异常→failed。"""
    from zhishi.adapters.parsers import PARSER_VERSION, ParsedDoc, parse_file
    if file.parse_status in ('parsed', 'needs_vision') and file.extracted_text and (file.content_sha256 or file.resource_type != 'file'):
        cached = json.loads(file.extracted_text)
        if cached.get('parser_version') == PARSER_VERSION or file.parse_status == 'needs_vision':
            return ParsedDoc(**cached)
    path = (storage_root.parent / file.storage_path).resolve() if file.resource_type == 'file' else None
    if path is not None and not path.is_relative_to(storage_root.resolve()):
        raise ValueError('附件路径不在资料目录内')
    if not file.content_sha256 and file.resource_type == "file":
        # Old v2 attachments are fingerprinted lazily when actually read, not at startup.
        root = storage_root.resolve()
        path = (storage_root.parent / file.storage_path).resolve()
        if not path.is_relative_to(root):
            raise ValueError("附件路径不在资料目录内")
        if path.is_file():
            file.content_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
            db.commit()
    if file.parse_status in ("parsed", "needs_vision") and file.extracted_text:
        data = json.loads(file.extracted_text)
        if data.get('parser_version') == PARSER_VERSION or file.parse_status == 'needs_vision':
            return ParsedDoc(**data)
        if path is None or not path.is_file():
            data.update(partial=True, warnings=['旧缓存可能只包含开头摘要，不能当作完整原文。'])
            return ParsedDoc(**data)
        # Old local caches had irreversible 5-page/30k limits: rebuild lazily from the original.
    if path is None:
        raise ValueError('该链接尚无正文缓存；请先获取网页正文或上传原文件。')
    try:
        doc = parse_file(path)
    except Exception as exc:  # 解析异常：落 failed 状态并附可读原因
        file.parse_status = "failed"
        file.extracted_text = json.dumps(
            {"kind": "failed", "text": f"解析失败：{exc}", "tables": []}, ensure_ascii=False)
        db.commit()
        raise ValueError(f'无法解析材料：{str(exc)[:500]}') from exc
    if doc.kind == "image":
        file.parse_status, file.extracted_text = "needs_vision", doc.to_json()
    elif doc.kind == "unsupported":
        file.parse_status = "failed"
        file.extracted_text = json.dumps(
            {"kind": "unsupported", "text": "旧版 .doc 等二进制格式暂不支持；请另存为 docx/pdf 后重试",
             "tables": []}, ensure_ascii=False)
    else:
        file.parse_status, file.extracted_text = "parsed", doc.to_json()
    db.commit()
    return doc
