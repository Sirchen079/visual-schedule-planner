from datetime import date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from zhishi.domain.library.reading_schemas import MaterialSummary, SourceReference


class ProjectSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=200, description="主题或学习项目名称；联网默认只搜索此主题。")
    objective: str = Field(min_length=1, max_length=4000, description="希望学会什么或最终产出什么；保留用户原始目标。")
    kind: Literal["study", "research"] = "study"
    background: str = Field(default="", max_length=4000, description="现有基础与约束；未提供时留空，不捏造水平。")
    start_date: date = Field(default_factory=date.today)
    end_date: date | None = Field(default=None, description="留空时先以起始日后两周为规划窗口，界面明确展示此假设。")
    daily_minutes: int = Field(default=60, ge=15, le=480)
    session_minutes: int = Field(default=45, ge=15, le=120)
    weekdays: list[int] = Field(default_factory=lambda: list(range(7)), min_length=1, max_length=7,
                                description="可安排日期，0=周一，6=周日。")
    window_start: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    window_end: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")

    @model_validator(mode="after")
    def valid_window(self):
        end = self.end_date or self.start_date + timedelta(days=13)
        if end < self.start_date or (end - self.start_date).days > 365:
            raise ValueError("规划窗口须为起始日起366天以内")
        if any(d < 0 or d > 6 for d in self.weekdays) or len(set(self.weekdays)) != len(self.weekdays):
            raise ValueError("可安排星期须为不重复的0至6")
        if bool(self.window_start) != bool(self.window_end):
            raise ValueError("每天的可用起止时间须一起填写，或一起留空采用设置中的工作时段")
        if self.window_start and self.window_start >= self.window_end:
            raise ValueError("可用结束时间必须晚于开始时间")
        return self


class ProjectCreate(ProjectSpec):
    request_key: str | None = Field(default=None, min_length=1, max_length=160)


class ProjectUpdate(BaseModel):
    version: int = Field(ge=1)
    spec: ProjectSpec


class StepDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=160)
    outcome: str = Field(min_length=1, max_length=3000, description="本步完成后可检查的产出或掌握标准。")
    minutes: int = Field(ge=15, le=960, description="估计总投入分钟；程序自动拆成单次学习时段。")
    source_ids: list[int] = Field(default_factory=list, max_length=10,
                                 description="本项目已抓取正文的资料编号；只能引用返回的真实编号。")
    source_refs: list[SourceReference] = Field(default_factory=list, max_length=10,
        description='可选精确出处：source_id为项目资料编号，part/revision/quote来自read_material原文，不猜页码。')


class PlanDraft(BaseModel):
    version: int = Field(ge=1)
    rationale: str = Field(min_length=1, max_length=4000)
    steps: list[StepDraft] = Field(min_length=1, max_length=40,
                                   description="按先后顺序列步骤；不提供时间点或模型生成的任务编号。程序负责排程。")


class VersionInput(BaseModel):
    version: int = Field(ge=1)


class FeedbackInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    note: str = Field(min_length=1, max_length=4000, description='用户自述的收获、困难或希望调整的内容，不推断掌握程度。')
    task_link_id: int | None = Field(default=None, gt=0, description='可选项目任务记录id，来自tasks[].id，不是task_id。')
    difficulty: Literal['too_easy', 'suitable', 'too_hard', 'unspecified'] = 'unspecified'
    actual_minutes: int | None = Field(default=None, ge=0, le=10080)


class FeedbackCreate(FeedbackInput):
    version: int = Field(ge=1)
    request_key: str = Field(min_length=1, max_length=160)


class FeedbackRead(FeedbackInput):
    id: int
    project_id: int
    status: Literal['active', 'withdrawn']
    created_at: datetime
    applied_plan_ids: list[int] = Field(default_factory=list)


class FeedbackPage(BaseModel):
    items: list[FeedbackRead]
    total: int
    next_before: int | None = None


class ExtensionDraft(PlanDraft):
    feedback_ids: list[int] = Field(default_factory=list, max_length=20,
        description='本方案回应的真实反馈编号；不填写即为独立追加阶段。')


