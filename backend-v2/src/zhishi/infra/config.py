"""数据目录根，优先级：ZHISHI_DATA_DIR 环境变量 > 工作目录 data/。
新版所有数据落在 data_root/v2/ 下，绝不触碰旧版 data/app.db。"""
from __future__ import annotations
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    port: int = 8000
    log_retain_days: int = 14
    backup_keep: int = 7
    trash_retain_days: int = 30

    @property
    def data_root(self) -> Path:
        env = os.environ.get("ZHISHI_DATA_DIR")
        return Path(env) if env else Path.cwd() / "data"

    @property
    def v2_root(self) -> Path:
        return self.data_root / "v2"

    @property
    def db_path(self) -> Path:
        return self.v2_root / "backend.db"

    @property
    def attachments_dir(self) -> Path:
        return self.v2_root / "attachments"

    @property
    def backups_dir(self) -> Path:
        return self.v2_root / "backups"

    @property
    def logs_dir(self) -> Path:
        return self.v2_root / "logs"


def get_settings() -> Settings:
    return Settings()
