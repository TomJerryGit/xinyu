# -*- coding: utf-8 -*-
"""单实例互斥：防止两个进程同时写同一个 SQLite。

Windows 使用 ``msvcrt.locking``，类 Unix 使用 ``fcntl.flock``。
锁由操作系统在进程退出时自动释放，因此崩溃不会留下"永远打不开"的锁。
"""
import os

from utils import DATA_ROOT, ensure_dir


class SingleInstance:
    def __init__(self, name="xinyu"):
        self.path = os.path.join(DATA_ROOT, f".{name}.lock")
        self._handle = None

    def acquire(self) -> bool:
        ensure_dir(self.path)
        self._handle = open(self.path, "a+")
        try:
            if os.name == "nt":
                import msvcrt

                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            try:
                self._handle.close()
            except OSError:
                pass
            self._handle = None
            return False

    def release(self):
        if not self._handle:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            self._handle.close()
            self._handle = None


def focus_existing(title_prefix="心语") -> bool:
    """把已经运行的窗口切到前台；找不到时返回 False。"""
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        found = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def callback(hwnd, _lparam):
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                if buffer.value.startswith(title_prefix):
                    found.append(hwnd)
                    return False
            return True

        user32.EnumWindows(callback, 0)
        if not found:
            return False
        hwnd = found[0]
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def notify_already_running():
    """第二个实例的轻提示；失败时静默退出。"""
    if os.name != "nt":
        print("心语已经在运行。")
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            0,
            "心语已经在运行，已为你切换到现有窗口。",
            "心语",
            0x40,  # MB_ICONINFORMATION
        )
    except Exception:
        pass
