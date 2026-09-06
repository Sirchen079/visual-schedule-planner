from freezegun import freeze_time
from zhishi.domain.focus import service as fs
from zhishi.domain.focus.schemas import TimerStart
from zhishi.domain.tasks import service as ts
from zhishi.domain.tasks.schemas import TaskCreate


def test_single_running_timer(db):
    t = ts.create_task(db, TaskCreate(title="专注任务"))
    with freeze_time("2026-09-03 10:00"):
        a = fs.start_timer(db, TimerStart(task_id=t.id))
    with freeze_time("2026-09-03 10:05"):
        b = fs.start_timer(db, TimerStart(task_title="无任务计时"))  # 自动停掉 a
        assert fs.current_log(db).id == b.id
        assert fs.stop_timer(db, a.id) is None       # a 已被强制停止，再停返回 None
        db.refresh(a)
        assert a.minutes == 5                          # 强制停止时长相已结算
        stopped = fs.stop_timer(db, b.id)
        assert stopped is not None and stopped.id == b.id


def test_stop_current_and_stats(db):
    with freeze_time("2026-09-03 10:00"):
        log = fs.start_timer(db, TimerStart(task_title="写作"))
    with freeze_time("2026-09-03 10:50"):
        fs.stop_timer(db, None)
        stats = fs.time_stats(db, days=1)   # 统计须在冻结时间轴内取，避免真实跨日导致桶错位
    assert stats["by_day"][0]["minutes"] == 50
    assert stats["by_day"][0]["date"] == "2026-09-03"
    assert stats["by_task"][0]["task_title"] == "写作"
