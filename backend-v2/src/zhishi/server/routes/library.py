from datetime import datetime
from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from zhishi.domain.library import service
from zhishi.domain.library.schemas import LinkCreate
from zhishi.server.deps import get_db

router = APIRouter(prefix="/api/files", tags=["library"])


# ---- typed 响应（openapi 从空 schema 变 $ref，字段与实际返回形状一致） ----

class FileOut(BaseModel):
    id: int
    original_name: str
    storage_path: str               # 本地相对路径或内部资源键；链接地址使用 source_url
    size: int
    mime_type: str
    notes: str
    source_url: str | None = None
    resource_type: str              # file/link/video
    parse_status: str               # pending/parsed/failed/needs_vision
    md_status: str = 'none'         # Markdown 副本：none/done/pending（扫描页 OCR 中）/failed
    uploaded_at: datetime


class OkOut(BaseModel):
    ok: bool


@router.post("", status_code=201, response_model=FileOut)
def upload(file: UploadFile, notes: str = Form(""),
           db: Session = Depends(get_db), request: Request = None):
    """上传文件。notes 为 multipart 表单域。"""
    storage_root = request.app.state.storage_root
    row = service.save_upload(db, storage_root=storage_root, upload=file, notes=notes)
    return _file_dict(row)


@router.post("/links", status_code=201, response_model=FileOut)
def create_link(payload: LinkCreate, db: Session = Depends(get_db)):
    try:
        return _file_dict(service.save_link(db, **payload.model_dump()))
    except ValueError as ex:
        raise HTTPException(422, str(ex))


@router.get("", response_model=list[FileOut])
def list_files(q: str | None = None, db: Session = Depends(get_db)):
    return [_file_dict(f) for f in service.list_files(db, q=q)]


@router.get("/trash", response_model=list[FileOut])
def list_trash(db: Session = Depends(get_db)):
    return [_file_dict(f) for f in service.list_trash(db)]


@router.get("/tasks/{task_id}", response_model=list[FileOut])
def task_files(task_id: int, db: Session = Depends(get_db)):
    return [_file_dict(f) for f in service.list_task_files(db, task_id)]


@router.get("/{file_id}", response_model=FileOut)
def get_file(file_id: int, db: Session = Depends(get_db)):
    try:
        return _file_dict(service.get_file(db, file_id))
    except LookupError:
        raise HTTPException(404, "文件不存在")


@router.patch("/{file_id}", response_model=FileOut)
def update_notes(file_id: int, body: dict, db: Session = Depends(get_db)):
    try:
        return _file_dict(service.update_notes(db, file_id, body.get("notes", "")))
    except LookupError:
        raise HTTPException(404, "文件不存在")


@router.delete("/{file_id}", status_code=204)
def soft_delete(file_id: int, db: Session = Depends(get_db)) -> None:
    try:
        service.soft_delete(db, file_id)
    except LookupError:
        raise HTTPException(404, "文件不存在")


@router.post("/{file_id}/restore", response_model=FileOut)
def restore(file_id: int, db: Session = Depends(get_db)):
    try:
        return _file_dict(service.restore(db, file_id))
    except LookupError:
        raise HTTPException(404, "文件不存在")


@router.delete("/{file_id}/purge", status_code=204)
def purge(file_id: int, db: Session = Depends(get_db), request: Request = None) -> None:
    try:
        service.purge(db, file_id, storage_root=request.app.state.storage_root)
    except LookupError:
        raise HTTPException(404, "文件不存在")


@router.post("/{file_id}/reparse", response_model=FileOut)
def reparse(file_id: int, request: Request, db: Session = Depends(get_db)):
    """清除解析缓存重建（Markdown 管道升级或扫描页 OCR 失败后的重试入口）。
    office/文本同步重建；含扫描页的 PDF 重建后交后台 OCR（md_status=pending）。"""
    row = db.get(service.LibraryFile, file_id)
    if row is None or row.deleted_at is not None:
        raise HTTPException(404, "文件不存在")
    if row.resource_type != 'file':
        raise HTTPException(400, "链接资源没有可重建的文件正文")
    row.parse_status, row.extracted_text, row.md_status = 'pending', None, 'none'
    db.commit()
    storage_root = request.app.state.storage_root
    try:
        service.ensure_parsed(db, row, storage_root=storage_root)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"重新解析失败：{str(exc)[:300]}")
    db.refresh(row)
    return _file_dict(row)


@router.post("/{file_id}/attach/{task_id}", response_model=OkOut)
def attach(file_id: int, task_id: int, db: Session = Depends(get_db)):
    try:
        service.attach_to_task(db, task_id, file_id)
    except LookupError:
        raise HTTPException(404, "任务不存在")
    return {"ok": True}


@router.post("/{file_id}/detach/{task_id}", response_model=OkOut)
def detach(file_id: int, task_id: int, db: Session = Depends(get_db)):
    try:
        service.detach_from_task(db, task_id, file_id)
    except LookupError:
        raise HTTPException(404, "任务不存在")
    return {"ok": True}


def _file_dict(f):
    return {"id": f.id, "original_name": f.original_name, "storage_path": f.storage_path,
            "size": f.size, "mime_type": f.mime_type, "notes": f.notes,
            "source_url": f.source_url, "resource_type": f.resource_type,
            "parse_status": f.parse_status, "md_status": getattr(f, 'md_status', 'none') or 'none',
            "uploaded_at": f.uploaded_at}
