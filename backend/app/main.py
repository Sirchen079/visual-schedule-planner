from contextlib import asynccontextmanager
from pathlib import Path
import os
import sys
import threading

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.database import engine
from app.models import Base
from app.routers import ai, ai_actions, files, goals, habits, ical, journal, mcp, notifications, reminders, schedule, settings, stats, tasks, timer
from app.services import backup_service


def init_db() -> None:
    """运行时建表（测试用内存库，不走这里）。"""
    Base.metadata.create_all(bind=engine)
    _migrate()
    # 内置 skill 种子：随版本幂等更新（始终生效，不进用户视图）
    from app.database import SessionLocal
    from app.services import ai_skill_service

    with SessionLocal() as db:
        ai_skill_service.seed_builtin_skills(db)


def _migrate() -> None:
    """轻量列迁移：为旧库补齐新字段（单人 SQLite，无需 Alembic）。"""
    ai_config_columns = {
        "assistant_name": "VARCHAR(100) DEFAULT '知时助手'",
        "persona": "TEXT DEFAULT ''",
        "base_url": "VARCHAR(500)",
        "full_url": "VARCHAR(500)",
        "proxy_url": "VARCHAR(500)",
        "extra_headers": "TEXT DEFAULT '{}'",
        "native_web_search_enabled": "BOOLEAN DEFAULT 0",
        "native_web_search_options": "TEXT DEFAULT '{}'",
        "search_enhancement_enabled": "BOOLEAN DEFAULT 0",
        "enabled": "BOOLEAN DEFAULT 0",
        "active_skill_id": "INTEGER",
        "created_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
        "updated_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
    }
    file_columns = {
        "source_url": "VARCHAR(1000)",
        "resource_type": "VARCHAR(30) DEFAULT 'file'",
    }
    task_columns = {
        "completed_at": "DATETIME",
        "due_time": "VARCHAR(5)",
        "remind_offsets": "TEXT DEFAULT '[]'",
        "recur_rule": "VARCHAR(20) DEFAULT 'none'",
        "recur_interval": "INTEGER DEFAULT 1",
        "sort_order": "FLOAT DEFAULT 0",
        "estimated_minutes": "INTEGER",
    }
    ai_config_columns.update(
        {
            "price_input": "FLOAT DEFAULT 0",
            "price_output": "FLOAT DEFAULT 0",
            "tool_calling_mode": "VARCHAR(20) DEFAULT 'native'",
            # 阶段 3：思维链展示开关（默认开启；DeepSeek/OpenAI 兼容服务的 reasoning_content 零成本获得）
            "show_reasoning": "BOOLEAN DEFAULT 1",
        }
    )
    with engine.connect() as conn:
        cols = [row[1] for row in conn.execute(text("PRAGMA table_info(subtasks)"))]
        if cols and "completed_at" not in cols:
            conn.execute(text("ALTER TABLE subtasks ADD COLUMN completed_at DATETIME"))
        task_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(tasks)"))]
        if task_cols:
            for name, column_type in task_columns.items():
                if name not in task_cols:
                    conn.execute(text(f"ALTER TABLE tasks ADD COLUMN {name} {column_type}"))
            # 历史已完成任务用 updated_at 近似回填完成时间（与报告口径一致）
            conn.execute(
                text(
                    "UPDATE tasks SET completed_at = updated_at "
                    "WHERE status = '完成' AND completed_at IS NULL"
                )
            )
        # 时区归一（一次性）：func.now() 历史数据是 UTC，本应用其他时间戳均为本地时间，
        # 统一转本地，避免按日聚合（统计/用量）在凌晨错位一天。用 app_settings 哨兵保证只跑一次。
        has_app_settings = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='app_settings'")
        ).fetchone()
        if has_app_settings and task_cols:
            setting_keys = {
                row[0] for row in conn.execute(text("SELECT key FROM app_settings"))
            }
            if "tz_normalized_v1" not in setting_keys:
                conn.execute(
                    text(
                        "UPDATE tasks SET completed_at = datetime(completed_at, 'localtime') "
                        "WHERE completed_at IS NOT NULL AND completed_at = updated_at"
                    )
                )
                conn.execute(text("UPDATE tasks SET created_at = datetime(created_at, 'localtime')"))
                conn.execute(text("UPDATE tasks SET updated_at = datetime(updated_at, 'localtime')"))
                has_usage = conn.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table' AND name='ai_usage_logs'")
                ).fetchone()
                if has_usage:
                    conn.execute(
                        text("UPDATE ai_usage_logs SET created_at = datetime(created_at, 'localtime')")
                    )
                conn.execute(
                    text("INSERT INTO app_settings (key, value) VALUES ('tz_normalized_v1', '1')")
                )
        ai_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(ai_configs)"))]
        if ai_cols:
            for name, column_type in ai_config_columns.items():
                if name not in ai_cols:
                    conn.execute(text(f"ALTER TABLE ai_configs ADD COLUMN {name} {column_type}"))
        skill_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(ai_skills)"))]
        if skill_cols and "is_builtin" not in skill_cols:
            conn.execute(text("ALTER TABLE ai_skills ADD COLUMN is_builtin BOOLEAN DEFAULT 0"))
        file_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(files)"))]
        if file_cols:
            for name, column_type in file_columns.items():
                if name not in file_cols:
                    conn.execute(text(f"ALTER TABLE files ADD COLUMN {name} {column_type}"))
            conn.execute(text("UPDATE files SET resource_type = 'file' WHERE resource_type IS NULL OR resource_type = ''"))
        entry_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(task_schedule_entries)"))]
        if entry_cols:
            for name, column_type in {"start_time": "VARCHAR(5)", "end_time": "VARCHAR(5)"}.items():
                if name not in entry_cols:
                    conn.execute(text(f"ALTER TABLE task_schedule_entries ADD COLUMN {name} {column_type}"))
        subtask_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(subtasks)"))]
        if subtask_cols and "estimated_minutes" not in subtask_cols:
            conn.execute(text("ALTER TABLE subtasks ADD COLUMN estimated_minutes INTEGER"))
        # 阶段 B3：会话上下文压缩。AIConversation 增 meta 列存 summary / summary_upto_message_id；
        # AIMessage 增 compacted 列标记已纳入摘要（压缩后旧消息不再逐条回放，防上下文爆炸）。
        conv_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(ai_conversations)"))]
        if conv_cols and "meta" not in conv_cols:
            conn.execute(text("ALTER TABLE ai_conversations ADD COLUMN meta TEXT DEFAULT '{}'"))
        msg_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(ai_messages)"))]
        if msg_cols and "compacted" not in msg_cols:
            conn.execute(text("ALTER TABLE ai_messages ADD COLUMN compacted BOOLEAN DEFAULT 0"))
        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # 启动即备份一份当天数据库，守护"数据不丢"这条 north star 红线
    backup_service.backup_if_due()
    yield


