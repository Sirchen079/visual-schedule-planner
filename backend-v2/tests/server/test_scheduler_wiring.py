"""调度器接线：晨报与自动档任务已在 lifespan 注册（固定间隔轮询 + 自检幂等）。"""
from fastapi.testclient import TestClient

from zhishi.server.app import create_app


def test_daily_ai_jobs_registered(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        names = set(c.app.state.scheduler._jobs.keys())
        assert {"morning-briefing", "autopilot"} <= names