class RevisionDraft(ExtensionDraft):
    mode: Literal['insert_before', 'replace']
    target_link_id: int = Field(gt=0, description='目标项目任务记录编号，来自tasks[].id，不是task_id。')
    movable_task_link_ids: list[int] = Field(default_factory=list, max_length=50,
        description='仅用户明确允许移动的手工安排对应tasks[].id。默认保留手工安排；不允许移动进行中事项。')


class ProjectSlotRead(BaseModel):
    id: int
    date: str
    start: str | None
    end: str | None


class ProjectTaskRead(BaseModel):
    id: int
    task_id: int | None
    title: str
    status: str
    minutes: int | None
    notes: str
    source_ids: list[int]
    source_refs: list[SourceReference] = Field(default_factory=list)
    slots: list[ProjectSlotRead]


class RevisionTarget(BaseModel):
    task_link_id: int
    title: str
    can_insert_before: bool
    can_replace: bool
    can_move: bool
    manual_schedule: bool
    reason: str


class RevisionRead(BaseModel):
    mode: Literal['insert_before', 'replace']
    target_link_id: int
    before_task: ProjectTaskRead
    moved_manual: list[dict] = Field(default_factory=list)
    new_unit_indices: list[int]
    warnings: list[str] = Field(default_factory=list)


class GatherInput(BaseModel):
    queries: list[str] = Field(default_factory=list, max_length=3)
    max_sources: int = Field(default=3, ge=1, le=6)


class AddSourceInput(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    title: str = Field(default="", max_length=300)
    refresh: bool = False


class MaterialInput(BaseModel):
    file_id: int = Field(gt=0)


class ArchiveInput(VersionInput):
    archived: bool = True


class SourceRead(BaseModel):
    id: int
    kind: Literal["web", "file"]
    title: str
    url: str
    query: str
    description: str
    content: str
    status: Literal["candidate", "verified", "failed"]
    error: str
    library_file_id: int | None
    library_state: Literal["active", "deleted", "missing"]
    retrieved_at: datetime | None
    superseded_by: int | None = None
    content_is_excerpt: bool = True
    document: MaterialSummary | None = None
    read_call: dict | None = None


class GatherResult(BaseModel):
    ok: bool
    project_id: int
    queries: list[str]
    sources: list[SourceRead]
    errors: list[dict]
    next_step: dict
    source_boundary: str
    context: dict


class UnitRead(BaseModel):
    title: str
    outcome: str
    minutes: int
    source_ids: list[int]
    source_refs: list[SourceReference] = Field(default_factory=list)
    existing_task_id: int | None = None
    not_before: str | None = None
    blocked_by: int | None = None
    not_after: str | None = None
    replace_content: bool = False


class Assignment(BaseModel):
    unit_index: int
    date: str
    start: str
    end: str


class Unassigned(BaseModel):
    unit_index: int
    reason: str


class PlanRead(BaseModel):
    id: int
    project_id: int
    project_version: int
    kind: Literal["initial", "replan", "extension", "revision"]
    state: Literal["draft", "applied"]
    rationale: str
    units: list[UnitRead]
    assignments: list[Assignment]
    unassigned: list[Unassigned]
    preserved: list[dict]
    result: dict
    created_at: datetime
    applied_at: datetime | None
    feedback_ids: list[int] = Field(default_factory=list)
    revision: RevisionRead | None = None


class PlanSummary(BaseModel):
    id: int
    kind: str
    state: str
    rationale: str
    created_at: datetime
    applied_at: datetime | None


class PlanHistory(BaseModel):
    items: list[PlanSummary]
    next_before: int | None = None


class ProjectRead(BaseModel):
    id: int
    spec: ProjectSpec
    version: int
    assumptions: list[str]
    status: Literal["active", "archived"]
    goal_id: int | None
    verified_sources: int
    total_sources: int
    total_tasks: int
    completed_tasks: int
    missing_tasks: int
    latest_plan_id: int | None
    created_at: datetime


class ProjectDetail(BaseModel):
    project: ProjectRead
    sources: list[SourceRead]
    tasks: list[ProjectTaskRead]
    latest_plan: PlanRead | None
    next_step: dict
    feedback: FeedbackPage = Field(default_factory=lambda: FeedbackPage(items=[], total=0))
    revision_targets: list[RevisionTarget] = Field(default_factory=list)
