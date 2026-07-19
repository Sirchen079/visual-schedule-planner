from __future__ import annotations

import json
import secrets
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Table, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


task_file = Table(
    "task_file",
    Base.metadata,
    Column("task_id", ForeignKey("tasks.id"), primary_key=True),
    Column("file_id", ForeignKey("files.id"), primary_key=True),
)


task_tag = Table(
    "task_tag",
    Base.metadata,
    Column("task_id", ForeignKey("tasks.id"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id"), primary_key=True),
)


class Task(Base):
    """任务/事项。"""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    priority: Mapped[str] = mapped_column(String(10), default="中")  # 高 / 中 / 低
    status: Mapped[str] = mapped_column(String(20), default="待办")  # 待办 / 进行中 / 完成
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # 完成时间戳：进入「完成」状态时打点，重新打开时清空（趋势分析的数据基础）
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # 截止时刻（可选 "HH:MM"），与 due_date 组合成精确截止时间
    due_time: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    # 提醒偏移（JSON 分钟数组，如 [0,30,1440]：截止时 / 提前 30 分 / 提前 1 天）
    remind_offsets_json: Mapped[str] = mapped_column(
        "remind_offsets", Text, default="[]", nullable=False
    )
    # 重复规则：none / daily / weekdays / weekly / monthly；完成时惰性生成下一实例
    recur_rule: Mapped[str] = mapped_column(String(20), default="none", nullable=False)
    recur_interval: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # 看板列内手动排序权重：越小越靠前，相同则按创建时间倒序（0 为默认）
    sort_order: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    # 预估耗时（分钟，可选）；与实际计时（time_logs）对照做预估 vs 实际分析
    estimated_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    @property
    def remind_offsets(self) -> list[int]:
        """提醒偏移分钟列表（DB 存 JSON 字符串，对外暴露解析后的列表）。"""
        try:
            value = json.loads(self.remind_offsets_json or "[]")
        except (TypeError, json.JSONDecodeError):
            return []
        if not isinstance(value, list):
            return []
        return sorted({max(0, int(v)) for v in value if isinstance(v, (int, float))})

    files: Mapped[list["File"]] = relationship(
        "File", secondary=task_file, back_populates="tasks"
    )
    tags: Mapped[list["Tag"]] = relationship(
        "Tag", secondary=task_tag, back_populates="tasks"
    )
    subtasks: Mapped[list["Subtask"]] = relationship(
        "Subtask", back_populates="task", cascade="all, delete-orphan", order_by="Subtask.id"
    )


class TaskScheduleEntry(Base):
    __tablename__ = "task_schedule_entries"
    __table_args__ = (
        UniqueConstraint("task_id", "date", name="uq_task_schedule_task_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    task: Mapped["Task"] = relationship("Task")


class File(Base):
    """资料库文件索引。原始文件在磁盘，数据库只存元信息。"""

    __tablename__ = "files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), default="application/octet-stream")
    notes: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    resource_type: Mapped[str] = mapped_column(String(30), default="file")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    tasks: Mapped[list[Task]] = relationship(
        "Task", secondary=task_file, back_populates="files"
    )


class Tag(Base):
    """标签（分类）：任务按名字关联，颜色用于日历等着色。"""

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    color: Mapped[str] = mapped_column(String(20), default="#74ccf2")

    tasks: Mapped[list[Task]] = relationship(
        "Task", secondary=task_tag, back_populates="tags"
    )


class Subtask(Base):
    """任务子项：勾选用于自动计算父任务完成进度。"""

    __tablename__ = "subtasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    task: Mapped["Task"] = relationship("Task", back_populates="subtasks")


class AIConfig(Base):
    __tablename__ = "ai_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), default="默认配置")
    assistant_name: Mapped[str] = mapped_column(String(100), default="知时助手")
    persona: Mapped[str] = mapped_column(Text, default="")
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    api_key: Mapped[str] = mapped_column(Text, nullable=False)
    base_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    full_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    proxy_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    extra_headers: Mapped[str] = mapped_column(Text, default="{}")
    native_web_search_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    native_web_search_options: Mapped[str] = mapped_column(Text, default="{}")
    search_enhancement_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # 每百万 tokens 的输入/输出单价（用户自填，用于用量成本估算；0 表示未设置）
    price_input: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    price_output: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    active_skill_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("ai_skills.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class AISkill(Base):
    __tablename__ = "ai_skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class AIConversation(Base):
    __tablename__ = "ai_conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(200), default="新的对话")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["AIMessage"]] = relationship(
        "AIMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="AIMessage.id",
    )


class AIMessage(Base):
    __tablename__ = "ai_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("ai_conversations.id"), index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")
    meta: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    conversation: Mapped["AIConversation"] = relationship(
        "AIConversation", back_populates="messages"
    )


class AIPendingAction(Base):
    __tablename__ = "ai_pending_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    conversation_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("ai_conversations.id"), nullable=True
    )
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    confirm_token: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    @staticmethod
    def new_token() -> str:
        return secrets.token_urlsafe(32)


class AppSetting(Base):
    """应用级偏好（key-value）：悬浮窗开关、关闭按钮行为等，随 app.db 备份迁移。"""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Habit(Base):
    """习惯：每日/每周打卡目标。连续达成形成 streak（连续天数/周数）。"""

    __tablename__ = "habits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # daily=每天 target_count 次；weekly=每周 target_count 次
    period: Mapped[str] = mapped_column(String(10), default="daily", nullable=False)
    target_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    color: Mapped[str] = mapped_column(String(20), default="#74ccf2", nullable=False)
    sort_order: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    logs: Mapped[list["HabitLog"]] = relationship(
        "HabitLog", back_populates="habit", cascade="all, delete-orphan"
    )


class HabitLog(Base):
    """习惯打卡记录：按 (habit, date) 唯一，count 可累加。"""

    __tablename__ = "habit_logs"
    __table_args__ = (UniqueConstraint("habit_id", "date", name="uq_habit_log_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    habit_id: Mapped[int] = mapped_column(ForeignKey("habits.id"), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    habit: Mapped[Habit] = relationship("Habit", back_populates="logs")


class TimeLog(Base):
    """专注时间流水：一次番茄钟/正计时一条。任务删除后保留 title 快照可统计。"""

    __tablename__ = "time_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    task_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tasks.id"), nullable=True, index=True
    )
    task_title: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="pomodoro", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # None 表示正在计时中（全局至多一条运行中记录）
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Goal(Base):
    """OKR 目标：定性的方向（O），下挂若干可量化的关键结果（KR）。"""

    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # active / done / archived
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False, index=True)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    sort_order: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    key_results: Mapped[list["KeyResult"]] = relationship(
        "KeyResult", back_populates="goal", cascade="all, delete-orphan", order_by="KeyResult.id"
    )


class KeyResult(Base):
    """关键结果（KR）：manual 手动填值；tag_task_count 关联标签任务完成数；
    habit_checkins 关联习惯打卡总次数。后两种进度自动滚出。"""

    __tablename__ = "key_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    target_value: Mapped[float] = mapped_column(Float, default=1, nullable=False)
    current_value: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    # 自动类 KR 的关联配置：{"tag": "标签名"} 或 {"habit_id": 1}
    link: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    goal: Mapped[Goal] = relationship("Goal", back_populates="key_results")


class JournalEntry(Base):
    """日记：一天一篇（date 唯一），Markdown 正文，幕僚的推理素材。"""

    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, unique=True, index=True)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    mood: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class NotificationLog(Base):
    """通知记录：到点提醒触发时落一条，供通知中心回溯（错过不丢）。

    触发仍由前端轮询驱动（无后台定时器），记录按 (task_id, remind_at) 幂等。
    """

    __tablename__ = "notification_logs"
    __table_args__ = (
        UniqueConstraint("task_id", "remind_at", name="uq_notification_task_remind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    task_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tasks.id"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(20), default="reminder", nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    remind_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class AIUsageLog(Base):
    """AI token 用量流水：每次模型调用落一条，供用量统计与成本估算。"""

    __tablename__ = "ai_usage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    config_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("ai_configs.id"), nullable=True, index=True
    )
    conversation_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("ai_conversations.id"), nullable=True, index=True
    )
    # chat / report / briefing：调用场景
    kind: Mapped[str] = mapped_column(String(20), default="chat", nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(30), default="", nullable=False)
    model: Mapped[str] = mapped_column(String(100), default="", nullable=False, index=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class AIReport(Base):
    """AI 生成的日报/周报，存历史可回看、删除、导出。"""

    __tablename__ = "ai_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # daily / weekly
    report_type: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(String(200), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    model_name: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
