from datetime import date as date_type, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

# 受控枚举：防止脏数据入库（priority/status 只允许这些取值）
Priority = Literal["高", "中", "低"]
Status = Literal["待办", "进行中", "完成"]
# 重复规则：none 不重复；daily 每天；weekdays 每个工作日；weekly 每周；monthly 每月
RecurRule = Literal["none", "daily", "weekdays", "weekly", "monthly"]


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
    estimated_minutes: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class SubtaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    estimated_minutes: Optional[int] = Field(None, ge=0)


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
    due_time: Optional[str] = Field(
        None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$"
    )  # 截止时刻 "HH:MM"，与 due_date 组合
    remind_offsets: list[int] = []  # 提醒偏移分钟（如 [0,30,1440]：截止时/提前30分/提前1天）
    recur_rule: RecurRule = "none"
    recur_interval: int = Field(1, ge=1, le=99)
    sort_order: float = 0  # 看板列内手动排序权重，越小越靠前
    estimated_minutes: Optional[int] = Field(None, ge=0)  # 预估耗时（分钟）


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
    due_time: Optional[str] = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    remind_offsets: Optional[list[int]] = None
    recur_rule: Optional[RecurRule] = None
    recur_interval: Optional[int] = Field(None, ge=1, le=99)
    sort_order: Optional[float] = None
    estimated_minutes: Optional[int] = Field(None, ge=0)


class TaskResponse(TaskBase):
    id: int
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
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
    start_time: Optional[str] = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")  # 日内开始时刻 "HH:MM"（可选）
    end_time: Optional[str] = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")  # 日内结束时刻 "HH:MM"（可选）


class ScheduleEntryCreate(ScheduleEntryBase):
    pass


class ScheduleEntryUpdate(BaseModel):
    date: Optional[date_type] = None
    note: Optional[str] = None
    source: Optional[ScheduleSource] = None
    start_time: Optional[str] = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end_time: Optional[str] = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


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
ToolCallingMode = Literal["native", "plan"]


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
    tool_calling_mode: ToolCallingMode = "native"
    # 每百万 tokens 输入/输出单价（可选，用于用量成本估算；0 表示未设置）
    price_input: float = Field(0, ge=0)
    price_output: float = Field(0, ge=0)
    # 阶段 3：思维链展示开关（默认开启）
    show_reasoning: bool = True


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
    tool_calling_mode: Optional[ToolCallingMode] = None
    active_skill_id: Optional[int] = None
    price_input: Optional[float] = Field(None, ge=0)
    price_output: Optional[float] = Field(None, ge=0)
    show_reasoning: Optional[bool] = None


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
    tool_calling_mode: ToolCallingMode = "native"
    enabled: bool
    price_input: float = 0
    price_output: float = 0
    show_reasoning: bool = True
    active_skill_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---- MCP 服务器配置 ----
MCPTransport = Literal["stdio", "http"]


def _validate_mcp_fields(
    transport: str,
    command: Optional[str],
    args: Optional[list[str]],
    url: Optional[str],
) -> None:
    """按传输类型校验必填项与格式。"""
    if transport == "stdio":
        if not command or not command.strip():
            raise ValueError("stdio 传输需要 command（可执行命令）")
        if args is None:
            raise ValueError("stdio args 缺失")
    elif transport == "http":
        if not url or not url.strip():
            raise ValueError("http 传输需要 url")
        stripped = url.strip()
        if not (stripped.startswith("http://") or stripped.startswith("https://")):
            raise ValueError("http url 只允许 http:// 或 https://")
    else:
        raise ValueError("transport 只允许 stdio 或 http")


class MCPServerBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    transport: MCPTransport
    command: Optional[str] = Field(None, max_length=500)
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: Optional[str] = Field(None, max_length=1000)
    headers: dict[str, str] = Field(default_factory=dict)
    timeout_sec: int = Field(30, ge=5, le=120)
    enabled: bool = True
    auto_approve_readonly: bool = False

    @model_validator(mode="after")
    def _check_transport_fields(self):
        _validate_mcp_fields(self.transport, self.command, self.args, self.url)
        return self


class MCPServerCreate(MCPServerBase):
    pass


class MCPServerUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    transport: Optional[MCPTransport] = None
    command: Optional[str] = Field(None, max_length=500)
    args: Optional[list[str]] = None
    env: Optional[dict[str, str]] = None
    url: Optional[str] = Field(None, max_length=1000)
    headers: Optional[dict[str, str]] = None
    timeout_sec: Optional[int] = Field(None, ge=5, le=120)
    enabled: Optional[bool] = None
    auto_approve_readonly: Optional[bool] = None

    @model_validator(mode="after")
    def _check_transport_fields(self):
        # 更新时 transport 可能未传，按显式传入的字段组合校验
        transport = self.transport
        if transport is None and (
            self.command is not None or self.args is not None or self.url is not None
        ):
            # 未带 transport 又改了传输相关字段，无法判定合法性，交给 service 层按现库值校验
            return self
        if transport is not None:
            _validate_mcp_fields(transport, self.command, self.args, self.url)
        return self


