"""长期记忆 REST：用户查看/手动维护 AI 记下的记忆，及总开关读写。
开关语义为「默认开」：缺失视为开，与 settingsvc.feature_enabled（缺失=关）不同，
由 settingsvc.DEFAULTS 里的 feature_memory_enabled='true' 保证两处一致。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from zhishi.agent.tools.memory_tools import MEMORY_FLAG, MEMORY_KINDS, memory_enabled
from zhishi.domain import settingsvc
from zhishi.domain.models import AIMemory
from zhishi.server.deps import get_db

router = APIRouter(prefix="/api/memories", tags=["memories"])


class MemoryOut(BaseModel):
    """记忆响应模型。source_conversation_id 可空（会话删除后记忆保留）；
    时间序列化为 ISO 串（与既有回包一致）。"""
    id: int
    kind: str
    content: str
    keywords: str
    source: str
    source_conversation_id: int | None = None
    created_at: datetime
    updated_at: datetime


class MemoryCreate(BaseModel):
    kind: str = "fact"
    content: str
    keywords: str = ""


class MemoryUpdate(BaseModel):
    """PATCH 语义：缺省字段不动。"""
    kind: str | None = None
    content: str | None = None
    keywords: str | None = None


class MemoryEnabled(BaseModel):
    """开关回包：GET/PUT 共用。"""
    enabled: bool


class OkOut(BaseModel):
    """删除/写操作统一回包（同 notifications 的 EnableOut 惯例，schema 不留空）。"""
    ok: bool


def _out(row: AIMemory) -> dict:
    return {"id": row.id, "kind": row.kind, "content": row.content, "keywords": row.keywords,
            "source": row.source, "source_conversation_id": row.source_conversation_id,
            "created_at": row.created_at, "updated_at": row.updated_at}


def _get_or_404(db: Session, memory_id: int) -> AIMemory:
    row = db.get(AIMemory, memory_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"记忆 #{memory_id} 不存在或已删除")
    return row


def _check_kind(kind: str) -> str:
    if kind not in MEMORY_KINDS:
        raise HTTPException(status_code=400,
                            detail=f"kind 须为 {'/'.join(MEMORY_KINDS)} 之一")
    return kind


@router.get("", response_model=list[MemoryOut])
def list_memories(db: Session = Depends(get_db)):
    """扁平列表 + kind 字段（前端按 kind 分组展示），最近更新的在前。"""
    rows = db.scalars(select(AIMemory).order_by(AIMemory.updated_at.desc(), AIMemory.id.desc())).all()
    return [_out(r) for r in rows]


@router.post("", response_model=MemoryOut, status_code=201)
def create_memory(body: MemoryCreate, db: Session = Depends(get_db)):
    """用户手动添加：source='user'。内容与 kind 的教学性校验同工具口径。"""
    content = (body.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="内容不能为空")
    if len(content) > 300:
        raise HTTPException(status_code=400, detail=f"内容过长（{len(content)} 字），上限 300 字")
    row = AIMemory(kind=_check_kind(body.kind), content=content,
                   keywords=(body.keywords or "").strip(), source="user")
    db.add(row)
    db.commit()
    return _out(row)


@router.patch("/{memory_id}", response_model=MemoryOut)
def update_memory(memory_id: int, body: MemoryUpdate, db: Session = Depends(get_db)):
    row = _get_or_404(db, memory_id)
    if body.kind is not None:
        row.kind = _check_kind(body.kind)
    if body.content is not None:
        content = body.content.strip()
        if not content:
            raise HTTPException(status_code=400, detail="内容不能为空")
        if len(content) > 300:
            raise HTTPException(status_code=400, detail=f"内容过长（{len(content)} 字），上限 300 字")
        row.content = content
    if body.keywords is not None:
        row.keywords = body.keywords.strip()
    db.commit()
    db.refresh(row)
    return _out(row)


@router.delete("/{memory_id}", response_model=OkOut)
def delete_memory(memory_id: int, db: Session = Depends(get_db)):
    db.delete(_get_or_404(db, memory_id))
    db.commit()
    return {"ok": True}


@router.get("/enabled", response_model=MemoryEnabled)
def get_enabled(db: Session = Depends(get_db)):
    return {"enabled": memory_enabled(db)}


@router.put("/enabled", response_model=MemoryEnabled)
def put_enabled(body: MemoryEnabled, db: Session = Depends(get_db)):
    """写 'true'/'false'；关闭后工具从 search_tools 消失、注入块不再出现。"""
    settingsvc.set_setting(db, MEMORY_FLAG, "true" if body.enabled else "false")
    return {"enabled": body.enabled}
