import pytest
from zhishi.infra.database import make_engine, make_session_factory, create_all


@pytest.fixture(autouse=True)
def _trusted_test_host(monkeypatch):
    """TestClient 默认 Host=testserver，须注入回环白名单才能穿过 OriginGuard。"""
    monkeypatch.setenv("ZHISHI_TRUSTED_HOSTS", "testserver,127.0.0.1,localhost,::1")


@pytest.fixture(autouse=True)
def _clear_mcp_tools_cache():
    """MCP 工具清单缓存是模块级全局状态，逐测试清空防止串场
    （各测试 db 独立但自增 id 都从 1 起，缓存键会撞）。"""
    from zhishi.adapters import mcp_client
    mcp_client._tools_cache.clear()
    yield
    mcp_client._tools_cache.clear()


@pytest.fixture
def db(tmp_path):
    engine = make_engine(tmp_path / "test.db")
    create_all(engine)
    factory = make_session_factory(engine)
    session = factory()
    yield session
    session.close()
    engine.dispose()
