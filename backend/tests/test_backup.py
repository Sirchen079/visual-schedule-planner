import sqlite3
from datetime import date, datetime, timedelta

from app.services import backup_service


def _make_db(path) -> None:
    con = sqlite3.connect(str(path))
    con.execute("create table t(x)")
    con.execute("insert into t values (42)")
    con.commit()
    con.close()


def _make_db_with_ai_key(path) -> None:
    con = sqlite3.connect(str(path))
    con.execute(
        """
        create table ai_configs(
            id integer primary key,
            name text not null,
            provider varchar(50) not null,
            model varchar(200) not null,
            api_key text not null,
            extra_headers text default '{}',
            native_web_search_options text default '{}'
        )
        """
    )
    con.execute(
        """
        insert into ai_configs(name, provider, model, api_key, extra_headers, native_web_search_options)
        values (
            'kimi',
            'claude_messages',
            'kimi-for-coding',
            'sk-secret-value',
            '{"Authorization":"Bearer proxy-secret","x-api-key":"header-key","X-Trace":"trace-id"}',
            '{"tools":[{"type":"web_search_20250305","name":"web_search","max_uses":3}],"token":"native-secret-token","user_location":{"country":"CN"}}'
        )
        """
    )
    con.commit()
    con.close()


def _touch_backup(backup_dir, name: str) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    (backup_dir / name).write_bytes(b"")


def test_backup_db_is_valid_copy(tmp_path):
    src = tmp_path / "app.db"
    _make_db(src)
    dest = backup_service.backup_db(db_path=src, backup_dir=tmp_path / "backup")
    assert dest.exists()
    # 备份是真·可读的 sqlite，内容与源一致
    con = sqlite3.connect(str(dest))
    assert con.execute("select x from t").fetchone()[0] == 42
    con.close()


def test_backup_db_redacts_ai_config_api_keys(tmp_path):
    src = tmp_path / "app.db"
    _make_db_with_ai_key(src)

    dest = backup_service.backup_db(db_path=src, backup_dir=tmp_path / "backup")

    con = sqlite3.connect(str(dest))
    api_key = con.execute("select api_key from ai_configs").fetchone()[0]
    con.close()
    assert api_key == ""


def test_backup_db_redacts_sensitive_ai_extra_headers(tmp_path):
    src = tmp_path / "app.db"
    _make_db_with_ai_key(src)

    dest = backup_service.backup_db(db_path=src, backup_dir=tmp_path / "backup")

    con = sqlite3.connect(str(dest))
    headers = con.execute("select extra_headers from ai_configs").fetchone()[0]
    con.close()
    assert headers == '{"X-Trace":"trace-id"}'


def test_backup_db_redacts_sensitive_native_web_search_options(tmp_path):
    src = tmp_path / "app.db"
    _make_db_with_ai_key(src)

    dest = backup_service.backup_db(db_path=src, backup_dir=tmp_path / "backup")

    con = sqlite3.connect(str(dest))
    options = con.execute("select native_web_search_options from ai_configs").fetchone()[0]
    con.close()
    assert '"token"' not in options
    assert '"user_location":{"country":"CN"}' in options
    assert '"web_search_20250305"' in options


def test_prune_keeps_only_n_newest(tmp_path):
    for i in range(5):
        # 日期递增，名字按日期排序即新→旧
        day = (date(2026, 1, 1) + timedelta(days=i)).strftime("%Y%m%d")
        _touch_backup(tmp_path, f"app-{day}-080000.db")
    removed = backup_service.prune_backups(keep=2, backup_dir=tmp_path)
    remaining = backup_service.list_backups(tmp_path)
    assert len(remaining) == 2
    # 留下的是最新的两份
    assert remaining[-1].name.startswith("app-20260105")
    assert len(removed) == 3


def test_backup_if_due_skips_when_db_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_service.settings, "backup_dir", tmp_path)
    monkeypatch.setattr(
        backup_service.settings, "database_dir", tmp_path / "nodata"
    )
    assert backup_service.backup_if_due() is None


def test_backup_if_due_skips_when_already_backed_up_today(tmp_path, monkeypatch):
    src = tmp_path / "app.db"
    _make_db(src)
    monkeypatch.setattr(backup_service.settings, "backup_dir", tmp_path / "backup")
    monkeypatch.setattr(backup_service.settings, "database_dir", tmp_path)
    # 先造一份"今天"的备份
    today = datetime.now().strftime("%Y%m%d")
    _touch_backup(tmp_path / "backup", f"app-{today}-010000.db")
    assert backup_service.backup_if_due() is None


def test_backup_if_due_creates_when_due(tmp_path, monkeypatch):
    src = tmp_path / "app.db"
    _make_db(src)
    backup_dir = tmp_path / "backup"
    monkeypatch.setattr(backup_service.settings, "backup_dir", backup_dir)
    monkeypatch.setattr(backup_service.settings, "database_dir", tmp_path)
    # 只有一份三天前的旧备份 → 今天应再备份一份
    old = (datetime.now() - timedelta(days=3)).strftime("%Y%m%d")
    _touch_backup(backup_dir, f"app-{old}-010000.db")
    created = backup_service.backup_if_due()
    assert created is not None and created.exists()
    assert backup_service.latest_backup_date(backup_dir) == date.today()
