from app.config import Settings


def test_default_settings():
    s = Settings()
    assert s.host == "127.0.0.1"
    assert s.port == 18731
    # 默认数据库目录
    assert s.database_dir.name == "data"
    # 数据安全感默认配置
    assert s.backup_keep == 7
    assert s.trash_retain_days == 30
    assert s.max_upload_mb == 100
    assert s.max_upload_bytes == 100 * 1024 * 1024
    assert s.db_path.name == "app.db"


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("APP_PORT", "9000")
    monkeypatch.setenv("APP_BACKUP_KEEP", "14")
    s = Settings()
    assert s.port == 9000
    assert s.backup_keep == 14
