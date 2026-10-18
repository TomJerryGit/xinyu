# -*- coding: utf-8 -*-
"""崩溃捕获与诊断包。

目标：用户说"卡住了/闪退了"时，能拿到一份不含隐私的诊断材料。
"""
import json
import os
import platform
import sys
import threading
import traceback
import zipfile
from datetime import datetime

from utils import DATA_ROOT, app_path, ensure_dir, safe_json_load
from version import VERSION


def _crash_dir() -> str:
    return app_path("data", "crash")


def write_crash(exc_type, exc_value, exc_traceback, context="") -> str:
    """把一次未捕获异常写入 ``data/crash``，返回文件路径。"""
    ensure_dir(os.path.join(_crash_dir(), "placeholder"))
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = os.path.join(_crash_dir(), f"crash_{stamp}.txt")
    try:
        lines = [
            f"心语 V{VERSION}",
            f"时间: {datetime.now().isoformat(timespec='seconds')}",
            f"平台: {platform.platform()}",
            f"Python: {sys.version}",
            f"frozen: {getattr(sys, 'frozen', False)}",
            f"数据目录: {DATA_ROOT}",
            f"工作目录: {os.getcwd()}",
            f"上下文: {context}",
            "",
            "".join(traceback.format_exception(exc_type, exc_value, exc_traceback)),
            "",
            "---- app.log tail ----",
        ]
        log_path = app_path("data", "app.log")
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8", errors="replace") as handle:
                lines.extend(handle.readlines()[-80:])
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
    except Exception:
        return ""
    try:
        from metrics import record

        record("crash", file=os.path.basename(path), context=context)
    except Exception:
        pass
    return path


def _hook(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    write_crash(exc_type, exc_value, exc_traceback, context="main")
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


def _thread_hook(args):
    write_crash(
        args.exc_type,
        args.exc_value,
        args.exc_traceback,
        context=f"thread:{getattr(args.thread, 'name', '?')}",
    )


def install_hooks():
    """安装主线程与子线程的崩溃钩子（幂等）。"""
    if getattr(sys, "_xinyu_crash_hooks", False):
        return
    sys.excepthook = _hook
    try:
        threading.excepthook = _thread_hook  # type: ignore[assignment]
    except Exception:
        pass
    sys._xinyu_crash_hooks = True  # type: ignore[attr-defined]


def _redacted_settings():
    settings = safe_json_load(app_path("data", "settings.json"), {})
    if not isinstance(settings, dict):
        return {}
    api = settings.get("api", {}) or {}
    api["api_key"] = "***"
    settings["api"] = api
    return settings


def _db_stats():
    import sqlite3

    lines = []
    for relative in ("data/classics.db", "data/works.db", "data/cache/cache.db"):
        path = app_path(*relative.split("/"))
        if not os.path.exists(path):
            continue
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            lines.append(f"[{relative}]")
            for (table,) in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ):
                count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                lines.append(f"  {table}: {count}")
            try:
                version = conn.execute(
                    "SELECT version FROM schema_migrations WHERE namespace='classics' ORDER BY version DESC LIMIT 1"
                ).fetchone()
                if version:
                    lines.append(f"  schema_version: {version[0]}")
            except Exception:
                pass
            conn.close()
        except Exception as exc:  # noqa: BLE001
            lines.append(f"[{relative}] 读取失败: {exc}")
    return "\n".join(lines)


def build_diagnostics() -> str:
    """生成不含 API Key / 用户正文的诊断 zip，返回路径。"""
    directory = app_path("exports")
    os.makedirs(directory, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(directory, f"xinyu_diagnostics_{stamp}.zip")

    system_text = "\n".join(
        [
            f"心语 V{VERSION}",
            f"平台: {platform.platform()}",
            f"Python: {sys.version}",
            f"frozen: {getattr(sys, 'frozen', False)}",
            f"数据目录: {DATA_ROOT}",
            f"资源目录: {getattr(sys, '_MEIPASS', 'source')}",
        ]
    )

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("system.txt", system_text)
        archive.writestr("db_stats.txt", _db_stats())
        archive.writestr(
            "settings.redacted.json",
            json.dumps(_redacted_settings(), ensure_ascii=False, indent=2),
        )
        log_path = app_path("data", "app.log")
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8", errors="replace") as handle:
                archive.writestr("app.log", handle.read()[-300_000:])
        crash_dir = _crash_dir()
        if os.path.isdir(crash_dir):
            for name in sorted(os.listdir(crash_dir))[-20:]:
                full = os.path.join(crash_dir, name)
                if os.path.isfile(full):
                    with open(full, "r", encoding="utf-8", errors="replace") as handle:
                        archive.writestr(f"crash/{name}", handle.read()[-200_000:])
    return path
