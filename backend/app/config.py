from __future__ import annotations

import os
import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_portable_root() -> Path | None:
    """定位便携安装根目录（含 知时.exe 的目录）。

    打包后后端 exe 位于 <安装根>/resources/zhishi-backend/，从 exe 向上查找
    包含 知时.exe 的目录，即可靠地定位安装根，不依赖固定的目录层级。
    仅在打包模式下生效；开发模式返回 None。
    """
    if not getattr(sys, "frozen", False):
        return None
    exe_dir = Path(sys.executable).resolve().parent
    for candidate in [exe_dir, *exe_dir.parents]:
        if (candidate / "知时.exe").exists():
            return candidate
    return None


def _resolve_data_root() -> Path:
    """数据目录根，优先级从高到低：

    1. 环境变量 ZHISHI_DATA_DIR（Electron 主进程拉起后端时显式传入，最可靠）；
    2. 打包便携模式：<安装根>/data（数据跟随软件，避开 C 盘 AppData 被塞爆）；
    3. 打包回退：%APPDATA%/知时/data（旧版兼容 / 后端被独立拉起时）；
    4. 开发模式：相对当前工作目录的 data/。
    """
    env_root = os.environ.get("ZHISHI_DATA_DIR")
    if env_root:
        return Path(env_root)
    if getattr(sys, "frozen", False):
        portable = _find_portable_root()
        # 仅当便携位置已有数据库时才采用：避免后端被独立运行（无 ZHISHI_DATA_DIR）
        # 时在安装目录新建空库，进而阻止 Electron 迁移、孤立用户历史数据。
        # 同时也消解 _find_portable_root 命中祖先残留 知时.exe 的风险——错误根下不会有 app.db。
        if portable is not None and (portable / "data" / "app.db").exists():
            return portable / "data"
        appdata = os.environ.get("APPDATA") or str(Path.home())
        return Path(appdata) / "知时" / "data"
    return Path("data")


# 模块级求值一次；APP_DATABASE_DIR / APP_FILES_DIR 等环境变量仍可覆盖单个字段
_DATA_ROOT = _resolve_data_root()


class Settings(BaseSettings):
    """应用配置。可通过环境变量（前缀 APP_）或 .env 文件覆盖。"""

    model_config = SettingsConfigDict(
        env_prefix="APP_", env_file=".env", extra="ignore"
    )

    database_dir: Path = _DATA_ROOT
    files_dir: Path = _DATA_ROOT / "files"
    ai_attachments_dir: Path = _DATA_ROOT / "ai_attachments"
    backup_dir: Path = _DATA_ROOT / "backup"
    # 日志目录：跟随数据根（安装目录/data/logs），避开 C 盘；排查"永远思考"等问题所需
    logs_dir: Path = _DATA_ROOT / "logs"
    host: str = "127.0.0.1"
    port: int = 18731
    # 数据安全感：自动备份保留份数、回收站保留天数、单文件上传上限
    backup_keep: int = 7
    trash_retain_days: int = 30
    # 日志保留天数：超过则启动时自动清理（按天滚动文件）
    log_retain_days: int = 3
    max_upload_mb: int = 100
    max_ai_attachment_mb: int = 50
    max_ai_inline_image_mb: int = 12
    max_ai_text_chars: int = 120000
    # iCal 导入上限：日历订阅/全年导出文件可能很大，5MB 过窄，放宽到 50MB
    max_ical_mb: int = 50
    # Agent 连续工作步数预算上限（每轮可调用的工具轮次）。默认 15：
    # 既给多步任务（调研→计划→执行→复核）留足空间，又避免失控死循环。
    # env APP_AGENT_MAX_STEPS 可覆盖；前端设置面板也可逐实例调整（范围 3-30）。
    agent_max_steps: int = 15

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

    @property
    def max_ical_bytes(self) -> int:
        return self.max_ical_mb * 1024 * 1024


settings = Settings()
