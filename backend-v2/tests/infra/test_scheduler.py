# tests/infra/test_scheduler.py
import asyncio
from zhishi.infra.scheduler import Scheduler

async def test_scheduler_runs_registered_task():
    s = Scheduler()
    hits = []
    s.add("probe", interval=0.01, coro_factory=lambda: _ap(hits))
    task = await s.start()
    await asyncio.sleep(0.05)
    await s.stop(task)
    assert len(hits) >= 2

async def _ap(hits):
    hits.append(1)

async def test_scheduler_swallows_errors():
    s = Scheduler()
    calls = []
    async def boom():
        calls.append(1)
        raise RuntimeError("boom")
    s.add("boom", interval=0.01, coro_factory=boom)
    task = await s.start()
    await asyncio.sleep(0.05)
    await s.stop(task)
    assert len(calls) >= 2  # 单次异常不终止循环


async def test_scheduler_respects_per_job_interval():
    """M4 回归：每个 job 按自己的 interval 调度——快 job 多跑，慢 job
    只在首轮立即执行一次，不得被最小 interval 拖着每轮都跑。"""
    s = Scheduler()
    fast, slow = [], []
    s.add("fast", interval=0.01, coro_factory=lambda: _ap(fast))
    s.add("slow", interval=10, coro_factory=lambda: _ap(slow))
    task = await s.start()
    await asyncio.sleep(0.15)
    await s.stop(task)
    assert len(fast) >= 3    # 快 job 按自身 0.01s 间隔多次执行
    assert len(slow) == 1    # 慢 job（10s）0.15s 内只应有首轮那一次


async def test_scheduler_delayed_job_not_refired_immediately():
    """慢 job 首轮执行后，next_due 推进一个完整 interval，期间不重复触发。"""
    s = Scheduler()
    hits = []
    s.add("heavy", interval=5, coro_factory=lambda: _ap(hits))
    task = await s.start()
    await asyncio.sleep(0.05)
    assert len(hits) == 1
    await s.stop(task)


async def test_slow_ai_job_does_not_block_reminder_and_does_not_overlap():
    scheduler = Scheduler()
    entered, release = asyncio.Event(), asyncio.Event()
    ai_calls, reminders = [], []
    async def slow_ai():
        ai_calls.append(1)
        entered.set()
        await release.wait()
    scheduler.add('morning-ai', .01, slow_ai)
    scheduler.add('reminder', .01, lambda: _ap(reminders))
    handle = await scheduler.start()
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await asyncio.sleep(.07)
        assert len(reminders) >= 3
        assert len(ai_calls) == 1
        assert await scheduler.start() is handle
    finally:
        await scheduler.stop(handle)
    assert not scheduler._workers
    assert handle.done()


async def test_add_after_start_and_restart_have_one_worker_per_job():
    scheduler = Scheduler()
    first = await scheduler.start()
    reached = asyncio.Event()
    async def job():
        reached.set()
    scheduler.add('later', 100, job)
    await asyncio.wait_for(reached.wait(), 1)
    await scheduler.stop(first)
    reached.clear()
    second = await scheduler.start()
    assert second is not first
    await asyncio.wait_for(reached.wait(), 1)
    await scheduler.stop(second)
