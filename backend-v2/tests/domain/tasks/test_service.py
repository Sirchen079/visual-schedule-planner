# tests/domain/tasks/test_service.py
import pytest
from datetime import datetime
from zhishi.domain.tasks import service as ts
from zhishi.domain.tasks.schemas import TaskCreate


def test_create_and_get(db):
    t = ts.create_task(db, TaskCreate(title="写周报", priority="high", tag_names=["工作"]))
    assert t.id is not None
    got = ts.get_task(db, t.id)
    assert got.title == "写周报"
    assert [x.name for x in got.tags] == ["工作"]


def test_list_filters(db):
    ts.create_task(db, TaskCreate(title="A", status="done"))
    ts.create_task(db, TaskCreate(title="B", priority="high"))
    assert [x.title for x in ts.list_tasks(db, status="todo")] == ["B"]
    assert [x.title for x in ts.list_tasks(db, priority="high")] == ["B"]


def test_update(db):
    t = ts.create_task(db, TaskCreate(title="旧"))
    ts.update_task(db, t.id, title="新", notes="加了说明")
    got = ts.get_task(db, t.id)
    assert got.title == "新" and got.notes == "加了说明"


def test_trash_flow(db):
    t = ts.create_task(db, TaskCreate(title="删我"))
    ts.soft_delete_task(db, t.id)
    assert [x.title for x in ts.list_tasks(db)] == []
    assert [x.title for x in ts.list_trash(db)] == ["删我"]
    ts.restore_task(db, t.id)
    assert len(ts.list_tasks(db)) == 1
    ts.soft_delete_task(db, t.id)
    ts.purge_task(db, t.id)
    assert ts.list_trash(db) == []
    with pytest.raises(LookupError):
        ts.get_task(db, t.id)


def test_purge_task_cascades_related_rows(db):
    """M3 回归：带排期/标签/附件/子任务/计时/通知的任务 purge 必须成功
    （FK 开启下曾被 task_schedule_entries 等关联行阻断），且关联表无孤儿行。"""
    from datetime import date
    from zhishi.domain.models import (LibraryFile, NotificationLog, Subtask,
                                      TaskScheduleEntry, TimeLog, task_file, task_tag)
    from zhishi.domain.library import service as ls
    from zhishi.domain.schedule import service as ss

    t = ts.create_task(db, TaskCreate(title="全关联任务", tag_names=["工作"]))
    ss.assign_task_to_day(db, t.id, date.today(), source="manual")     # 排期
    f = LibraryFile(original_name="a.txt", storage_path="files/a.txt", size=5)
    db.add(f); db.commit()
    ls.attach_to_task(db, t.id, f.id)                                  # 附件
    db.add(Subtask(task_id=t.id, title="子任务")); db.commit()          # 子任务
    db.add(TimeLog(task_id=t.id, task_title="全关联任务",
                   started_at=datetime.now(), minutes=25)); db.commit()  # 计时
    db.add(NotificationLog(task_id=t.id, title="提醒",
                           remind_at=datetime.now())); db.commit()     # 通知

    ts.soft_delete_task(db, t.id)
    ts.purge_task(db, t.id)   # 修复前：IntegrityError（FK）

    assert db.query(TaskScheduleEntry).filter_by(task_id=t.id).count() == 0
    assert db.execute(task_tag.select().where(task_tag.c.task_id == t.id)).all() == []
    assert db.execute(task_file.select().where(task_file.c.task_id == t.id)).all() == []
    assert db.query(Subtask).filter_by(task_id=t.id).count() == 0
    # 计时/通知日志按设计保留（统计靠冗余 task_title 延续）：行还在，task_id 置空
    tl = db.query(TimeLog).filter_by(task_title="全关联任务").one()
    assert tl.task_id is None
    nl = db.query(NotificationLog).filter_by(title="提醒").one()
    assert nl.task_id is None


def test_remind_offsets_serialized(db):
    t = ts.create_task(db, TaskCreate(title="提醒", remind_offsets=[0, 30, 1440]))
    assert ts.get_task(db, t.id).remind_offset_list == [0, 30, 1440]
