from __future__ import annotations

import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import UploadFile
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.models import File, Task
from app.schemas import FileUpdate


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

    with destination.open("wb") as out:
        shutil.copyfileobj(upload.file, out)

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
