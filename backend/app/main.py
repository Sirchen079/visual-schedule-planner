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
from app.routers import ai, files, reminders, schedule, tasks
from app.services import backup_service


def init_db() -> None:
    """运行时建表（测试用内存库，不走这里）。"""
    Base.metadata.create_all(bind=engine)
    _migrate()


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
    with engine.connect() as conn:
        cols = [row[1] for row in conn.execute(text("PRAGMA table_info(subtasks)"))]
        if cols and "completed_at" not in cols:
            conn.execute(text("ALTER TABLE subtasks ADD COLUMN completed_at DATETIME"))
        ai_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(ai_configs)"))]
        if ai_cols:
            for name, column_type in ai_config_columns.items():
                if name not in ai_cols:
                    conn.execute(text(f"ALTER TABLE ai_configs ADD COLUMN {name} {column_type}"))
        file_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(files)"))]
        if file_cols:
            for name, column_type in file_columns.items():
                if name not in file_cols:
                    conn.execute(text(f"ALTER TABLE files ADD COLUMN {name} {column_type}"))
            conn.execute(text("UPDATE files SET resource_type = 'file' WHERE resource_type IS NULL OR resource_type = ''"))
        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # 启动即备份一份当天数据库，守护"数据不丢"这条 north star 红线
    backup_service.backup_if_due()
    yield


app = FastAPI(title="可视化日程安排", lifespan=lifespan)
app.include_router(tasks.router)
app.include_router(files.router)
app.include_router(reminders.router)
app.include_router(schedule.router)
app.include_router(ai.router)


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
