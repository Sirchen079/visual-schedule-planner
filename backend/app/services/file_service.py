from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.models import File, Task
from app.schemas import FileUpdate

_CHUNK = 1024 * 1024  # 流式读写分块大小


def _safe_name(filename: str) -> str:
    name = Path(filename or "unnamed").name
    # Windows 不允许这些字符出现在文件名中
    for ch in '<>:"/\\|?*':
        name = name.replace(ch, "_")
    return name.strip() or "unnamed"


def save_upload(db: Session, upload: UploadFile, notes: str = "") -> File:
    settings.files_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_name(upload.filename or "unnamed")
    stored_name = f"{int(time.time() * 1000)}-{safe_name}"
    destination = settings.files_dir / stored_name
    limit = settings.max_upload_bytes

    # 流式分块写入，超过大小上限立即中止并清理残留文件
    written = 0
    with destination.open("wb") as out:
        while chunk := upload.file.read(_CHUNK):
            written += len(chunk)
            if written > limit:
                out.close()
                destination.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=f"文件超过上限 {settings.max_upload_mb}MB",
                )
            out.write(chunk)

    db_file = File(
        original_name=safe_name,
        storage_path=str(destination.relative_to(settings.database_dir.parent)),
        size=destination.stat().st_size,
        mime_type=upload.content_type or "application/octet-stream",
        notes=notes,
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)
    return db_file


def list_files(db: Session, q: Optional[str] = None) -> list[File]:
    stmt = select(File).where(File.deleted_at.is_(None)).order_by(File.uploaded_at.desc())
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(or_(File.original_name.like(pattern), File.notes.like(pattern)))
    return list(db.execute(stmt).scalars().all())


def get_file(db: Session, file_id: int) -> Optional[File]:
    stmt = select(File).where(File.id == file_id, File.deleted_at.is_(None))
    return db.execute(stmt).scalar_one_or_none()


def update_file(db: Session, file_id: int, patch: FileUpdate) -> Optional[File]:
    db_file = get_file(db, file_id)
    if db_file is None:
        return None
    for field, value in patch.model_dump(exclude_unset=True).items():
        setattr(db_file, field, value)
    db.commit()
    db.refresh(db_file)
    return db_file


def soft_delete_file(db: Session, file_id: int) -> bool:
    db_file = get_file(db, file_id)
    if db_file is None:
        return False
    db_file.deleted_at = datetime.now()
    db.commit()
    return True


def content_path(db_file: File) -> Path:
    return settings.database_dir.parent / db_file.storage_path


def attach_to_task(db: Session, task_id: int, file_id: int) -> bool:
    task = db.execute(
        select(Task).options(selectinload(Task.files)).where(
            Task.id == task_id, Task.deleted_at.is_(None)
        )
    ).scalar_one_or_none()
    db_file = get_file(db, file_id)
    if task is None or db_file is None:
        return False
    if db_file not in task.files:
        task.files.append(db_file)
        db.commit()
    return True


def detach_from_task(db: Session, task_id: int, file_id: int) -> bool:
    task = db.execute(
        select(Task).options(selectinload(Task.files)).where(
            Task.id == task_id, Task.deleted_at.is_(None)
        )
    ).scalar_one_or_none()
    if task is None:
        return False
    for db_file in list(task.files):
        if db_file.id == file_id:
            task.files.remove(db_file)
            db.commit()
            return True
    return False


def list_task_files(db: Session, task_id: int) -> Optional[list[File]]:
    task = db.execute(
        select(Task).options(selectinload(Task.files)).where(
            Task.id == task_id, Task.deleted_at.is_(None)
        )
    ).scalar_one_or_none()
    if task is None:
        return None
    return [f for f in task.files if f.deleted_at is None]


# ---- 回收站（软删可恢复，超期连同磁盘文件清理） ----

def list_trash(db: Session) -> list[File]:
    stmt = select(File).where(File.deleted_at.is_not(None)).order_by(File.deleted_at.desc())
    return list(db.execute(stmt).scalars().all())


def restore_file(db: Session, file_id: int) -> Optional[File]:
    stmt = select(File).where(File.id == file_id, File.deleted_at.is_not(None))
    db_file = db.execute(stmt).scalar_one_or_none()
    if db_file is None:
        return None
    db_file.deleted_at = None
    db.commit()
    db.refresh(db_file)
    return db_file


def purge_file(db: Session, file_id: int) -> bool:
    """彻底删除回收站文件：删磁盘文件 + 删数据库记录。"""
    db_file = db.get(File, file_id)
    if db_file is None or db_file.deleted_at is None:
        return False
    _remove_disk_file(db_file)
    db.delete(db_file)
    db.commit()
    return True


def purge_expired(db: Session, retain_days: Optional[int] = None) -> int:
    """清理回收站中超过 retain_days 天的文件（含磁盘），返回清理数量。"""
    retain_days = settings.trash_retain_days if retain_days is None else retain_days
    cutoff = datetime.now() - timedelta(days=retain_days)
    rows = list(
        db.execute(
            select(File).where(File.deleted_at.is_not(None), File.deleted_at < cutoff)
        ).scalars().all()
    )
    for f in rows:
        _remove_disk_file(f)
        db.delete(f)
    db.commit()
    return len(rows)


def _remove_disk_file(db_file: File) -> None:
    """删除磁盘上的原始文件，记录还在但内容已清。"""
    path = content_path(db_file)
    path.unlink(missing_ok=True)
