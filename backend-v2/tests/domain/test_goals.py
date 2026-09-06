# tests/domain/test_goals.py
from datetime import date
from freezegun import freeze_time
from zhishi.domain.goals import service as gs
from zhishi.domain.goals.schemas import GoalCreate, KeyResultCreate
from zhishi.domain.habits import service as hs
from zhishi.domain.habits.schemas import HabitCreate
from zhishi.domain.tasks import service as ts
from zhishi.domain.tasks.schemas import TaskCreate


def test_manual_kr(db):
    g = gs.create_goal(db, GoalCreate(title="学期目标", start_date=date(2026, 9, 1),
                                      end_date=date(2026, 12, 31)))
    kr = gs.add_key_result(db, g.id, KeyResultCreate(
        title="读完 12 本书", kind="manual", target_value=12, unit="本"))
    gs.update_kr_progress(db, kr.id, current_value=5)
    cur, pct = gs.kr_progress(db, kr)
    assert cur == 5 and pct == 42  # round(5/12*100)=42（计划原稿 41 为笔误，与 2/3→67 的 round 语义一致）


@freeze_time("2026-09-10")
def test_tag_task_count_kr(db):
    g = gs.create_goal(db, GoalCreate(title="刷题", start_date=date(2026, 9, 1),
                                      end_date=date(2026, 9, 30)))
    gs.add_key_result(db, g.id, KeyResultCreate(
        title="完成 3 道算法题", kind="tag_task_count", target_value=3, unit="题", link="算法"))
    for i in range(2):
        t = ts.create_task(db, TaskCreate(title=f"题{i}", tag_names=["算法"]))
        ts.update_task(db, t.id, status="done")
    krs = gs.goal_progress(db, g.id)
    assert krs[0]["current_value"] == 2.0 and krs[0]["progress"] == 67


def test_habit_checkins_kr(db):
    g = gs.create_goal(db, GoalCreate(title="健康", start_date=date(2026, 9, 1),
                                      end_date=date(2026, 9, 30)))
    gs.add_key_result(db, g.id, KeyResultCreate(
        title="跑步 4 次", kind="habit_checkins", target_value=4, unit="次", link="跑步"))
    h = hs.create_habit(db, HabitCreate(name="跑步"))
    from datetime import date as d
    hs.check_in(db, h.id, d(2026, 9, 2))
    hs.check_in(db, h.id, d(2026, 9, 3))
    krs = gs.goal_progress(db, g.id)
    assert krs[0]["current_value"] == 2.0
