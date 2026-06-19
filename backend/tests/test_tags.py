def test_create_task_with_tags(client):
    body = client.post("/tasks", json={"title": "写论文", "tags": ["科研", "导师"]}).json()
    assert [t["name"] for t in body["tags"]] == ["科研", "导师"]
    # 两个新标签分配到不同颜色
    colors = [t["color"] for t in body["tags"]]
    assert len(set(colors)) == 2


def test_tags_get_or_create_reuses(client):
    client.post("/tasks", json={"title": "A", "tags": ["科研"]})
    client.post("/tasks", json={"title": "B", "tags": ["科研"]})
    tags = client.get("/tasks/tags").json()
    assert len(tags) == 1
    assert tags[0]["name"] == "科研"


def test_update_tags_replaces_whole_set(client):
    tid = client.post("/tasks", json={"title": "X", "tags": ["a", "b"]}).json()["id"]
    body = client.put(f"/tasks/{tid}", json={"tags": ["b", "c"]}).json()
    assert [t["name"] for t in body["tags"]] == ["b", "c"]


def test_task_without_tags_has_empty_list(client):
    body = client.post("/tasks", json={"title": "无标"}).json()
    assert body["tags"] == []


def test_tags_endpoint_lists_all(client):
    client.post("/tasks", json={"title": "X", "tags": ["科研", "杂事"]})
    names = [t["name"] for t in client.get("/tasks/tags").json()]
    assert "科研" in names and "杂事" in names


def test_tags_deduped_and_trimmed(client):
    body = client.post(
        "/tasks", json={"title": "X", "tags": ["  科研 ", "科研", ""]}
    ).json()
    assert [t["name"] for t in body["tags"]] == ["科研"]
