# tests/domain/schedule/test_planner.py
from datetime import date, datetime
from freezegun import freeze_time
from zhishi.domain.schedule import planner
from zhishi.domain.tasks import service as ts
from zhishi.domain.tasks.schemas import TaskCreate


def _mk(db, title, *, priority="medium", due=None, est=60):
    return ts.create_task(db, TaskCreate(title=title, priority=priority,
                                         due_date=due, estimated_minutes=est))


@freeze_time("2026-09-08 09:00")
def test_plan_day_orders_and_fits(db):
    hi = _mk(db, "高优任务", priority="high", est=60)
    lo = _mk(db, "低优任务", priority="low", est=60)
    od = _mk(db, "逾期任务", priority="medium", due=datetime(2026, 9, 7, 18), est=60)
    plan = planner.plan_day(db, date(2026, 9, 8))
    titles = [p["task_id"] for p in plan["assignments"]]
    assert titles[0] == od.id      # 逾期最优先
    assert titles[1] == hi.id      # 其次高优
    assert titles[-1] == lo.id
    assert plan["unassigned"] == []   # 工作时段装得下 3×60min


@freeze_time("2026-09-08 09:00")
def test_plan_day_respects_capacity(db):
    for i in range(6):
        _mk(db, f"任务{i}", est=120)           # 6×120min 远超全天
    plan = planner.plan_day(db, date(2026, 9, 8))
    total = sum(a["estimated_minutes"] for a in plan["assignments"])
    assert total <= 8 * 60                      # 容量约束
    assert plan["unassigned"]                   # 装不下的进入未安排


def test_reschedule_overdue(db):
    from zhishi.agent.tools import macro
    with freeze_time("2026-09-08 09:00"):
        t = _mk(db, "过期任务", due=datetime(2026, 9, 6, 18), est=60)
        out = __import__("json").loads(macro.reschedule_overdue(db))
    # 偏差（对计划）：实现返回 moved 列表（与 import_timetable 的 skipped/conflicts
    # 列表风格一致），原断言 moved >= 1 假设为数字，改为长度断言
    assert len(out["moved"]) >= 1
    from zhishi.domain.schedule import service as ss
    day = ss.day_schedule(db, date(2026, 9, 8))
    assert any(i["task_id"] == t.id for i in day["tasks"])


@freeze_time('2026-09-08 09:00')
def test_booked_work_uses_capacity_and_is_not_reassigned(db):
    from zhishi.domain.schedule import service as ss
    booked = _mk(db, '已经安排', est=450)
    ss.assign_task_to_day(db, booked.id, date(2026,9,8))
    _mk(db, '新任务', est=60)
    plan = planner.plan_day(db, date(2026,9,8))
    assert not plan['assignments']
    assert len(plan['unassigned']) == 1
    assert plan['unassigned'][0]['reason'] == '超出当日容量'


@freeze_time('2026-09-08 09:00')
def test_small_task_can_use_earlier_gap_and_nothing_escapes_working_hours(db):
    from zhishi.domain.schedule import service as ss
    day = date(2026,9,8)
    ss.create_event(db,title='上午会',date=day,start_time='09:30',end_time='10:00')
    ss.create_event(db,title='晚间会',date=day,start_time='20:00',end_time='21:00')
    _mk(db,'长任务',priority='high',est=90)
    short = _mk(db,'短任务',est=30)
    for i in range(6):
        _mk(db,f'余下{i}',est=90)
    plan = planner.plan_day(db,day)
    assert next(a for a in plan['assignments'] if a['task_id'] == short.id)['start'] == '09:00'
    assert all('09:00' <= a['start'] < a['end'] <= '18:00' for a in plan['assignments'])
