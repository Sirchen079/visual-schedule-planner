from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import engine
from app.models import Base
from app.routers import tasks


def init_db() -> None:
    """运行时建表（测试用内存库，不走这里）。"""
    Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="可视化日程安排", lifespan=lifespan)
app.include_router(tasks.router)


@app.get("/")
def root():
    return {"status": "ok", "service": "可视化日程安排"}
