# -*- coding: utf-8 -*-
"""心语桌面端入口。

生产级约定：
* 数据目录与资源目录分离，安装到 Program Files 也能写入用户数据；
* 单实例互斥，第二个实例会唤起已有窗口；
* 启动即安装崩溃钩子，未捕获异常落盘到 data/crash。
"""
import os
import sys
import time
import warnings

_ENTRY = time.perf_counter()

BASE_DIR = (
    os.path.dirname(os.path.abspath(sys.executable))
    if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.abspath(__file__))
)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault("MMKV_LOG_LEVEL", "off")
warnings.filterwarnings("ignore")

from perf import begin, dump, mark  # noqa: E402

begin(_ENTRY)
mark("path_ready")

import webview  # noqa: E402

mark("webview_import")

from api import API  # noqa: E402
from crash_reporter import install_hooks, write_crash  # noqa: E402
from html_ui import HTML  # noqa: E402
from single_instance import (  # noqa: E402
    SingleInstance,
    focus_existing,
    notify_already_running,
)
from utils import DATA_ROOT  # noqa: E402
from version import APP_NAME, VERSION  # noqa: E402

mark("modules_imported")


def main():
    mark("main_start")
    os.makedirs(DATA_ROOT, exist_ok=True)
    os.chdir(DATA_ROOT)
    mark("data_root")

    api = API()
    mark("api_init")
    api.backup_mgr.schedule_auto_backup(interval_hours=24)

    webview.create_window(
        f"{APP_NAME} V{VERSION}",
        html=HTML,
        js_api=api,
        width=1160,
        height=780,
        min_size=(900, 620),
    )
    mark("window_created")

    def on_loaded():
        try:
            mark("window_loaded")
            # 先落盘，避免聚焦/显示失败时丢失启动数据
            dump("startup")
        except Exception as exc:  # noqa: BLE001
            print(f"记录启动打点失败: {exc}")

    debug = os.environ.get("XINYU_DEBUG", "0") == "1"
    try:
        mark("webview_start")
        webview.start(on_loaded, debug=debug, private_mode=False)
    finally:
        api.close()


def run() -> int:
    install_hooks()
    guard = SingleInstance()
    if not guard.acquire():
        focus_existing()
        notify_already_running()
        return 1
    try:
        main()
        return 0
    except Exception:
        try:
            dump("startup_failed")
        except Exception:
            pass
        write_crash(*sys.exc_info(), context="startup")
        raise
    finally:
        guard.release()


if __name__ == "__main__":
    raise SystemExit(run())
