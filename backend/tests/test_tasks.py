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
