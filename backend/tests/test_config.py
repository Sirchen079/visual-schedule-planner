from app.config import Settings


def test_default_settings():
    s = Settings()
    assert s.host == "127.0.0.1"
    assert s.port == 18731
    # 默认数据库目录
    assert s.database_dir.name == "data"


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("APP_PORT", "9000")
    s = Settings()
    assert s.port == 9000
