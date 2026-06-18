from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置。可通过环境变量（前缀 APP_）或 .env 文件覆盖。"""

    model_config = SettingsConfigDict(
        env_prefix="APP_", env_file=".env", extra="ignore"
    )

    database_dir: Path = Path("data")
    files_dir: Path = Path("data/files")
    host: str = "127.0.0.1"
    port: int = 8000


settings = Settings()
