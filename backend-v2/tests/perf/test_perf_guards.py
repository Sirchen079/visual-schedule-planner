"""本地性能回归测试：领域查询耗时和慢模型执行期间的 SSE 心跳。
测试使用受控数据与模型替身，不衡量外部服务响应速度。"""
import asyncio
import time
from datetime import date

from fastapi.testclient import TestClient


def test_domain_hot_paths_under_load(db):
    from zhishi.domain.tasks import service as ts
    from zhishi.domain.tasks.schemas import TaskCreate
    from zhishi.domain.schedule import service as ss
    from zhishi.domain.schedule import conflicts as cf

    for i in range(50):
        t = ts.create_task(db, TaskCreate(title=f"任务{i}", estimated_minutes=30,
                                          tag_names=["压测"]))
        ss.assign_task_to_day(db, t.id, date(2026, 9, 7 + (i % 5)))
    for i in range(30):
        ss.create_event(db, title=f"课{i}", date=date(2026, 9, 7 + (i % 5)),
                        start_time=f"{8 + i % 10:02d}:00", end_time=f"{9 + i % 10:02d}:00")

    t0 = time.perf_counter()
    assert len(ts.list_tasks(db, tag="压测")) == 50
    day = ss.unified_day(db, date(2026, 9, 7))
    month = ss.month_schedule(db, 2026, 9)
    load = ss.range_load(db, date(2026, 9, 7), days=14)
    conflicts = cf.check_conflicts(db, date(2026, 9, 7), date(2026, 9, 11))
    elapsed = time.perf_counter() - t0

    assert len(day["items"]) > 0 and len(month) == 30 and len(load) == 14
    assert len(conflicts) > 0
    assert elapsed < 2.0, f"领域热路径总耗时 {elapsed:.2f}s 超守卫线（疑似算法回归）"


def test_heartbeat_visible_when_model_slow(tmp_path):
    """慢模型（>5s 无输出）时 SSE 必须出现 heartbeat 帧——活性契约端到端验证。"""
    import json
    from pydantic_ai.models.function import FunctionModel
    from zhishi.server.app import create_app
    import zhishi.server.routes.ai as ai_route
    from zhishi.domain.models import AIConfig

    # FunctionModel stream_function：先静默 6.5s 再产文本，触发 ≥1 个心跳帧
    async def slow_stream(messages, info):
        await asyncio.sleep(6.5)
        yield "终于好了"

    def make_model(_cfg=None, api_key=None):
        return FunctionModel(stream_function=slow_stream)

    ai_route.build_model = make_model
    with TestClient(create_app(data_dir=tmp_path)) as c:
        with c.app.state.session_factory() as session:
            session.add(AIConfig(name="t", provider_kind="openai_compat", model="t",
                                 base_url="http://x", enabled=True))
            session.commit()
        r = c.post("/ai/chat/stream", json={"message": "慢点回"})
        assert r.status_code == 200
        heartbeats = [line for line in r.text.splitlines() if '"type": "heartbeat"' in line]
        assert heartbeats, "慢模型下未见 heartbeat 帧（活性契约破坏）"
