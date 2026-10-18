# -*- coding: utf-8 -*-
"""数据备份与恢复。

安全约定：
* 备份前由调用方执行 WAL checkpoint，zip 中不再包含 ``-wal/-shm``；
* 默认排除 ``.secret.key``、日志与缓存，避免"密文 + 密钥"一起泄露；
* 恢复时拒绝绝对路径、盘符与 ``..``，并先解压到临时目录再复制。
"""
import json
import os
import shutil
import threading
import time
import zipfile
from datetime import datetime

from utils import app_path, ensure_dir, normalize_path, secure_file_permissions
from version import VERSION

_EXCLUDED_NAMES = {".secret.key", "app.log"}
_EXCLUDED_SUFFIXES = (".wal", ".shm", "-wal", "-shm", ".log")
_EXCLUDED_DIRS = {"cache"}


class BackupManager:
    def __init__(self, backup_dir="backups", keep_last=7):
        self.backup_dir = normalize_path(backup_dir)
        os.makedirs(self.backup_dir, exist_ok=True)
        self.keep_last = keep_last
        self.interval_hours = 24
        self._auto_backup_thread = None
        self._auto_backup_stop = threading.Event()

    # ---------- 创建 ----------
    def create(self, include_secrets=False):
        """把 ``data`` 目录打包为 zip，返回路径；失败返回 None。"""
        # 精确到微秒：恢复前会自动创建安全备份，秒级命名可能覆盖同一秒内的目标备份
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        zip_path = os.path.join(self.backup_dir, f"xinyu_backup_{stamp}.zip")
        suffix = 1
        while os.path.exists(zip_path):
            zip_path = os.path.join(self.backup_dir, f"xinyu_backup_{stamp}_{suffix}.zip")
            suffix += 1
        data_dir = app_path("data")
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
                if os.path.isdir(data_dir):
                    for root, dirs, files in os.walk(data_dir):
                        dirs[:] = [d for d in dirs if d not in _EXCLUDED_DIRS]
                        for name in files:
                            if not include_secrets and name in _EXCLUDED_NAMES:
                                continue
                            if name.endswith(_EXCLUDED_SUFFIXES):
                                continue
                            filepath = os.path.join(root, name)
                            arcname = os.path.join(
                                "data", os.path.relpath(filepath, data_dir)
                            ).replace("\\", "/")
                            archive.write(filepath, arcname)

                manifest = {
                    "app": "心语",
                    "version": VERSION,
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "include_secrets": bool(include_secrets),
                }
                archive.writestr(
                    "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2)
                )

            self._cleanup_old_backups()
            secure_file_permissions(zip_path)
            return zip_path
        except Exception as exc:  # noqa: BLE001
            print(f"备份失败: {exc}")
            if os.path.exists(zip_path):
                try:
                    os.remove(zip_path)
                except OSError:
                    pass
            return None

    # ---------- 恢复 ----------
    def restore(self, backup_path):
        """从备份 zip 恢复；返回 ``(ok, message)``。"""
        source = normalize_path(backup_path)
        if not os.path.isfile(source):
            return False, "备份文件不存在"

        try:
            with zipfile.ZipFile(source, "r") as archive:
                if archive.testzip() is not None:
                    return False, "备份文件已损坏"
                members = archive.infolist()
        except zipfile.BadZipFile:
            return False, "备份文件不是有效的 ZIP 格式"
        except Exception as exc:  # noqa: BLE001
            return False, f"读取备份失败: {exc}"

        temp_dir = os.path.join(self.backup_dir, f".restore_{datetime.now():%Y%m%d%H%M%S}")
        try:
            os.makedirs(temp_dir, exist_ok=True)
            with zipfile.ZipFile(source, "r") as archive:
                for member in members:
                    name = member.filename.replace("\\", "/")
                    if name.startswith("/") or ":" in name or ".." in name.split("/"):
                        print(f"跳过非法路径: {name}")
                        continue
                    if name == "manifest.json" or name.endswith("/"):
                        continue
                    # 旧备份可能混入 WAL/SHM，恢复时忽略，避免把备份之后的写入重放回来
                    if name.endswith(("-wal", "-shm")):
                        continue
                    archive.extract(member, temp_dir)

            restored = 0
            for root, _, files in os.walk(temp_dir):
                for name in files:
                    src = os.path.join(root, name)
                    rel = os.path.relpath(src, temp_dir).replace("\\", "/")
                    target = app_path(*rel.split("/"))
                    ensure_dir(target)
                    shutil.copy2(src, target)
                    restored += 1
            return True, f"恢复成功，共 {restored} 个文件"
        except Exception as exc:  # noqa: BLE001
            return False, f"恢复失败: {exc}"
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    # ---------- 查询/删除 ----------
    def list_backups(self):
        if not os.path.isdir(self.backup_dir):
            return []
        names = [name for name in os.listdir(self.backup_dir) if name.endswith(".zip")]
        names.sort(key=lambda name: os.path.getmtime(os.path.join(self.backup_dir, name)), reverse=True)
        return names

    def delete(self, backup_filename):
        name = os.path.basename(str(backup_filename or "").replace("\\", "/"))
        if not name or not name.endswith(".zip") or ".." in name:
            return False, "非法文件名"
        path = os.path.join(self.backup_dir, name)
        if not os.path.isfile(path):
            return False, "文件不存在"
        try:
            os.remove(path)
            return True, "已删除"
        except OSError as exc:
            return False, f"删除失败: {exc}"

    def resolve_backup(self, filename):
        """把用户输入的文件名/相对路径解析为备份目录内的真实文件。"""
        raw = str(filename or "").strip().strip('"')
        name = os.path.basename(raw.replace("\\", "/"))
        candidate = os.path.join(self.backup_dir, name)
        if os.path.isfile(candidate):
            return candidate
        fallback = normalize_path(raw)
        if os.path.isfile(fallback):
            return fallback
        return ""

    def _cleanup_old_backups(self):
        backups = self.list_backups()
        for old in backups[self.keep_last :]:
            try:
                os.remove(os.path.join(self.backup_dir, old))
            except OSError as exc:
                print(f"清理旧备份失败 {old}: {exc}")

    # ---------- 自动备份 ----------
    def schedule_auto_backup(self, interval_hours=None):
        if interval_hours is not None:
            self.interval_hours = max(0.1, float(interval_hours))
        if self._auto_backup_thread and self._auto_backup_thread.is_alive():
            return
        self._auto_backup_stop.clear()

        def loop():
            while not self._auto_backup_stop.is_set():
                if self._backup_due():
                    self.create()
                self._auto_backup_stop.wait(timeout=self.interval_hours * 3600)

        self._auto_backup_thread = threading.Thread(
            target=loop, daemon=True, name="xinyu-auto-backup"
        )
        self._auto_backup_thread.start()

    def _backup_due(self):
        """最近一份备份还在周期内时跳过，避免每次启动都生成 2MB 备份。"""
        backups = self.list_backups()
        if not backups:
            return True
        try:
            age = time.time() - os.path.getmtime(os.path.join(self.backup_dir, backups[0]))
        except OSError:
            return True
        return age >= self.interval_hours * 3600 * 0.9

    def stop_auto_backup(self):
        self._auto_backup_stop.set()
        thread = self._auto_backup_thread
        if thread and thread.is_alive():
            thread.join(timeout=2)
        self._auto_backup_thread = None

    # ---------- 信息/配置 ----------
    def get_backup_info(self):
        backups = self.list_backups()
        latest = backups[0] if backups else None
        return {
            "backup_dir": self.backup_dir,
            "keep_last": self.keep_last,
            "backup_count": len(backups),
            "latest_backup": latest,
            "latest_backup_time": datetime.fromtimestamp(
                os.path.getmtime(os.path.join(self.backup_dir, latest))
            ).isoformat()
            if latest
            else None,
            "backups": backups,
        }

    def get_config(self):
        return {
            "backup_dir": self.backup_dir,
            "keep_last": self.keep_last,
            "interval_hours": self.interval_hours,
        }

    def set_config(self, keep_last=None, interval_hours=None):
        if keep_last is not None and int(keep_last) > 0:
            self.keep_last = int(keep_last)
            self._cleanup_old_backups()
        if interval_hours is not None and float(interval_hours) > 0:
            self.interval_hours = float(interval_hours)
            if self._auto_backup_thread and self._auto_backup_thread.is_alive():
                self.stop_auto_backup()
                self.schedule_auto_backup(self.interval_hours)
        return True, "配置已保存"
