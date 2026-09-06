"""七域全部表。跨域外键集中在一个文件定义（task_tag/task_file 是关联表）。"""
from __future__ import annotations
import json
from datetime import date, datetime
from sqlalchemy import (Boolean, CheckConstraint, Column, Date, DateTime, Float, ForeignKey, Integer,
                        String, Table, Text, UniqueConstraint)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Bill(Base):
    __tablename__ = 'bills'
    id: Mapped[int] = mapped_column(primary_key=True)
    spec_json: Mapped[str] = mapped_column(Text)
    first_due: Mapped[date] = mapped_column(Date)
    cycle: Mapped[str] = mapped_column(String(12))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    request_key: Mapped[str] = mapped_column(String(160), unique=True)
    original_payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class BillOccurrence(Base):
    __tablename__ = 'bill_occurrences'
    __table_args__ = (UniqueConstraint('bill_id', 'sequence'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey('bills.id'), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    due: Mapped[date] = mapped_column(Date, index=True)
    spec_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), default='pending')
    version: Mapped[int] = mapped_column(Integer, default=1)
    ledger_entry_id: Mapped[int | None] = mapped_column(ForeignKey('ledger_entries.id'), unique=True)
    resolution_json: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)


class LedgerEntry(Base):
    """Personal bookkeeping. Integer minor units; never float money."""
    __tablename__ = "ledger_entries"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="ledger_positive_amount"),
        CheckConstraint("direction IN ('income','expense')", name="ledger_direction"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    direction: Mapped[str] = mapped_column(String(10))
    amount_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    category: Mapped[str] = mapped_column(String(50), default="未分类")
    account: Mapped[str] = mapped_column(String(80), default="默认账户")
    payee: Mapped[str] = mapped_column(String(200), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    source_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("library_files.id", ondelete="SET NULL"))
    source_excerpt: Mapped[str] = mapped_column(Text, default="")
    idempotency_key: Mapped[str | None] = mapped_column(String(160), unique=True)
    original_payload: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    deleted_at: Mapped[datetime | None]


task_tag = Table("task_tag", Base.metadata,
    Column("task_id", ForeignKey("tasks.id"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id"), primary_key=True))

task_file = Table("task_file", Base.metadata,
    Column("task_id", ForeignKey("tasks.id"), primary_key=True),
    Column("file_id", ForeignKey("library_files.id"), primary_key=True))


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    notes: Mapped[str] = mapped_column(Text, default="")
    due_date: Mapped[datetime | None]
    due_time: Mapped[str | None] = mapped_column(String(5))          # "HH:MM"
    remind_offsets: Mapped[str] = mapped_column(Text, default="[]")  # JSON [0,30,1440]
    priority: Mapped[str] = mapped_column(String(10), default="medium")  # high/medium/low
    status: Mapped[str] = mapped_column(String(20), default="todo")  # todo/doing/done
    progress: Mapped[int] = mapped_column(Integer, default=0)        # 0-100
    start_date: Mapped[datetime | None]
    recur_rule: Mapped[str] = mapped_column(String(20), default="none")  # none/daily/weekdays/weekly/monthly
    recur_interval: Mapped[int] = mapped_column(Integer, default=1)
    recur_rrule: Mapped[str | None] = mapped_column(Text)            # RFC5545，优先生效
    estimated_minutes: Mapped[int | None] = mapped_column(Integer)
    sort_order: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    completed_at: Mapped[datetime | None]
    deleted_at: Mapped[datetime | None]

    subtasks: Mapped[list["Subtask"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    tags: Mapped[list["Tag"]] = relationship(secondary=task_tag)
    files: Mapped[list["LibraryFile"]] = relationship(secondary=task_file)

    @property
    def remind_offset_list(self) -> list[int]:
        try:
            return json.loads(self.remind_offsets or "[]")
        except ValueError:
            return []


class Subtask(Base):
    __tablename__ = "subtasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    title: Mapped[str] = mapped_column(String(200))
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None]
    estimated_minutes: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    task: Mapped[Task] = relationship(back_populates="subtasks")


class Tag(Base):
    __tablename__ = "tags"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    color: Mapped[str] = mapped_column(String(20), default="#64748b")


class TaskScheduleEntry(Base):
    __tablename__ = "task_schedule_entries"
    __table_args__ = (UniqueConstraint("task_id", "date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    date: Mapped[date] = mapped_column(Date)
    start_time: Mapped[str | None] = mapped_column(String(5))
    end_time: Mapped[str | None] = mapped_column(String(5))
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual/ai/ical
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    task: Mapped[Task] = relationship()


class Event(Base):
    """独立日程块（不挂任务）。课表的'课'是日程不是任务。"""
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    date: Mapped[date] = mapped_column(Date)
    start_time: Mapped[str | None] = mapped_column(String(5))
    end_time: Mapped[str | None] = mapped_column(String(5))
    location: Mapped[str] = mapped_column(String(200), default="")
    category: Mapped[str] = mapped_column(String(30), default="general")
    recur_rrule: Mapped[str | None] = mapped_column(Text)  # 如 FREQ=WEEKLY;INTERVAL=2（单双周）
    repeat_note: Mapped[str | None] = mapped_column(Text)  # 人类可读周次规则，如「双周课（第2-16周）」
    notes: Mapped[str] = mapped_column(Text, default="")
    remind_offsets: Mapped[str] = mapped_column(Text, default='[]')
    reminder_time: Mapped[str | None] = mapped_column(String(5))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class Goal(Base):
    __tablename__ = "goals"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="active")  # active/done/archived
    start_date: Mapped[date | None]
    end_date: Mapped[date | None]
    sort_order: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    deleted_at: Mapped[datetime | None]
    key_results: Mapped[list["KeyResult"]] = relationship(back_populates="goal", cascade="all, delete-orphan")


class KeyResult(Base):
    __tablename__ = "key_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"))
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20), default="manual")  # manual/tag_task_count/habit_checkins
    target_value: Mapped[float] = mapped_column(Float, default=100.0)
    current_value: Mapped[float] = mapped_column(Float, default=0.0)
    unit: Mapped[str] = mapped_column(String(20), default="")
    link: Mapped[str] = mapped_column(Text, default="")  # tag 名或 habit 名
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    goal: Mapped[Goal] = relationship(back_populates="key_results")


class Habit(Base):
    __tablename__ = "habits"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    notes: Mapped[str] = mapped_column(Text, default="")
    period: Mapped[str] = mapped_column(String(10), default="daily")  # daily/weekly
    target_count: Mapped[int] = mapped_column(Integer, default=1)
    color: Mapped[str] = mapped_column(String(20), default="#22c55e")
    sort_order: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    deleted_at: Mapped[datetime | None]


class HabitLog(Base):
    __tablename__ = "habit_logs"
    __table_args__ = (UniqueConstraint("habit_id", "date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    habit_id: Mapped[int] = mapped_column(ForeignKey("habits.id"))
    date: Mapped[date] = mapped_column(Date)
    count: Mapped[int] = mapped_column(Integer, default=0)


class JournalEntry(Base):
    __tablename__ = "journal_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, unique=True)
    content: Mapped[str] = mapped_column(Text, default="")
    mood: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class TimeLog(Base):
    __tablename__ = "time_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"))
    task_title: Mapped[str] = mapped_column(String(200), default="")  # 冗余：任务删除后统计仍在
    kind: Mapped[str] = mapped_column(String(20), default="focus")    # focus/break
    started_at: Mapped[datetime] = mapped_column(DateTime)
    ended_at: Mapped[datetime | None]
    minutes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class LibraryFile(Base):
    """资料库文件/链接。只管存储与关联；extracted_text 由 解析管道回填。"""
    __tablename__ = "library_files"
    id: Mapped[int] = mapped_column(primary_key=True)
    original_name: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(String(500), unique=True)
    size: Mapped[int] = mapped_column(Integer, default=0)
    mime_type: Mapped[str] = mapped_column(String(100), default="application/octet-stream")
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str | None] = mapped_column(String(1000))
    resource_type: Mapped[str] = mapped_column(String(30), default="file")  # file/link/video
    extracted_text: Mapped[str | None] = mapped_column(Text)
    parse_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/parsed/failed
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    deleted_at: Mapped[datetime | None]


class InboxItem(Base):
    """Source-grounded proposals. Applying and creating the target share one transaction."""
    __tablename__ = "inbox_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(250), unique=True)
    source_file_id: Mapped[int | None] = mapped_column(ForeignKey("library_files.id", ondelete="SET NULL"))
    source_name: Mapped[str] = mapped_column(String(255), default="文字输入")
    source_excerpt: Mapped[str] = mapped_column(Text)
    item_key: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20))
    payload_json: Mapped[str] = mapped_column(Text)
    uncertainty: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    version: Mapped[int] = mapped_column(Integer, default=1)
    target_id: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class MaterialIndex(Base):
    __tablename__ = 'material_indexes'
    file_id: Mapped[int] = mapped_column(ForeignKey('library_files.id', ondelete='CASCADE'), primary_key=True)
    revision: Mapped[str] = mapped_column(String(64))
    metadata_json: Mapped[str] = mapped_column(Text)


