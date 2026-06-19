from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# 受控枚举：防止脏数据入库（priority/status 只允许这些取值）
Priority = Literal["高", "中", "低"]
Status = Literal["待办", "进行中", "完成"]


class TagResponse(BaseModel):
    id: int
    name: str
    color: str

    model_config = ConfigDict(from_attributes=True)


class SubtaskResponse(BaseModel):
    id: int
    task_id: int
    title: str
    done: bool
    completed_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SubtaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


class SubtaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    done: Optional[bool] = None


class FileResponse(BaseModel):
    id: int
    original_name: str
    storage_path: str
    size: int
    mime_type: str
    notes: str
    uploaded_at: datetime
    deleted_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class FileUpdate(BaseModel):
    notes: Optional[str] = None


class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    notes: str = ""
    due_date: Optional[datetime] = None
    priority: Priority = "中"
    status: Status = "待办"
    progress: int = Field(0, ge=0, le=100)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    tags: list[str] = []  # 标签名列表，后端按名字 get-or-create


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    notes: Optional[str] = None
    due_date: Optional[datetime] = None
    priority: Optional[Priority] = None
    status: Optional[Status] = None
    progress: Optional[int] = Field(None, ge=0, le=100)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    tags: Optional[list[str]] = None


class TaskResponse(TaskBase):
    id: int
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    files: list[FileResponse] = []
    tags: list[TagResponse] = []
    subtasks: list[SubtaskResponse] = []

    model_config = ConfigDict(from_attributes=True)
