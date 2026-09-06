# src/zhishi/infra/logsetup.py
from __future__ import annotations
import logging
import os
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def setup_logging(logs_dir: Path, console: bool = False) -> Path:
    """幂等配置 root logger；按天滚动 app.log。返回日志文件路径。
    幂等仅指同一 logs_dir；目录变化（测试/多数据根）时替换旧 app.log 处理器。"""
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "app.log"
    root = logging.getLogger()
    target = os.path.abspath(log_file)
    for h in root.handlers:
        if isinstance(h, TimedRotatingFileHandler) and h.baseFilename == target:
            return log_file
    for h in list(root.handlers):
        if isinstance(h, TimedRotatingFileHandler) and h.baseFilename.endswith("app.log"):
            root.handlers.remove(h)
            h.close()
    root.setLevel(logging.INFO)
    fh = TimedRotatingFileHandler(log_file, when="midnight", backupCount=14, encoding="utf-8")
    fh.setFormatter(logging.Formatter(_FMT))
    root.addHandler(fh)
    if console:
        root.addHandler(logging.StreamHandler())
    return log_file
