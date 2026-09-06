from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WatchConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    enabled: bool = False
    queries: list[str] = Field(default_factory=list, max_length=3)
    frequency: Literal['daily', 'weekly'] = 'weekly'
    weekday: int = Field(default=0, ge=0, le=6)
    time: str = Field(default='09:00', pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    max_sources: int = Field(default=3, ge=1, le=6)
    refresh_existing: bool = True

    @model_validator(mode='after')
    def validate_queries(self):
        self.queries = list(dict.fromkeys(q.strip() for q in self.queries if q.strip()))
        if any(len(q) > 500 for q in self.queries):
            raise ValueError('每条检索词最多500字符')
        if self.enabled and not self.queries:
            raise ValueError('开启前请填写公开主题检索词')
        return self


class WatchUpdate(WatchConfig):
    version: int = Field(ge=0)


class WatchSource(BaseModel):
    source_id: int
    library_file_id: int | None = None
    title: str
    url: str
    changed: bool
    status: str
    error: str = ''


class WatchRunRead(BaseModel):
    id: int
    project_id: int
    status: str
    config: WatchConfig
    sources: list[WatchSource]
    errors: list[str]
    started_at: datetime
    finished_at: datetime | None


class WatchRead(BaseModel):
    project_id: int
    version: int
    config: WatchConfig
    next_run_at: datetime | None
    running: bool
    project_active: bool
    runs: list[WatchRunRead]
    next_before: int | None
