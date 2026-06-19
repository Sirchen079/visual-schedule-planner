def test_create_task(client):
    resp = client.post("/tasks", json={"title": "写论文"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "写论文"
    assert data["status"] == "待办"
    assert data["progress"] == 0
    assert "id" in data


def test_create_task_rejects_empty_title(client):
    resp = client.post("/tasks", json={"title": ""})
    assert resp.status_code == 422


def test_list_tasks(client):
    client.post("/tasks", json={"title": "任务A"})
    client.post("/tasks", json={"title": "任务B"})
    resp = client.get("/tasks")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_get_task(client):
    tid = client.post("/tasks", json={"title": "任务X"}).json()["id"]
    resp = client.get(f"/tasks/{tid}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "任务X"


def test_get_task_not_found(client):
    assert client.get("/tasks/9999").status_code == 404


def test_update_task(client):
    tid = client.post("/tasks", json={"title": "旧"}).json()["id"]
    resp = client.put(f"/tasks/{tid}", json={"status": "进行中", "progress": 50})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "进行中"
    assert body["progress"] == 50
    assert body["title"] == "旧"


def test_update_task_not_found(client):
    assert client.put("/tasks/9999", json={"status": "完成"}).status_code == 404


def test_delete_task_is_soft(client):
    tid = client.post("/tasks", json={"title": "要删的"}).json()["id"]
    assert client.delete(f"/tasks/{tid}").status_code == 204
    # 列表里看不到了
    assert client.get(f"/tasks/{tid}").status_code == 404
    assert len(client.get("/tasks").json()) == 0


def test_delete_task_not_found(client):
    assert client.delete("/tasks/9999").status_code == 404


# ---- 回收站：恢复 / 彻底删除 / 超期清理 ----

def test_list_trash_and_restore(client):
    tid = client.post("/tasks", json={"title": "误删"}).json()["id"]
    client.delete(f"/tasks/{tid}")
    # 正常列表为空、回收站有一条
    assert client.get("/tasks").json() == []
    trash = client.get("/tasks/trash").json()
    assert len(trash) == 1
    assert trash[0]["title"] == "误删"
    # 恢复后回到正常列表
    assert client.post(f"/tasks/{tid}/restore").status_code == 200
    assert len(client.get("/tasks").json()) == 1
    assert client.get("/tasks/trash").json() == []


def test_purge_task_removes_permanently(client):
    tid = client.post("/tasks", json={"title": "彻底删"}).json()["id"]
    client.delete(f"/tasks/{tid}")
    assert client.delete(f"/tasks/{tid}/purge").status_code == 204
    assert client.get("/tasks/trash").json() == []
    # 彻底删后无法恢复
    assert client.post(f"/tasks/{tid}/restore").status_code == 404


def test_purge_requires_in_trash(client):
    tid = client.post("/tasks", json={"title": "正常"}).json()["id"]
    # 未软删，不能 purge / restore
    assert client.delete(f"/tasks/{tid}/purge").status_code == 404
    assert client.post(f"/tasks/{tid}/restore").status_code == 404


def test_purge_expired_clears_old_only(db_session):
    from datetime import datetime, timedelta

    from app.models import Task
    from app.services import task_service

    old = Task(title="旧的", deleted_at=datetime.now() - timedelta(days=40))
    recent = Task(title="昨天的", deleted_at=datetime.now() - timedelta(days=1))
    db_session.add_all([old, recent])
    db_session.commit()

    removed = task_service.purge_expired(db_session, retain_days=30)
    assert removed == 1
    assert db_session.get(Task, old.id) is None
    assert db_session.get(Task, recent.id) is not None


# ---- 枚举约束 + progress↔status 联动 ----

def test_create_rejects_invalid_priority(client):
    resp = client.post("/tasks", json={"title": "x", "priority": "紧急"})
    assert resp.status_code == 422


def test_create_rejects_invalid_status(client):
    resp = client.post("/tasks", json={"title": "x", "status": "已取消"})
    assert resp.status_code == 422


def test_update_rejects_invalid_priority(client):
    tid = client.post("/tasks", json={"title": "x"}).json()["id"]
    assert client.put(f"/tasks/{tid}", json={"priority": "无敌"}).status_code == 422


def test_status_done_auto_sets_progress_100(client):
    tid = client.post("/tasks", json={"title": "x", "progress": 30}).json()["id"]
    body = client.put(f"/tasks/{tid}", json={"status": "完成"}).json()
    assert body["status"] == "完成"
    assert body["progress"] == 100


def test_progress_full_auto_sets_done(client):
    tid = client.post("/tasks", json={"title": "x"}).json()["id"]
    body = client.put(f"/tasks/{tid}", json={"progress": 100}).json()
    assert body["progress"] == 100
    assert body["status"] == "完成"


def test_explicit_status_wins_when_both_set(client):
    # 同时显式设 status=进行中 + progress=100：尊重用户显式值
    tid = client.post("/tasks", json={"title": "x"}).json()["id"]
    body = client.put(f"/tasks/{tid}", json={"status": "进行中", "progress": 100}).json()
    assert body["status"] == "进行中"
    assert body["progress"] == 100
