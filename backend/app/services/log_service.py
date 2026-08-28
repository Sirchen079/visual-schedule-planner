"""文件日志：按天滚动写入 <数据根>/logs/，启动时清理超过保留天数的旧日志。

排查"永远正在思考"等运行时问题的关键基础设施——此前 console=False（无黑窗）
导致 uvicorn 与异常日志全部丢失，问题无从定位。

设计：
- 单一 setup_logging() 在 launcher 启动时调用一次，配置 root logger + uvicorn logger。
- TimedRotatingFileHandler 按天滚动：app.log → app.log.2026-07-22 → ...
- 启动时扫描 logs_dir，删除早于 log_retain_days 的文件（含滚动归档）。
- 控制台输出仅在开发模式（非 frozen）保留，打包后纯文件输出。
"""
from __future__ import annotations

import logging
import os
import sys
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from app.config import settings

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def setup_logging() -> Path:
    """配置全局文件日志。返回日志文件路径。幂等：多次调用只配置一次。"""
    global _configured
    log_dir = settings.logs_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"

    if _configured:
        return log_file

    # 先清理过期日志，避免无限堆积
    _prune_old_logs(log_dir, settings.log_retain_days)

    level = logging.INFO
    fmt = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    root = logging.getLogger()
    root.setLevel(level)

    # 文件 handler：按天滚动，午夜切割。保留份数给一个足够大的值，由 _prune_old_logs 按天数兜底清理。
    file_handler = TimedRotatingFileHandler(
        log_file, when="midnight", interval=1, backupCount=30, encoding="utf-8", utc=False
    )
    file_handler.suffix = "%Y-%m-%d"
    file_handler.setFormatter(fmt)
    file_handler.setLevel(level)
    root.addHandler(file_handler)

    # 开发模式（非打包）同时输出控制台；打包后 console=False 无 stdout，省略
    if not getattr(sys, "frozen", False):
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(fmt)
        stream_handler.setLevel(level)
        root.addHandler(stream_handler)

    # uvicorn 的日志走它自己的 logger，需显式接管，否则默认只输出到 stderr（打包后丢失）
    for uv_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(uv_name)
        uv_logger.handlers = [file_handler] if getattr(sys, "frozen", False) else [file_handler, stream_handler]
        uv_logger.setLevel(level)
        uv_logger.propagate = False

    _configured = True
    logging.getLogger(__name__).info(
        "日志系统就绪：log_dir=%s, retain_days=%d", log_dir, settings.log_retain_days
    )
    return log_file


def _prune_old_logs(log_dir: Path, retain_days: int) -> None:
    """删除 logs_dir 下早于 retain_days 天的日志文件（含滚动归档 app.log.YYYY-MM-DD）。"""
    if retain_days <= 0:
        return
    cutoff = time.time() - retain_days * 86400
    try:
        for entry in log_dir.iterdir():
            if not entry.is_file():
                continue
            # 只动 app.log 及其滚动归档，避免误删无关文件
            name = entry.name
            if name != "app.log" and not name.startswith("app.log."):
                continue
            try:
                mtime = entry.stat().st_mtime
            except OSError:
                continue
            if mtime < cutoff:
                entry.unlink(missing_ok=True)
    except OSError:
        # 清理失败不影响启动
        pass
