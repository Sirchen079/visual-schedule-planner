from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class FileResponse(BaseModel):
    id: int
    original_name: str
    storage_path: str
    size: int
    mime_type: str
    notes: str
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FileUpdate(BaseModel):
    notes: Optional[str] = None


class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    notes: str = ""
    due_date: Optional[datetime] = None
    priority: str = "中"
    status: str = "待办"
    progress: int = Field(0, ge=0, le=100)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    notes: Optional[str] = None
    due_date: Optional[datetime] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    progress: Optional[int] = Field(None, ge=0, le=100)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class TaskResponse(TaskBase):
    id: int
    created_at: datetime
    updated_at: datetime
    files: list[FileResponse] = []

    model_config = ConfigDict(from_attributes=True)
