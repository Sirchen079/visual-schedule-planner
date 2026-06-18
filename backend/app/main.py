from contextlib import asynccontextmanager
from pathlib import Path
import os
import threading

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import engine
from app.models import Base
from app.routers import files, tasks


def init_db() -> None:
    """运行时建表（测试用内存库，不走这里）。"""
    Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="可视化日程安排", lifespan=lifespan)
app.include_router(tasks.router)
app.include_router(files.router)


@app.post("/shutdown")
def shutdown():
    """从网页端关闭本地服务。仅用于本地单机应用。"""
    threading.Timer(0.5, lambda: os._exit(0)).start()
    return {"status": "shutting_down"}


# 生产托管前端：若已构建（frontend/dist），由后端单端口同时提供界面与 API
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
