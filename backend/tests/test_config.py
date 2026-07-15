from pathlib import Path

from app.config import Settings, _resolve_data_root


def test_default_settings(monkeypatch):
    # 防止开发者 shell 里手动设置的便携测试变量翻转默认值
    monkeypatch.delenv("ZHISHI_DATA_DIR", raising=False)
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


def test_data_root_dev_default(monkeypatch):
    # 开发模式（非 frozen、无 env）：相对当前工作目录的 data/
    monkeypatch.delenv("ZHISHI_DATA_DIR", raising=False)
    monkeypatch.setattr("sys.frozen", False, raising=False)
    assert _resolve_data_root() == Path("data")


def test_data_root_env_overrides(monkeypatch, tmp_path):
    # ZHISHI_DATA_DIR 优先级最高，便携式安装目录由此传入
    monkeypatch.setenv("ZHISHI_DATA_DIR", str(tmp_path))
    assert _resolve_data_root() == tmp_path


def test_data_root_frozen_fallback_to_appdata(monkeypatch, tmp_path):
    # 打包模式、无 env、且 _find_portable_root 找不到已迁移的便携库时，回退到 APPDATA
    monkeypatch.delenv("ZHISHI_DATA_DIR", raising=False)
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert _resolve_data_root() == tmp_path / "知时" / "data"