class MaterialChunk(Base):
    __tablename__ = 'material_chunks'
    file_id: Mapped[int] = mapped_column(ForeignKey('library_files.id', ondelete='CASCADE'), primary_key=True)
    part: Mapped[int] = mapped_column(Integer, primary_key=True)
    location: Mapped[str] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text)


class ResearchProject(Base):
    __tablename__ = "research_projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    spec_json: Mapped[str] = mapped_column(Text)
    assumptions_json: Mapped[str] = mapped_column(Text, default="[]")
    request_key: Mapped[str | None] = mapped_column(String(160), unique=True)
    original_payload: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="active")
    goal_id: Mapped[int | None] = mapped_column(ForeignKey("goals.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ResearchSource(Base):
    __tablename__ = "research_sources"
    __table_args__ = (UniqueConstraint("project_id", "url_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("research_projects.id"))
    kind: Mapped[str] = mapped_column(String(10), default="web")
    url: Mapped[str] = mapped_column(Text)
    url_key: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(300))
    query: Mapped[str] = mapped_column(String(500), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="candidate")
    error: Mapped[str] = mapped_column(Text, default="")
    library_file_id: Mapped[int | None] = mapped_column(ForeignKey("library_files.id", ondelete="SET NULL"))
    retrieved_at: Mapped[datetime | None]
    superseded_by: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ResearchWatch(Base):
    __tablename__ = 'research_watches'
    project_id: Mapped[int] = mapped_column(ForeignKey('research_projects.id'), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=0)
    config_json: Mapped[str] = mapped_column(Text, default='{}')
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    active_token: Mapped[str | None] = mapped_column(String(36))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error_key: Mapped[str] = mapped_column(String(64), default='')


class ResearchWatchRun(Base):
    __tablename__ = 'research_watch_runs'
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('research_watches.project_id'), index=True)
    token: Mapped[str] = mapped_column(String(36), unique=True)
    status: Mapped[str] = mapped_column(String(20), default='running')
    config_json: Mapped[str] = mapped_column(Text)
    sources_json: Mapped[str] = mapped_column(Text, default='[]')
    errors_json: Mapped[str] = mapped_column(Text, default='[]')
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class ResearchPlan(Base):
    __tablename__ = "research_plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("research_projects.id"))
    project_version: Mapped[int] = mapped_column(Integer)
    request_hash: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[str] = mapped_column(String(20), default="initial")
    state: Mapped[str] = mapped_column(String(20), default="draft")
    rationale: Mapped[str] = mapped_column(Text, default="")
    units_json: Mapped[str] = mapped_column(Text)
    assignments_json: Mapped[str] = mapped_column(Text)
    unassigned_json: Mapped[str] = mapped_column(Text)
    preserved_json: Mapped[str] = mapped_column(Text, default="[]")
    movable_json: Mapped[str] = mapped_column(Text, default="[]")
    calendar_fingerprint: Mapped[str] = mapped_column(String(64))
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    applied_at: Mapped[datetime | None]


class ResearchFeedback(Base):
    __tablename__ = 'research_feedback'
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('research_projects.id'), index=True)
    task_link_id: Mapped[int | None] = mapped_column(ForeignKey('research_tasks.id'))
    request_key: Mapped[str] = mapped_column(String(160), unique=True)
    payload_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default='active')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ResearchPlanFeedback(Base):
    __tablename__ = 'research_plan_feedback'
    plan_id: Mapped[int] = mapped_column(ForeignKey('research_plans.id'), primary_key=True)
    feedback_id: Mapped[int] = mapped_column(ForeignKey('research_feedback.id'), primary_key=True)


