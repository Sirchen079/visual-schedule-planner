from zhishi.domain.tasks import service as ts
from zhishi.domain.tasks.schemas import TaskCreate
from zhishi.domain import subtasks as st


def test_progress_sync_and_auto_complete(db):
    t = ts.create_task(db, TaskCreate(title="大任务"))
    a = st.create_subtask(db, t.id, title="步骤A")
    b = st.create_subtask(db, t.id, title="步骤B")
    st.update_subtask(db, t.id, a.id, done=True)
    assert ts.get_task(db, t.id).progress == 50
    st.update_subtask(db, t.id, b.id, done=True)
    got = ts.get_task(db, t.id)
    assert got.progress == 100 and got.status == "done" and got.completed_at is not None


def test_delete_resyncs(db):
    t = ts.create_task(db, TaskCreate(title="删子任务"))
    a = st.create_subtask(db, t.id, title="A")
    st.create_subtask(db, t.id, title="B")
    st.update_subtask(db, t.id, a.id, done=True)
    st.delete_subtask(db, t.id, a.id)
    assert ts.get_task(db, t.id).progress == 0  # 剩 1 个未完成
