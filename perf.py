# -*- coding: utf-8 -*-
"""启动性能打点。

``app.py`` 在导入任何重模块之前调用 :func:`begin`，关键节点调用 :func:`mark`，
窗口加载完成后 :func:`dump` 写入 ``data/perf/startup.jsonl`` 与
``startup_latest.json``，同时记入本地指标。
"""
import json
import os
import platform
import sys
import time

from utils import app_path
from version import VERSION

_start = time.perf_counter()
_marks = []
_dumped = False


def begin(start: float = None):
    global _start
    _start = float(start) if start else time.perf_counter()


def mark(name: str, **extra):
    """记录一个相对启动的毫秒节点。"""
    _marks.append(
        {
            "name": name,
            "ms": round((time.perf_counter() - _start) * 1000, 1),
            "extra": extra,
        }
    )


def snapshot(context="startup"):
    return {
        "context": context,
        "version": VERSION,
        "frozen": bool(getattr(sys, "frozen", False)),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "total_ms": round((time.perf_counter() - _start) * 1000, 1),
        "marks": list(_marks),
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def dump(context="startup"):
    global _dumped
    if _dumped:
        return _latest_path()
    _dumped = True
    data = snapshot(context)
    directory = app_path("data", "perf")
    os.makedirs(directory, exist_ok=True)
    latest = os.path.join(directory, "startup_latest.json")
    history = os.path.join(directory, "startup.jsonl")
    try:
        with open(latest, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        with open(history, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(data, ensure_ascii=False) + "\n")
    except OSError:
        pass
    try:
        from metrics import record

        record(
            "startup",
            total_ms=data["total_ms"],
            frozen=data["frozen"],
            marks={item["name"]: item["ms"] for item in data["marks"]},
        )
    except Exception:
        pass
    return latest


def _latest_path():
    return app_path("data", "perf", "startup_latest.json")


def read_latest():
    path = _latest_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return {}