class ResearchCurriculum(Base):
    __tablename__ = 'research_curricula'
    project_id: Mapped[int] = mapped_column(ForeignKey('research_projects.id'), primary_key=True)
    order_json: Mapped[str] = mapped_column(Text, default='[]')


class ResearchPlanEdit(Base):
    __tablename__ = 'research_plan_edits'
    plan_id: Mapped[int] = mapped_column(ForeignKey('research_plans.id'), primary_key=True)
    context_json: Mapped[str] = mapped_column(Text)


class ResearchTask(Base):
    __tablename__ = "research_tasks"
    __table_args__ = (UniqueConstraint("plan_id", "unit_index"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("research_projects.id"))
    plan_id: Mapped[int] = mapped_column(ForeignKey("research_plans.id"))
    unit_index: Mapped[int] = mapped_column(Integer)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200))
    source_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    managed_slots_json: Mapped[str] = mapped_column(Text, default="[]")


class SecretaryFollowup(Base):
    __tablename__ = 'secretary_followups'
    id: Mapped[int] = mapped_column(primary_key=True)
    evidence_key: Mapped[str] = mapped_column(String(100), unique=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('research_projects.id'), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    evidence_json: Mapped[str] = mapped_column(Text, default='{}')
    status: Mapped[str] = mapped_column(String(20), default='pending')
    version: Mapped[int] = mapped_column(Integer, default=1)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey('research_plans.id'))
    notification_id: Mapped[int | None] = mapped_column(ForeignKey('notification_logs.id'))
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime)
    error: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class NotificationLog(Base):
    __tablename__ = "notification_logs"
    __table_args__ = (UniqueConstraint("task_id", "remind_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"))
    dedupe_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    kind: Mapped[str] = mapped_column(String(20), default="reminder")
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    target_path: Mapped[str] = mapped_column(String(300), default='')
    remind_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    read_at: Mapped[datetime | None]


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