app = FastAPI(title="知时", lifespan=lifespan)
app.include_router(tasks.router)
app.include_router(files.router)
app.include_router(reminders.router)
app.include_router(schedule.router)
app.include_router(settings.router)
app.include_router(stats.router)
app.include_router(notifications.router)
app.include_router(habits.router)
app.include_router(journal.router)
app.include_router(goals.router)
app.include_router(timer.router)
app.include_router(ical.router)
app.include_router(ai_actions.router)
app.include_router(ai.router)
app.include_router(mcp.router)


@app.get("/health")
def health():
    return {"status": "ok"}


def graceful_exit():
    """备份最新数据库、关闭连接确保 journal 落盘后退出进程。

    供 /shutdown 路由与桌面应用（Electron）退出流程复用。
    """
    # 退出前再备一份最新数据库，并正常关闭连接确保 journal 落盘
    try:
        backup_service.backup_db()
    except Exception:
        # 备份失败不阻止退出
        pass
    engine.dispose()
    os._exit(0)


@app.post("/shutdown")
def shutdown():
    """从网页端关闭本地服务。仅用于本地单机应用。"""
    threading.Timer(0.5, graceful_exit).start()
    return {"status": "shutting_down"}


def _frontend_dir() -> Path:
    """前端静态资源目录。

    打包模式：PyInstaller 把 frontend/dist 解包到 sys._MEIPASS/frontend/dist。
    开发模式：仓库根的 frontend/dist。
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "frontend" / "dist"
    return Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


# 生产托管前端：若已构建（frontend/dist），由后端单端口同时提供界面与 API
FRONTEND_DIR = _frontend_dir()
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
