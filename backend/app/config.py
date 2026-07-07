import os
import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_root() -> Path:
    """数据目录根。

    开发模式：相对当前工作目录的 data/（保持原行为）。
    打包模式（PyInstaller frozen）：写入 %APPDATA%/知时/data，
    避免安装目录（Program Files）不可写导致的数据丢失。
    """
    if getattr(sys, "frozen", False):
        appdata = os.environ.get("APPDATA") or str(Path.home())
        return Path(appdata) / "知时" / "data"
    return Path("data")


# 模块级求值一次；APP_DATABASE_DIR / APP_FILES_DIR 等环境变量仍可覆盖单个字段
_DATA_ROOT = _default_data_root()


class Settings(BaseSettings):
    """应用配置。可通过环境变量（前缀 APP_）或 .env 文件覆盖。"""

    model_config = SettingsConfigDict(
        env_prefix="APP_", env_file=".env", extra="ignore"
    )

    database_dir: Path = _DATA_ROOT
    files_dir: Path = _DATA_ROOT / "files"
    ai_attachments_dir: Path = _DATA_ROOT / "ai_attachments"
    backup_dir: Path = _DATA_ROOT / "backup"
    host: str = "127.0.0.1"
    port: int = 18731
    # 数据安全感：自动备份保留份数、回收站保留天数、单文件上传上限
    backup_keep: int = 7
    trash_retain_days: int = 30
    max_upload_mb: int = 100
    max_ai_attachment_mb: int = 50
    max_ai_inline_image_mb: int = 12
    max_ai_text_chars: int = 120000

    @property
    def db_path(self) -> Path:
        """SQLite 数据库文件绝对路径。"""
        return self.database_dir / "app.db"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def max_ai_attachment_bytes(self) -> int:
        return self.max_ai_attachment_mb * 1024 * 1024

    @property
    def max_ai_inline_image_bytes(self) -> int:
        return self.max_ai_inline_image_mb * 1024 * 1024


settings = Settings()
