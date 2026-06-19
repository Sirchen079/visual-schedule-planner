def test_create_subtask(client):
    tid = client.post("/tasks", json={"title": "父"}).json()["id"]
    s = client.post(f"/tasks/{tid}/subtasks", json={"title": "第一步"}).json()
    assert s["title"] == "第一步"
    assert s["done"] is False
    task = client.get(f"/tasks/{tid}").json()
    assert len(task["subtasks"]) == 1


def test_subtask_progress_syncs_to_parent(client):
    tid = client.post("/tasks", json={"title": "父"}).json()["id"]
    client.post(f"/tasks/{tid}/subtasks", json={"title": "a"})
    client.post(f"/tasks/{tid}/subtasks", json={"title": "b"})
    subs = client.get(f"/tasks/{tid}").json()["subtasks"]
    client.put(f"/tasks/{tid}/subtasks/{subs[0]['id']}", json={"done": True})
    task = client.get(f"/tasks/{tid}").json()
    assert task["progress"] == 50


def test_all_subtasks_done_marks_task_complete(client):
    tid = client.post("/tasks", json={"title": "父"}).json()["id"]
    r = client.post(f"/tasks/{tid}/subtasks", json={"title": "a"}).json()
    client.put(f"/tasks/{tid}/subtasks/{r['id']}", json={"done": True})
    task = client.get(f"/tasks/{tid}").json()
    assert task["progress"] == 100
    assert task["status"] == "完成"


def test_delete_subtask(client):
    tid = client.post("/tasks", json={"title": "父"}).json()["id"]
    r = client.post(f"/tasks/{tid}/subtasks", json={"title": "a"}).json()
    assert client.delete(f"/tasks/{tid}/subtasks/{r['id']}").status_code == 204
    assert client.get(f"/tasks/{tid}").json()["subtasks"] == []


def test_subtask_not_found(client):
    tid = client.post("/tasks", json={"title": "父"}).json()["id"]
    assert client.put(f"/tasks/{tid}/subtasks/999", json={"done": True}).status_code == 404
    assert client.post("/tasks/999/subtasks", json={"title": "x"}).status_code == 404


def test_manual_progress_ignored_when_subtasks_exist(client):
    tid = client.post("/tasks", json={"title": "父"}).json()["id"]
    client.post(f"/tasks/{tid}/subtasks", json={"title": "a"})
    client.post(f"/tasks/{tid}/subtasks", json={"title": "b"})
    # 手动设 progress=80 应被完成率(0)覆盖
    body = client.put(f"/tasks/{tid}", json={"progress": 80}).json()
    assert body["progress"] == 0
