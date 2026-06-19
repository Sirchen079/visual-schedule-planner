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


# ---- 文件回收站：恢复 / 彻底删除（含磁盘清理） ----

def test_file_trash_restore_and_purge(client):
    fid = client.post("/files", files={"file": ("a.txt", b"hello", "text/plain")}).json()["id"]
    client.delete(f"/files/{fid}")
    # 正常列表空、回收站有一条
    assert client.get("/files").json() == []
    assert len(client.get("/files/trash").json()) == 1
    # 恢复
    assert client.post(f"/files/{fid}/restore").status_code == 200
    assert len(client.get("/files").json()) == 1
    assert client.get("/files/trash").json() == []
    # 再次软删后彻底清除
    client.delete(f"/files/{fid}")
    assert client.delete(f"/files/{fid}/purge").status_code == 204
    assert client.get("/files/trash").json() == []
    assert client.post(f"/files/{fid}/restore").status_code == 404


def test_file_purge_requires_in_trash(client):
    fid = client.post("/files", files={"file": ("b.txt", b"x", "text/plain")}).json()["id"]
    # 未软删，purge / restore 都应 404
    assert client.delete(f"/files/{fid}/purge").status_code == 404
    assert client.post(f"/files/{fid}/restore").status_code == 404


def test_purge_file_deletes_disk_content(db_session, tmp_path, monkeypatch):
    from datetime import datetime

    from app.models import File
    from app.services import file_service

    disk = tmp_path / "real.txt"
    disk.write_bytes(b"data")
    # 让 content_path 指向我们准备的磁盘文件
    monkeypatch.setattr(file_service, "content_path", lambda f: disk)

    f = File(
        original_name="real.txt",
        storage_path="ignored",
        size=4,
        mime_type="text/plain",
        deleted_at=datetime.now(),
    )
    db_session.add(f)
    db_session.commit()

    assert file_service.purge_file(db_session, f.id) is True
    # 磁盘文件 + 数据库记录都被清除
    assert not disk.exists()
    assert db_session.get(File, f.id) is None


def test_upload_rejects_oversize(client, monkeypatch):
    from app.services import file_service

    monkeypatch.setattr(file_service.settings, "max_upload_mb", 0)
    # 0MB 上限 → 任意非空文件被拒
    resp = client.post(
        "/files",
        files={"file": ("big.bin", b"x" * 10, "application/octet-stream")},
    )
    assert resp.status_code == 413
    # 不留垃圾记录
    assert client.get("/files").json() == []