# ---- AI 层----

class AIConfig(Base):
    """AI 模型配置。api_key_ref 指 keyring 条目名，库内不存明文。"""
    __tablename__ = "ai_configs"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    provider_kind: Mapped[str] = mapped_column(String(20))  # openai_compat / anthropic
    model: Mapped[str] = mapped_column(String(100))
    base_url: Mapped[str | None] = mapped_column(String(500))
    api_key_ref: Mapped[str] = mapped_column(String(100), default="")
    price_input: Mapped[float] = mapped_column(Float, default=0.0)   # 元/百万token
    price_output: Mapped[float] = mapped_column(Float, default=0.0)
    request_limit: Mapped[int] = mapped_column(Integer, default=30)  # 步数预算
    context_window: Mapped[int | None] = mapped_column(Integer)
    max_output_tokens: Mapped[int | None] = mapped_column(Integer)
    reasoning_effort: Mapped[str | None] = mapped_column(String(16))
    input_modalities_json: Mapped[str] = mapped_column(Text, default='["text"]')
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class AIConversation(Base):
    __tablename__ = "ai_conversations"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), default="新会话")
    meta_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class AIContextCheckpoint(Base):
    """An immutable pre-compaction transcript, independent of the working context."""
    __tablename__ = 'ai_context_checkpoints'
    __table_args__ = (UniqueConstraint('conversation_id', 'fingerprint'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey('ai_conversations.id'), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    history_json: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class AIMessage(Base):
    """双存储：history_json = PydanticAI ModelMessage 序列化（续跑直接喂回）；
    display_json = 前端展示元数据（文本预览/工具结果/摘要）。"""
    __tablename__ = "ai_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("ai_conversations.id"))
    role: Mapped[str] = mapped_column(String(20))           # user / assistant / system
    display_json: Mapped[str] = mapped_column(Text, default="{}")
    history_json: Mapped[str] = mapped_column(Text, default="[]")  # 仅边界消息非空
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class AIRun(Base):
    """run 级 trace：状态/步数/工具链/token/耗时/中断原因。"""
    __tablename__ = "ai_runs"
    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)  # uuid4 hex
    conversation_id: Mapped[int] = mapped_column(ForeignKey("ai_conversations.id"))
    status: Mapped[str] = mapped_column(String(20), default="running")
    # running/awaiting_approval/completed/interrupted/failed/budget_exceeded
    done_reason: Mapped[str] = mapped_column(String(30), default="")
    steps: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls_json: Mapped[str] = mapped_column(Text, default="[]")
    usage_json: Mapped[str] = mapped_column(Text, default="{}")
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class AIToolExecution(Base):
    __tablename__ = 'ai_tool_executions'
    __table_args__ = (UniqueConstraint('run_id', 'call_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey('ai_runs.run_id'), index=True)
    call_id: Mapped[str] = mapped_column(String(100))
    tool: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default='running')
    result_json: Mapped[str] = mapped_column(Text, default='null')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class AIWorkspace(Base):
    """Window selection and drafts survive backend port changes; surfaces stay separate."""
    __tablename__ = 'ai_workspaces'
    surface: Mapped[str] = mapped_column(String(20), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    state_json: Mapped[str] = mapped_column(Text, default='{}')


class AIPendingAction(Base):
    """审批卡片：confirm 工具调用的持久化暂停点。状态机
    pending → confirmed → executed / rejected / expired。"""
    __tablename__ = "ai_pending_actions"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("ai_conversations.id"))
    run_id: Mapped[str] = mapped_column(String(36))
    tool_call_id: Mapped[str] = mapped_column(String(100))
    tool_name: Mapped[str] = mapped_column(String(100))
    args_json: Mapped[str] = mapped_column(Text, default="{}")
    preview: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    grant_token: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    resolved_at: Mapped[datetime | None]


class AIToolGrant(Base):
    """「始终允许」规则：tool_name 匹配 + arg_pattern（JSON 子集匹配，空=整工具）。"""
    __tablename__ = "ai_tool_grants"
    id: Mapped[int] = mapped_column(primary_key=True)
    tool_name: Mapped[str] = mapped_column(String(100))
    arg_pattern: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class AISkill(Base):
    __tablename__ = "ai_skills"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class AIUsageLog(Base):
    __tablename__ = "ai_usage_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    config_id: Mapped[int | None] = mapped_column(ForeignKey("ai_configs.id"))
    run_id: Mapped[str] = mapped_column(String(36), default="")
    kind: Mapped[str] = mapped_column(String(20), default="chat")
    provider: Mapped[str] = mapped_column(String(20), default="")
    model: Mapped[str] = mapped_column(String(100), default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class AIReport(Base):
    """AI 生成的报告/晨报/自动档摘要。period_start/end 标注覆盖窗口；
    briefing 同日幂等以 (report_type, period_start) 判定。"""
    __tablename__ = "ai_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    report_type: Mapped[str] = mapped_column(String(20))  # daily/weekly/briefing/autopilot
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(200), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    model_name: Mapped[str] = mapped_column(String(100), default="")  # "rule" = 纯规则降级
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class MCPServer(Base):
    """外部 MCP 工具服务器。工具不进 registry（动态清单）：runtime 对每个
    enabled 服务器构造 toolset，工具名映射 mcp__{id}__{原名}。"""
    __tablename__ = "mcp_servers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    transport: Mapped[str] = mapped_column(String(10), default="http")  # stdio / http
    command: Mapped[str] = mapped_column(String(500), default="")       # stdio 可执行文件
    args_json: Mapped[str] = mapped_column(Text, default="[]")
    env_json: Mapped[str] = mapped_column(Text, default="{}")           # 子进程环境（值属敏感）
    url: Mapped[str | None] = mapped_column(String(500))                # http 流式端点
    headers_json: Mapped[str] = mapped_column(Text, default="{}")       # http 头（值属敏感）
    timeout_sec: Mapped[int] = mapped_column(Integer, default=30)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_approve_readonly: Mapped[bool] = mapped_column(Boolean, default=False)
    # B1 安全：stdio 服务器须用户在配置中显式信任后才允许连接/工具装配
    # （无认证本地服务下防任意进程拉起）；http 传输不受限。
    trusted: Mapped[bool] = mapped_column(Boolean, default=False)
    last_status: Mapped[str] = mapped_column(String(20), default="untested")  # untested/ok/error
    last_error: Mapped[str | None] = mapped_column(Text)                # 脱敏后错误
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
