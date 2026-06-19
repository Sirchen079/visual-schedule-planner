from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置。可通过环境变量（前缀 APP_）或 .env 文件覆盖。"""

    model_config = SettingsConfigDict(
        env_prefix="APP_", env_file=".env", extra="ignore"
    )

    database_dir: Path = Path("data")
    files_dir: Path = Path("data/files")
    backup_dir: Path = Path("data/backup")
    host: str = "127.0.0.1"
    port: int = 18731
    # 数据安全感：自动备份保留份数、回收站保留天数、单文件上传上限
    backup_keep: int = 7
    trash_retain_days: int = 30
    max_upload_mb: int = 100

    @property
    def db_path(self) -> Path:
        """SQLite 数据库文件绝对路径。"""
        return self.database_dir / "app.db"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


settings = Settings()