class MCPServerResponse(BaseModel):
    """响应模型：env/headers 的 value 一律脱敏。"""

    id: int
    name: str
    transport: str
    command: Optional[str] = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: Optional[str] = None
    headers: dict[str, str] = Field(default_factory=dict)
    timeout_sec: int = 30
    enabled: bool = True
    auto_approve_readonly: bool = False
    last_status: str = "unknown"
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MCPToolInfo(BaseModel):
    name: str  # 已加 mcp__s{id}__ 前缀的完整工具名
    original_name: str  # MCP 服务器原始工具名
    server_id: int
    server_name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    read_only: bool = False


class MCPTestResult(BaseModel):
    ok: bool
    message: str = ""
    tools: list[MCPToolInfo] = Field(default_factory=list)


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
    description: str = Field("", max_length=500)
    content: str = Field(..., min_length=1, max_length=20000)


class AISkillUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    content: Optional[str] = Field(None, min_length=1, max_length=20000)


class AISkillImport(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1, max_length=20000)


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
    # 阶段 B2：请求级覆盖步数预算（3-30）。None/缺省回落 settings.agent_max_steps。
    max_steps: Optional[int] = None
    # 阶段 C1：会话模式。chat=正常对话；plan=计划模式（只读调研 + propose_plan 收尾）。
    mode: Optional[str] = "chat"

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
    # resume 端点专用：true=已续跑并返回新回复；false=无 checkpoint 或仍有 pending（前端静默）
    resumed: bool = False
    # 本次 run 累计 token 用量（provider 不回 usage 时为 None）
    usage: dict[str, Any] | None = None


class AIChatResumeRequest(BaseModel):
    conversation_id: int


class AIPlanStep(BaseModel):
    action: str = ""
    tool: str = ""
    args_preview: str | None = None
    rationale: str | None = None


class AIPlanApproveRequest(BaseModel):
    """阶段 C1：批准计划。可携带用户编辑后的 steps；批准后作为新用户指令注入会话并切回 chat 模式执行。"""
    steps: list[AIPlanStep] | None = None


class AIPlanRejectRequest(BaseModel):
    """阶段 C1：拒绝计划。可选携带用户拒绝理由，回一句话。"""
    reason: str | None = None


class AIToolGrantCreate(BaseModel):
    """阶段 D1：创建「始终允许」授权规则。"""
    tool_name: str
    arg_pattern: str = ""


class AIToolGrantResponse(BaseModel):
    id: int
    tool_name: str
    arg_pattern: str = ""
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AIConversationMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    pending_actions: list[AIPendingActionResponse] = Field(default_factory=list)
    # 消息元数据（白名单）：usage / elapsed_ms / reasoning，供历史消息展示 token 用量与思维链
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AIConversationSummaryResponse(BaseModel):
    id: int
    title: str
    last_message: str = ""
    message_count: int = 0
    created_at: datetime
    updated_at: datetime


