from contextlib import asynccontextmanager
from pathlib import Path
import os
import threading

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.database import engine
from app.models import Base
from app.routers import ai, files, reminders, tasks
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
        "enabled": "BOOLEAN DEFAULT 0",
        "active_skill_id": "INTEGER",
        "created_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
        "updated_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
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
app.include_router(ai.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/shutdown")
def shutdown():
    """从网页端关闭本地服务。仅用于本地单机应用。"""
    def _graceful_exit():
        # 退出前再备一份最新数据库，并正常关闭连接确保 journal 落盘
        try:
            backup_service.backup_db()
        except Exception:
            # 备份失败不阻止退出
            pass
        engine.dispose()
        os._exit(0)

    threading.Timer(0.5, _graceful_exit).start()
    return {"status": "shutting_down"}


# 生产托管前端：若已构建（frontend/dist），由后端单端口同时提供界面与 API
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
