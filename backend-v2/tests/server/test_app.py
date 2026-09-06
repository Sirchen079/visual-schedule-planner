# tests/server/test_app.py
from fastapi.testclient import TestClient
from zhishi.server.app import create_app


def make_client(tmp_path):
    app = create_app(data_dir=tmp_path)
    return TestClient(app)


def test_health(tmp_path):
    with make_client(tmp_path) as c:
        r = c.get("/health")
        assert r.status_code == 200
        assert r.json() == {"ok": True, "version": "2.14.2"}


def test_shutdown(tmp_path):
    with make_client(tmp_path) as c:
        r = c.post("/shutdown")
        assert r.status_code == 200
        assert r.json()["ok"] is True


def test_data_dir_created(tmp_path):
    with make_client(tmp_path) as c:
        c.get("/health")
    assert (tmp_path / "v2" / "backend.db").exists()
    assert (tmp_path / "v2" / "logs" / "app.log").exists()


def test_startup_seeds_builtin_skills(tmp_path):
    with make_client(tmp_path) as c:
        rows = c.get("/ai/skills").json()
    names = [r["name"] for r in rows]
    assert any("任务、提醒与日程" in n for n in names)
    assert all(r["is_builtin"] for r in rows if "内置" in r["name"])
