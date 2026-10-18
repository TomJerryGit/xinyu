# -*- coding: utf-8 -*-
"""心语通用工具模块。

路径分为两类：
* ``RESOURCE_DIR``：只读资源（templates/static/locales），打包后在 PyInstaller 解包目录；
* ``DATA_ROOT``：可写数据（data/exports/backups），安装版默认位于
  ``%APPDATA%\\Xinyu``，便携版（exe 旁存在 ``portable.flag``）或源码运行时位于程序目录。

这样安装到 Program Files 后仍可正常写入用户数据。
"""
import json
import os
import sys
import tempfile
import time
from datetime import datetime
from typing import Any, Optional

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
    RESOURCE_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    RESOURCE_DIR = BASE_DIR


def _resolve_data_root() -> str:
    override = os.environ.get("XINYU_DATA_DIR", "").strip()
    if override:
        return os.path.abspath(override)
    if getattr(sys, "frozen", False):
        # 便携模式：exe 旁边放一个 portable.flag，数据就留在 exe 目录
        if os.path.exists(os.path.join(BASE_DIR, "portable.flag")):
            return BASE_DIR
        appdata = os.environ.get("APPDATA") or os.path.join(
            os.path.expanduser("~"), "AppData", "Roaming"
        )
        return os.path.join(appdata, "Xinyu")
    return BASE_DIR


DATA_ROOT = _resolve_data_root()


def app_path(*parts: str) -> str:
    """返回基于可写数据目录的绝对路径。"""
    return os.path.join(DATA_ROOT, *parts)


def resource_path(*parts: str) -> str:
    """返回只读资源目录（模板、静态文件、语言包）的绝对路径。"""
    return os.path.join(RESOURCE_DIR, *parts)


def get_data_dir() -> str:
    """返回数据目录路径，若不存在则创建。"""
    data_dir = app_path("data")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def ensure_dir(path: str) -> str:
    """确保目录存在，若不存在则创建。"""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    return path


def safe_json_load(path: str, default: Optional[Any] = None) -> Any:
    """安全地加载 JSON 文件，若文件不存在或解析失败则返回默认值。"""
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def atomic_write_text(path: str, content: str, encoding: str = "utf-8") -> bool:
    """先写临时文件再原子替换，避免写到一半时进程退出导致文件损坏。"""
    try:
        ensure_dir(path)
        directory = os.path.dirname(os.path.abspath(path))
        fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding=encoding) as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            replaced = False
            for attempt in range(4):
                try:
                    os.replace(tmp_path, path)
                    replaced = True
                    break
                except PermissionError:
                    time.sleep(0.04 * (attempt + 1))
            if not replaced:
                # 杀毒软件/索引器短暂占用目标文件时，退化为直接覆盖
                with open(path, "w", encoding=encoding) as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        return True
    except Exception as exc:
        print(f"写入文件失败: {exc}")
        return False


def safe_json_save(path: str, data: Any, indent: int = 2) -> bool:
    """安全地保存 JSON 文件（原子写入，自动创建目录）。"""
    try:
        text = json.dumps(data, ensure_ascii=False, indent=indent)
    except Exception as exc:
        print(f"序列化 JSON 失败: {exc}")
        return False
    return atomic_write_text(path, text)


def normalize_path(path: str) -> str:
    """规范化路径并限制在项目根目录内，越界时返回根目录。

    使用 ``commonpath`` 而不是 ``startswith``，避免 ``D:\\xinyu_evil``
    这类同前缀目录绕过限制。
    """
    if not path:
        return BASE_DIR
    try:
        base = os.path.realpath(DATA_ROOT)
        target = os.path.realpath(path if os.path.isabs(path) else os.path.join(base, path))
        if os.path.commonpath([base, target]) != base:
            return base
        return target
    except (ValueError, OSError):
        return BASE_DIR


def secure_file_permissions(path: str) -> bool:
    """尽量把文件权限收紧到"仅当前用户可读写"。

    Windows 使用 icacls；失败（例如受限账户、无 icacls）时返回 False，
    调用方不应因此中断主流程。
    """
    try:
        if not os.path.exists(path):
            return False
        if os.name == "posix":
            os.chmod(path, 0o600)
            return True
        if os.name == "nt":
            import getpass
            import subprocess

            user = getpass.getuser()
            result = subprocess.run(
                ["icacls", path, "/inheritance:r", "/grant:r", f"{user}:F"],
                check=False,
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        return False
    except Exception as exc:
        print(f"设置文件权限失败: {exc}")
        return False


def get_timestamp_str() -> str:
    """返回文件名安全的时间戳字符串。"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def get_current_datetime() -> str:
    """返回当前时间的 ISO 格式字符串。"""
    return datetime.now().isoformat()


def read_text_file(path: str, default: str = "") -> str:
    """安全地读取 UTF-8 文本文件。"""
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except Exception:
        return default


def write_text_file(path: str, content: str, encoding: str = "utf-8") -> bool:
    """安全地写入文本文件（原子替换）。"""
    return atomic_write_text(path, content, encoding=encoding)


def clamp(value: int, low: int, high: int) -> int:
    """把整数限制在闭区间内。"""
    return max(low, min(high, value))
