from fastapi import APIRouter, Depends, File as UploadFileParam, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse as FastAPIFileResponse
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import FileResponse, FileUpdate
from app.services import file_service

router = APIRouter(tags=["files"])


@router.post("/files", response_model=FileResponse, status_code=status.HTTP_201_CREATED)
def upload_file(
    file: UploadFile = UploadFileParam(...),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    return file_service.save_upload(db, file, notes)


@router.get("/files", response_model=list[FileResponse])
def list_files(q: str | None = None, db: Session = Depends(get_db)):
    return file_service.list_files(db, q)


# 注意：/files/trash 必须在 /files/{file_id} 之前注册
@router.get("/files/trash", response_model=list[FileResponse])
def list_trash_files(db: Session = Depends(get_db)):
    # 惰性清理：访问回收站时顺手清掉超期项（含磁盘文件）
    file_service.purge_expired(db)
    return file_service.list_trash(db)


@router.get("/files/{file_id}", response_model=FileResponse)
def get_file(file_id: int, db: Session = Depends(get_db)):
    db_file = file_service.get_file(db, file_id)
    if db_file is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    return db_file


@router.put("/files/{file_id}", response_model=FileResponse)
def update_file(file_id: int, patch: FileUpdate, db: Session = Depends(get_db)):
    db_file = file_service.update_file(db, file_id, patch)
    if db_file is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    return db_file


@router.get("/files/{file_id}/content")
def file_content(file_id: int, db: Session = Depends(get_db)):
    db_file = file_service.get_file(db, file_id)
    if db_file is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    if file_service.is_link_resource(db_file):
        if not db_file.source_url:
            raise HTTPException(status_code=404, detail="链接资料缺少 URL")
        return RedirectResponse(db_file.source_url)
    path = file_service.content_path(db_file)
    if not path.exists():
        raise HTTPException(status_code=404, detail="磁盘文件不存在")
    return FastAPIFileResponse(
        path,
        media_type=db_file.mime_type,
        filename=db_file.original_name,
    )


@router.post("/files/{file_id}/restore", response_model=FileResponse)
def restore_file(file_id: int, db: Session = Depends(get_db)):
    db_file = file_service.restore_file(db, file_id)
    if db_file is None:
        raise HTTPException(status_code=404, detail="回收站中无此文件")
    return db_file


@router.delete("/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(file_id: int, db: Session = Depends(get_db)):
    if not file_service.soft_delete_file(db, file_id):
        raise HTTPException(status_code=404, detail="文件不存在")


@router.delete("/files/{file_id}/purge", status_code=status.HTTP_204_NO_CONTENT)
def purge_file(file_id: int, db: Session = Depends(get_db)):
    if not file_service.purge_file(db, file_id):
        raise HTTPException(status_code=404, detail="回收站中无此文件")


@router.get("/tasks/{task_id}/files", response_model=list[FileResponse])
def list_task_files(task_id: int, db: Session = Depends(get_db)):
    files = file_service.list_task_files(db, task_id)
    if files is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return files


@router.post("/tasks/{task_id}/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def attach_file(task_id: int, file_id: int, db: Session = Depends(get_db)):
    if not file_service.attach_to_task(db, task_id, file_id):
        raise HTTPException(status_code=404, detail="任务或文件不存在")


@router.delete("/tasks/{task_id}/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def detach_file(task_id: int, file_id: int, db: Session = Depends(get_db)):
    if not file_service.detach_from_task(db, task_id, file_id):
        raise HTTPException(status_code=404, detail="任务或关联不存在")
