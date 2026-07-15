from datetime import date as date_type, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    source_url: Optional[str] = None
    resource_type: str = "file"
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


ScheduleSource = Literal["manual", "ai", "system"]


class ScheduleEntryBase(BaseModel):
    task_id: int
    date: date_type
    source: ScheduleSource = "manual"
    note: str = ""


class ScheduleEntryCreate(ScheduleEntryBase):
    pass


class ScheduleEntryUpdate(BaseModel):
    date: Optional[date_type] = None
    note: Optional[str] = None
    source: Optional[ScheduleSource] = None


class ScheduleEntryRead(ScheduleEntryBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ScheduleTaskItem(BaseModel):
    task: TaskResponse
    entry: Optional[ScheduleEntryRead] = None
    reason: str


class DayScheduleBuckets(BaseModel):
    must_do: list[ScheduleTaskItem] = Field(default_factory=list)
    planned: list[ScheduleTaskItem] = Field(default_factory=list)
    in_progress_today: list[ScheduleTaskItem] = Field(default_factory=list)
    upcoming_pressure: list[ScheduleTaskItem] = Field(default_factory=list)
    unscheduled: list[ScheduleTaskItem] = Field(default_factory=list)


class DayScheduleSummary(BaseModel):
    must_do: int
    planned: int
    in_progress_today: int
    upcoming_pressure: int
    unscheduled: int
    total: int


class DayScheduleResponse(BaseModel):
    date: date_type
    summary: DayScheduleSummary
    buckets: DayScheduleBuckets


class MonthScheduleDay(BaseModel):
    date: date_type
    due_count: int
    planned_count: int
    in_progress_count: int
    overdue_count: int
    total_count: int


class MonthScheduleResponse(BaseModel):
    year: int
    month: int
    days: list[MonthScheduleDay]


AIProvider = Literal["openai_chat", "openai_responses", "claude_messages"]


class AIConfigCreate(BaseModel):
    name: str = Field("默认配置", min_length=1, max_length=100)
    assistant_name: str = Field("知时助手", min_length=1, max_length=100)
    persona: str = ""
    provider: AIProvider
    model: str = Field(..., min_length=1, max_length=100)
    api_key: str = Field(..., min_length=1)
    base_url: Optional[str] = None
    full_url: Optional[str] = None
    proxy_url: Optional[str] = None
    extra_headers: dict[str, str] = Field(default_factory=dict)
    native_web_search_enabled: bool = False
    native_web_search_options: dict[str, Any] = Field(default_factory=dict)
    search_enhancement_enabled: bool = False


class AIConfigUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    assistant_name: Optional[str] = Field(None, min_length=1, max_length=100)
    persona: Optional[str] = None
    provider: Optional[AIProvider] = None
    model: Optional[str] = Field(None, min_length=1, max_length=100)
    api_key: Optional[str] = Field(None, min_length=1)
    base_url: Optional[str] = None
    full_url: Optional[str] = None
    proxy_url: Optional[str] = None
    extra_headers: Optional[dict[str, str]] = None
    native_web_search_enabled: Optional[bool] = None
    native_web_search_options: Optional[dict[str, Any]] = None
    search_enhancement_enabled: Optional[bool] = None
    active_skill_id: Optional[int] = None


class AIConfigResponse(BaseModel):
    id: int
    name: str
    assistant_name: str
    persona: str = ""
    provider: AIProvider
    model: str
    api_key_masked: str
    base_url: Optional[str] = None
    full_url: Optional[str] = None
    proxy_url: Optional[str] = None
    extra_headers: dict[str, str] = Field(default_factory=dict)
    native_web_search_enabled: bool = False
    native_web_search_options: dict[str, Any] = Field(default_factory=dict)
    search_enhancement_enabled: bool = False
    enabled: bool
    active_skill_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AIModelsRequest(BaseModel):
    config_id: Optional[int] = None
    provider: Optional[AIProvider] = None
    api_key: Optional[str] = Field(None, min_length=1)
    base_url: Optional[str] = None
    full_url: Optional[str] = None
    proxy_url: Optional[str] = None
    extra_headers: dict[str, str] = Field(default_factory=dict)


class AIModelsResponse(BaseModel):
    models: list[str] = Field(default_factory=list)


class AISkillCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = ""
    content: str = Field(..., min_length=1)


class AISkillUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    content: Optional[str] = Field(None, min_length=1)


class AISkillImport(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)


class AISkillResponse(BaseModel):
    id: int
    name: str
    description: str
    content: str
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AIActionExecute(BaseModel):
    confirm_token: str = Field(..., min_length=1)


class AIPendingActionResponse(BaseModel):
    id: int
    conversation_id: Optional[int] = None
    action_type: str
    summary: str
    preview: list[str] = Field(default_factory=list)
    status: str
    expires_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AIChatAttachmentRef(BaseModel):
    id: str = Field(..., min_length=8, max_length=120)


class AIChatAttachmentResponse(BaseModel):
    id: str
    original_name: str
    size: int
    mime_type: str
    kind: str


class AIChatRequest(BaseModel):
    conversation_id: Optional[int] = None
    message: str = ""
    attachments: list[AIChatAttachmentRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_message_or_attachment(self):
        if not self.message.strip() and not self.attachments:
            raise ValueError("消息内容和附件不能同时为空")
        return self


class AIChatResponse(BaseModel):
    conversation_id: int
    assistant_name: str
    reply: str
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    pending_actions: list[AIPendingActionResponse] = Field(default_factory=list)


class AIConversationMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    pending_actions: list[AIPendingActionResponse] = Field(default_factory=list)
    created_at: datetime


class AIConversationSummaryResponse(BaseModel):
    id: int
    title: str
    last_message: str = ""
    message_count: int = 0
    created_at: datetime
    updated_at: datetime


class AIConversationDetailResponse(AIConversationSummaryResponse):
    messages: list[AIConversationMessageResponse] = Field(default_factory=list)


class AppSettingRead(BaseModel):
    key: str
    value: str
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AppSettingsBatch(BaseModel):
    """批量更新应用设置：{"settings": {"assistant_float_enabled": "true"}}"""

    settings: dict[str, str] = Field(default_factory=dict)
