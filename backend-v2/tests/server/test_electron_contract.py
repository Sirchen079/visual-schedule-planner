"""桌面后端进程接口测试：指定端口启动、健康检查、关闭、数据目录隔离与静态资源托管。"""
from fastapi.testclient import TestClient
from zhishi.server.app import create_app


def test_static_frontend_served_and_api_coexist(tmp_path, monkeypatch):
    frontend = tmp_path / "frontend" / "dist"
    frontend.mkdir(parents=True)
    (frontend / "index.html").write_text("<html><body>知时 v2</body></html>", encoding="utf-8")
    monkeypatch.setenv("ZHISHI_FRONTEND_DIR", str(frontend))

    data_dir = tmp_path / "data"
    with TestClient(create_app(data_dir=data_dir)) as c:
        r = c.get("/")
        assert r.status_code == 200 and "知时 v2" in r.text
        assert c.get("/health").json()["ok"] is True          # API 与静态共存
        assert c.get("/api/tasks").status_code == 200
        assert c.post("/shutdown").json()["ok"] is True
    assert (data_dir / "v2" / "backend.db").exists()           # 数据根落位


def test_no_frontend_dir_still_boots(tmp_path, monkeypatch):
    monkeypatch.delenv("ZHISHI_FRONTEND_DIR", raising=False)
    with TestClient(create_app(data_dir=tmp_path / "d")) as c:
        assert c.get("/health").json()["ok"] is True           # 纯 API 模式可启动
        assert c.get("/").status_code in (404, 200)            # 无前端时 / 不炸


def test_real_launch_path_no_data_dir(tmp_path, monkeypatch):
    """回归：不传 data_dir 的真实启动路径（曾因 settings 名被路由模块遮蔽而炸）。"""
    monkeypatch.setenv("ZHISHI_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("ZHISHI_FRONTEND_DIR", raising=False)
    with TestClient(create_app()) as c:
        assert c.get("/health").json()["ok"] is True
    assert (tmp_path / "v2" / "backend.db").exists()
