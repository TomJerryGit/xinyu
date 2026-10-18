# -*- coding: utf-8 -*-
"""心语日志模块：写入 ``data/app.log``，带轮转，避免日志无限增长。"""
import logging
import os
from logging.handlers import RotatingFileHandler

from utils import app_path

_LOGGER_NAME = "xinyu"
_MAX_BYTES = 2 * 1024 * 1024
_BACKUP_COUNT = 3


def _build_logger() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if getattr(logger, "_xinyu_configured", False):
        return logger

    log_dir = app_path("data")
    os.makedirs(log_dir, exist_ok=True)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    handler = RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    logger._xinyu_configured = True  # type: ignore[attr-defined]
    return logger


logger = _build_logger()


def log(level: str, msg: str) -> None:
    """按级别写日志，未知级别回退到 info。"""
    method = getattr(logger, str(level).lower(), None)
    if not callable(method):
        method = logger.info
    method(msg)
