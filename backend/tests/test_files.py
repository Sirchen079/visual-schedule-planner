def test_upload_and_list_file(client):
    resp = client.post(
        "/files",
        files={"file": ("paper.pdf", b"pdf-bytes", "application/pdf")},
        data={"notes": "文献"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["original_name"] == "paper.pdf"
    assert data["mime_type"] == "application/pdf"
    assert data["size"] == len(b"pdf-bytes")
    assert data["notes"] == "文献"

    listed = client.get("/files").json()
    assert len(listed) == 1
    assert listed[0]["original_name"] == "paper.pdf"


def test_search_file(client):
    client.post("/files", files={"file": ("alpha.txt", b"a", "text/plain")})
    client.post("/files", files={"file": ("beta.txt", b"b", "text/plain")})
    resp = client.get("/files?q=alpha")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["original_name"] == "alpha.txt"


def test_get_file_content(client):
    fid = client.post(
        "/files",
        files={"file": ("note.txt", b"hello", "text/plain")},
    ).json()["id"]
    resp = client.get(f"/files/{fid}/content")
    assert resp.status_code == 200
    assert resp.content == b"hello"


def test_soft_delete_file(client):
    fid = client.post(
        "/files",
        files={"file": ("trash.txt", b"x", "text/plain")},
    ).json()["id"]
    assert client.delete(f"/files/{fid}").status_code == 204
    assert client.get(f"/files/{fid}").status_code == 404
    assert client.get("/files").json() == []


def test_attach_and_detach_file_to_task(client):
    task_id = client.post("/tasks", json={"title": "读论文"}).json()["id"]
    file_id = client.post(
        "/files",
        files={"file": ("paper.pdf", b"pdf", "application/pdf")},
    ).json()["id"]

    assert client.post(f"/tasks/{task_id}/files/{file_id}").status_code == 204
    task = client.get(f"/tasks/{task_id}").json()
    assert len(task["files"]) == 1
    assert task["files"][0]["original_name"] == "paper.pdf"

    files = client.get(f"/tasks/{task_id}/files").json()
    assert len(files) == 1

    assert client.delete(f"/tasks/{task_id}/files/{file_id}").status_code == 204
    assert client.get(f"/tasks/{task_id}/files").json() == []
