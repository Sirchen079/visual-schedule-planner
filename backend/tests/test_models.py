from app.schemas import TaskCreate, TaskUpdate
from app.services import task_service


def test_create_and_get_task(db_session):
    task = task_service.create_task(db_session, TaskCreate(title="写论文初稿"))
    assert task.id is not None
    assert task.title == "写论文初稿"
    assert task.status == "待办"
    assert task.progress == 0

    got = task_service.get_task(db_session, task.id)
    assert got is not None
    assert got.title == "写论文初稿"


def test_get_task_not_found(db_session):
    assert task_service.get_task(db_session, 9999) is None


def test_list_tasks_excludes_soft_deleted(db_session):
    task_service.create_task(db_session, TaskCreate(title="任务A"))
    b = task_service.create_task(db_session, TaskCreate(title="任务B"))
    assert len(task_service.list_tasks(db_session)) == 2

    task_service.soft_delete_task(db_session, b.id)
    remaining = task_service.list_tasks(db_session)
    assert len(remaining) == 1
    assert remaining[0].title == "任务A"
    # 软删除后 get 也查不到
    assert task_service.get_task(db_session, b.id) is None


def test_soft_delete_not_found(db_session):
    assert task_service.soft_delete_task(db_session, 9999) is False


def test_update_task_partial(db_session):
    task = task_service.create_task(db_session, TaskCreate(title="旧标题"))
    updated = task_service.update_task(
        db_session, task.id, TaskUpdate(status="进行中", progress=50)
    )
    assert updated is not None
    assert updated.status == "进行中"
    assert updated.progress == 50
    # 未传的字段保持不变
    assert updated.title == "旧标题"


def test_update_task_not_found(db_session):
    assert (
        task_service.update_task(db_session, 9999, TaskUpdate(status="完成")) is None
    )
