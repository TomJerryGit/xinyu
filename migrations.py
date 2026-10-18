# -*- coding: utf-8 -*-
"""轻量数据库迁移框架。

每个数据库一个命名空间，``schema_migrations`` 记录已应用版本。
迁移前会通过 SQLite 在线备份生成 ``.pre_vX.bak``，失败时保留现场。
"""
import os
import sqlite3
from datetime import datetime


class Migrator:
    def __init__(self, conn: sqlite3.Connection, db_path: str, namespace: str):
        self.conn = conn
        self.db_path = db_path
        self.namespace = namespace
        self._ensure_table()

    def _ensure_table(self):
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                namespace TEXT NOT NULL,
                version INTEGER NOT NULL,
                applied_at TEXT NOT NULL,
                PRIMARY KEY (namespace, version)
            )
            """
        )
        self.conn.commit()

    def current(self) -> int:
        row = self.conn.execute(
            "SELECT MAX(version) FROM schema_migrations WHERE namespace = ?",
            (self.namespace,),
        ).fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    def applied(self):
        return [
            row[0]
            for row in self.conn.execute(
                "SELECT version FROM schema_migrations WHERE namespace = ? ORDER BY version",
                (self.namespace,),
            ).fetchall()
        ]

    def backup(self, tag: str):
        """在线备份当前数据库；文件不存在或为空时跳过。"""
        if not self.db_path or not os.path.exists(self.db_path):
            return ""
        if os.path.getsize(self.db_path) == 0:
            return ""
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = f"{self.db_path}.pre_{tag}_{stamp}.bak"
        source_conn = sqlite3.connect(self.db_path)
        target_conn = sqlite3.connect(target)
        try:
            source_conn.backup(target_conn)
            target_conn.commit()
        finally:
            source_conn.close()
            target_conn.close()
        return target

    def apply(self, target: int, callback, make_backup: bool = True):
        """应用一个迁移；返回 (applied, backup_path)。"""
        current = self.current()
        if current >= target:
            return False, ""
        backup_path = self.backup(f"v{current}_to_v{target}") if make_backup else ""
        try:
            callback()
            self.conn.execute(
                "INSERT INTO schema_migrations (namespace, version, applied_at) VALUES (?, ?, ?)",
                (self.namespace, target, datetime.now().isoformat(timespec="seconds")),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return True, backup_path
