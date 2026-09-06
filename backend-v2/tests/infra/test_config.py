# tests/infra/test_config.py
from zhishi.infra.config import Settings

def test_data_root_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ZHISHI_DATA_DIR", str(tmp_path))
    s = Settings()
    assert s.data_root == tmp_path
    assert s.db_path.parent == tmp_path / "v2"
    assert s.db_path.name == "backend.db"

def test_data_root_default(tmp_path, monkeypatch):
    monkeypatch.delenv("ZHISHI_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    s = Settings()
    assert s.data_root == tmp_path / "data"
