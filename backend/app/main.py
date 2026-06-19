from contextlib import asynccontextmanager
from pathlib import Path
import os
import threading

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.database import engine
from app.models import Base
from app.routers import files, reminders, tasks
from app.services import backup_service


def init_db() -> None:
    """运行时建表（测试用内存库，不走这里）。"""
    Base.metadata.create_all(bind=engine)
    _migrate()


def _migrate() -> None:
    """轻量列迁移：为旧库补齐新字段（单人 SQLite，无需 Alembic）。"""
    with engine.connect() as conn:
        cols = [row[1] for row in conn.execute(text("PRAGMA table_info(subtasks)"))]
        if cols and "completed_at" not in cols:
            conn.execute(text("ALTER TABLE subtasks ADD COLUMN completed_at DATETIME"))
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
