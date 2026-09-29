"""对话文件夹附加 REST：用户为会话附加/列出/移除本地文件夹（附加即读取授权，移除即撤销）。
标签默认取路径最后一段名；移除时显式先删索引 chunk 行再删 folder 行（不依赖 FK 级联）。"""
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from zhishi.domain.models import AIConversation, AIConversationFolder, FolderFileChunk
from zhishi.server.deps import get_db

router = APIRouter(prefix="/ai/conversations/{conversation_id}/folders",
                   tags=["conversation-folders"])


class FolderOut(BaseModel):
    """附件响应模型。时间序列化为 ISO 串（与既有回包一致）。"""
    id: int
    label: str
    root_path: str
    created_at: datetime


class FolderCreate(BaseModel):
    root_path: str


def _out(row: AIConversationFolder) -> dict:
    return {"id": row.id, "label": row.label, "root_path": row.root_path,
            "created_at": row.created_at}


def _conversation_or_404(db: Session, conversation_id: int) -> AIConversation:
    row = db.get(AIConversation, conversation_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"会话 #{conversation_id} 不存在或已删除")
    return row


def _folder_or_404(db: Session, conversation_id: int, folder_id: int) -> AIConversationFolder:
    row = db.get(AIConversationFolder, folder_id)
    if row is None or row.conversation_id != conversation_id:
        raise HTTPException(status_code=404, detail=f"附件 #{folder_id} 不存在或不属于该会话")
    return row


@router.get("", response_model=list[FolderOut])
def list_folders(conversation_id: int, db: Session = Depends(get_db)):
    """列该会话附加的本地文件夹（按 id 升序，与 AI 工具侧口径一致）。"""
    _conversation_or_404(db, conversation_id)
    rows = db.scalars(select(AIConversationFolder)
                      .where(AIConversationFolder.conversation_id == conversation_id)
                      .order_by(AIConversationFolder.id)).all()
    return [_out(r) for r in rows]


@router.post("", response_model=FolderOut, status_code=201)
def attach_folder(conversation_id: int, body: FolderCreate, db: Session = Depends(get_db)):
    """附加本地文件夹：路径须存在且为目录（否则 400），同会话同 root_path 重复 409。
    附加仅登记授权与元数据，不在此建索引（索引由 AI 工具侧按需构建）。"""
    _conversation_or_404(db, conversation_id)
    root = (body.root_path or "").strip()
    if not root:
        raise HTTPException(status_code=400, detail="root_path 不能为空")
    p = Path(root)
    if not p.exists():
        raise HTTPException(status_code=400, detail=f"路径不存在：{root}")
    if not p.is_dir():
        raise HTTPException(status_code=400, detail=f"路径不是目录（只允许附加文件夹）：{root}")
    dup = db.scalars(select(AIConversationFolder)
                     .where(AIConversationFolder.conversation_id == conversation_id,
                            AIConversationFolder.root_path == root)).first()
    if dup is not None:
        raise HTTPException(status_code=409, detail=f"该文件夹已附加到此会话：{root}")
    label = p.name or root   # 盘根/根目录 name 为空时退回整个路径字符串
    row = AIConversationFolder(conversation_id=conversation_id, root_path=root, label=label)
    db.add(row)
    db.commit()
    return _out(row)


@router.delete("/{folder_id}", status_code=204)
def remove_folder(conversation_id: int, folder_id: int, db: Session = Depends(get_db)) -> None:
    """移除附件（=撤销读取授权）：显式先删 chunk 索引行再删 folder 行（SQLite 无 FK 级联）。"""
    _conversation_or_404(db, conversation_id)
    row = _folder_or_404(db, conversation_id, folder_id)
    db.execute(delete(FolderFileChunk).where(FolderFileChunk.folder_id == folder_id))
    db.delete(row)
    db.commit()
