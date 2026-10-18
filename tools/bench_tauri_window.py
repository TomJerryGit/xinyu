# -*- coding: utf-8 -*-
"""测量 Tauri spike 从进程启动到“心语”窗口可见的时间。

用法：
    python tools/bench_tauri_window.py --exe spike/tauri/src-tauri/target/release/xinyu-tauri-spike.exe
"""
import argparse
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes


def find_window(pid):
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lparam):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value != pid:
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        if buffer.value.startswith("心语") and user32.IsWindowVisible(hwnd):
            found.append((hwnd, buffer.value))
            return False
        return True

    user32.EnumWindows(callback, 0)
    return found[0] if found else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--exe",
        default=os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "spike", "tauri", "src-tauri", "target", "release", "xinyu-tauri-spike.exe",
        ),
    )
    args = parser.parse_args()
    if not os.path.exists(args.exe):
        print("未找到 Tauri 产物：", args.exe)
        print("本机没有 Rust/MSVC 工具链，无法编译；请在有工具链的机器上 cargo build --release 后重试。")
        return 2
    started = time.perf_counter()
    proc = subprocess.Popen([args.exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    window = None
    deadline = started + 30
    while time.perf_counter() < deadline:
        window = find_window(proc.pid)
        if window:
            break
        if proc.poll() is not None:
            break
        time.sleep(0.05)
    elapsed = time.perf_counter() - started
    print("window:", window, "elapsed_seconds:", round(elapsed, 2), "alive:", proc.poll() is None)
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    return 0 if window else 1


if __name__ == "__main__":
    sys.exit(main())
