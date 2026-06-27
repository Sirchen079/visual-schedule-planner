"""数据库自动备份。

设计要点：
- 用 SQLite 在线 backup API（而非直接拷贝文件），避免拷到一半页不一致；
- 启动时若当天已备份过则跳过（幂等），并按 backup_keep 清理超额旧备份；
- 全部落在 data/backup/，已被 gitignore，可随 data/ 整体搬迁。
"""

from __future__ import annotations

import re
import sqlite3
import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from app.config import settings
from app.services import ai_config_service

_NAME_RE = re.compile(r"app-(\d{8})-\d{6}\.db$")


def _backup_name(when: datetime) -> str:
    return f"app-{when.strftime('%Y%m%d-%H%M%S')}.db"


def _date_of(path: Path) -> Optional[date]:
    m = _NAME_RE.search(path.name)
    if not m:
        return None
    return datetime.strptime(m.group(1), "%Y%m%d").date()


def backup_db(
    db_path: Optional[Path] = None,
    backup_dir: Optional[Path] = None,
) -> Path:
    """复制源数据库到 backup_dir，返回备份文件路径。"""
    src_path = db_path or settings.db_path
    dest_dir = backup_dir or settings.backup_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / _backup_name(datetime.now())

    src = sqlite3.connect(str(src_path))
    dst = sqlite3.connect(str(dest))
    try:
        src.backup(dst)
        _redact_ai_secrets(dst)
    finally:
        dst.close()
        src.close()
    return dest


def _redact_ai_secrets(conn: sqlite3.Connection) -> None:
    tables = {
        row[0]
        for row in conn.execute(
            "select name from sqlite_master where type = 'table'"
        ).fetchall()
    }
    if "ai_configs" not in tables:
        return
    columns = [row[1] for row in conn.execute("PRAGMA table_info(ai_configs)")]
    if "api_key" not in columns:
        return
    conn.execute("UPDATE ai_configs SET api_key = ''")
    if "extra_headers" in columns:
        for row_id, raw_headers in conn.execute(
            "SELECT id, extra_headers FROM ai_configs"
        ).fetchall():
            headers = ai_config_service.headers_from_json(raw_headers)
            redacted = {
                name: value
                for name, value in headers.items()
                if not ai_config_service.is_sensitive_header(name)
            }
            conn.execute(
                "UPDATE ai_configs SET extra_headers = ? WHERE id = ?",
                (json.dumps(redacted, ensure_ascii=False, separators=(",", ":")), row_id),
            )
    conn.commit()


def list_backups(backup_dir: Optional[Path] = None) -> list[Path]:
    dest_dir = backup_dir or settings.backup_dir
    if not dest_dir.exists():
        return []
    return sorted((p for p in dest_dir.glob("app-*.db") if _date_of(p)), key=lambda p: p.name)


def latest_backup_date(backup_dir: Optional[Path] = None) -> Optional[date]:
    backups = list_backups(backup_dir)
    return _date_of(backups[-1]) if backups else None


def prune_backups(
    keep: Optional[int] = None,
    backup_dir: Optional[Path] = None,
) -> list[Path]:
    """保留最近 keep 份，删除更老的。返回被删除的文件列表。"""
    keep = settings.backup_keep if keep is None else keep
    backups = list_backups(backup_dir)
    if keep >= len(backups):
        return []
    to_remove = backups[: len(backups) - keep]
    for p in to_remove:
        p.unlink(missing_ok=True)
    return to_remove


def backup_if_due() -> Optional[Path]:
    """启动时调用：今天还没备份过则备份一份，并清理超额旧备份。"""
    if not settings.db_path.exists():
        return None
    if latest_backup_date() == date.today():
        return None
    created = backup_db()
    prune_backups()
    return created