class AIConversationRename(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


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


# ---- AI 日报/周报 ----
ReportType = Literal["daily", "weekly"]


class AIReportGenerateRequest(BaseModel):
    report_type: ReportType
    target_date: Optional[date_type] = None  # 默认今天；weekly 取所在周


class AIReportResponse(BaseModel):
    id: int
    report_type: str  # daily / weekly / briefing
    period_start: date_type
    period_end: date_type
    title: str
    content: str
    model_name: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---- 统计分析 ----


class StatsSummary(BaseModel):
    """当前存量概览：状态计数 + 时效分桶。"""

    total: int
    by_status: dict[str, int]
    overdue: int
    due_today: int
    due_this_week: int
    completed_total: int


class StatsDailyPoint(BaseModel):
    date: date_type
    completed: int
    created: int


class StatsDailyResponse(BaseModel):
    days: list[StatsDailyPoint]


class StatsTagItem(BaseModel):
    name: str
    color: str
    total: int
    completed: int


class StatsByTagResponse(BaseModel):
    tags: list[StatsTagItem]


class StatsPriorityItem(BaseModel):
    priority: str
    by_status: dict[str, int]
    total: int


class StatsByPriorityResponse(BaseModel):
    priorities: list[StatsPriorityItem]


class TokenUsageDay(BaseModel):
    date: date_type
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class TokenUsageModel(BaseModel):
    model: str
    provider: str
    call_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost: Optional[float] = None  # 按配置价目估算；未设价目为 None


class TokenUsageResponse(BaseModel):
    days: list[TokenUsageDay]
    models: list[TokenUsageModel]
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    total_estimated_cost: Optional[float] = None
    untracked_calls: int = 0  # 接口未返回 usage 的调用次数


# ---- 通知中心 ----


class NotificationResponse(BaseModel):
    id: int
    task_id: Optional[int] = None
    kind: str
    title: str
    body: str
    remind_at: datetime
    created_at: datetime
    read_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class NotificationUnreadCount(BaseModel):
    unread: int


# ---- 习惯打卡 ----
HabitPeriod = Literal["daily", "weekly"]


class HabitBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    notes: str = ""
    period: HabitPeriod = "daily"
    target_count: int = Field(1, ge=1, le=99)
    color: str = "#74ccf2"
    sort_order: float = 0


class HabitCreate(HabitBase):
    pass


class HabitUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    notes: Optional[str] = None
    period: Optional[HabitPeriod] = None
    target_count: Optional[int] = Field(None, ge=1, le=99)
    color: Optional[str] = None
    sort_order: Optional[float] = None


class HabitResponse(HabitBase):
    id: int
    created_at: datetime
    # 计算字段：今日/本周完成次数、当前连续达成纪录
    today_count: int = 0
    period_count: int = 0  # daily=今日次数；weekly=本周次数
    streak: int = 0  # daily=连续天数；weekly=连续周数
    done_today: bool = False

    model_config = ConfigDict(from_attributes=True)


class HabitCheckRequest(BaseModel):
    date: Optional[date_type] = None  # 缺省今天


class HabitLogResponse(BaseModel):
    date: date_type
    count: int

    model_config = ConfigDict(from_attributes=True)


# ---- 日记 ----


class JournalUpsert(BaseModel):
    content: str = ""
    mood: Optional[str] = Field(None, max_length=20)


class JournalResponse(BaseModel):
    id: int
    date: date_type
    content: str
    mood: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class JournalListItem(BaseModel):
    id: int
    date: date_type
    preview: str  # 正文前 120 字
    mood: Optional[str] = None
    updated_at: datetime


# ---- 逾期风险预测（确定性规则，不依赖 AI）----


class RiskItem(BaseModel):
    task_id: int
    title: str
    priority: str
    status: str
    due_date: Optional[datetime] = None
    progress: int
    score: int
    reasons: list[str]


class RiskResponse(BaseModel):
    items: list[RiskItem]


# ---- 番茄钟 / 时间记录 ----


class TimeLogStart(BaseModel):
    task_id: int
    kind: Literal["pomodoro", "stopwatch"] = "pomodoro"


class TimeLogResponse(BaseModel):
    id: int
    task_id: Optional[int] = None
    task_title: str
    kind: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    minutes: int

    model_config = ConfigDict(from_attributes=True)


class TimeDailyPoint(BaseModel):
    date: date_type
    minutes: int


class TimeTagItem(BaseModel):
    name: str
    color: str
    minutes: int


class TimeTaskItem(BaseModel):
    task_id: Optional[int] = None
    title: str
    minutes: int


class EstimateVsActualItem(BaseModel):
    task_id: int
    title: str
    estimated_minutes: int
    actual_minutes: int


class TimeStatsResponse(BaseModel):
    daily: list[TimeDailyPoint]
    by_tag: list[TimeTagItem]
    by_task: list[TimeTaskItem]
    estimates: list[EstimateVsActualItem]
    total_minutes: int


# ---- OKR 目标管理 ----
GoalStatus = Literal["active", "done", "archived"]
KrKind = Literal["manual", "tag_task_count", "habit_checkins"]


class KeyResultBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    kind: KrKind = "manual"
    target_value: float = Field(1, gt=0)
    unit: str = ""
    link: dict[str, Any] = Field(default_factory=dict)


class KeyResultCreate(KeyResultBase):
    pass


class KeyResultUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    kind: Optional[KrKind] = None
    target_value: Optional[float] = Field(None, gt=0)
    unit: Optional[str] = None
    link: Optional[dict[str, Any]] = None
    current_value: Optional[float] = None  # 仅 manual 类型允许直接改值


class KeyResultResponse(KeyResultBase):
    id: int
    goal_id: int
    current_value: float
    progress: int = 0  # 0-100，自动类 KR 由后端实时计算

    model_config = ConfigDict(from_attributes=True)


class GoalBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    notes: str = ""
    start_date: Optional[date_type] = None
    end_date: Optional[date_type] = None


class GoalCreate(GoalBase):
    key_results: list[KeyResultCreate] = []


class GoalUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    notes: Optional[str] = None
    status: Optional[GoalStatus] = None
    start_date: Optional[date_type] = None
    end_date: Optional[date_type] = None


class GoalResponse(GoalBase):
    id: int
    status: str
    progress: int = 0  # 各 KR 进度均值
    key_results: list[KeyResultResponse] = []
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
