"""B1 安全加固回归：
1) Origin 防护中间件：带 Origin 且 host 与请求 Host 不一致 → 403
   （防 DNS rebinding / 恶意网页跨站读取）；同源与无 Origin（Electron/curl）放行；
2) Electron 进程契约不受影响：/health、/shutdown、静态 / 无 Origin 均可用。"""
from fastapi.testclient import TestClient
from zhishi.server.app import create_app


def test_malicious_origin_blocked(tmp_path):
    """外部恶意页跨站请求：Origin host ≠ 请求 Host → 403，响应不可读。"""
    with TestClient(create_app(data_dir=tmp_path)) as c:
        r = c.get("/health", headers={"Origin": "http://evil.example.com"})
        assert r.status_code == 403


def test_origin_port_mismatch_blocked(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        r = c.get("/health", headers={"Origin": "http://testserver:9999"})
        assert r.status_code == 403


def test_same_origin_and_no_origin_pass(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as c:
        # 同源（TestClient Host=testserver）：放行
        assert c.get("/health", headers={"Origin": "http://testserver"}).status_code == 200
        # 无 Origin（curl / 旧 Electron 壳直接拉起）：放行
        assert c.get("/health").status_code == 200
        # Electron 契约：/shutdown 免认证可用
        assert c.post("/shutdown").json()["ok"] is True


def test_electron_static_contract_survives_guard(tmp_path, monkeypatch):
    """同源加载静态页 + API 共存（BrowserWindow 同源请求不得被拦）。"""
    frontend = tmp_path / "frontend" / "dist"
    frontend.mkdir(parents=True)
    (frontend / "index.html").write_text("<html>知时</html>", encoding="utf-8")
    monkeypatch.setenv("ZHISHI_FRONTEND_DIR", str(frontend))
    with TestClient(create_app(data_dir=tmp_path / "d")) as c:
        assert c.get("/").status_code == 200 and "知时" in c.get("/").text
        assert c.get("/api/tasks", headers={"Origin": "http://testserver"}).status_code == 200
        assert c.get("/api/tasks", headers={"Origin": "http://evil.example.com"}).status_code == 403


def test_dns_rebinding_host_blocked(tmp_path):
    """1：Host 与 Origin 同为攻击域名（DNS rebinding）也必须拦截——
    Host hostname 钉死在回环白名单（127.0.0.1/localhost/::1），非白名单一律 403。"""
    app = create_app(data_dir=tmp_path)
    with TestClient(app, base_url="http://rebind.evil:8421") as c:
        r = c.get("/health", headers={"Origin": "http://rebind.evil:8421"})
        assert r.status_code == 403, "rebinding 场景（Host=Origin=攻击域）未被拦截"
    with TestClient(app, base_url="http://rebind.evil:8421") as c:
        assert c.get("/health").status_code == 403, "仅伪造 Host 也应被拦截"
