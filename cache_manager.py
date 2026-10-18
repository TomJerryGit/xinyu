# -*- coding: utf-8 -*-
"""两级缓存：内存 LRU + SQLite 文件缓存。

写入时会记录真实过期时间，``get`` 以数据库中的 ``expire_at`` 为准，
因此调用方设置的 10 分钟、30 分钟 TTL 都会生效。
"""
import hashlib
import json
import os
import sqlite3
import threading
import time
from collections import OrderedDict

from logger import log
from utils import app_path

DEFAULT_TTL = 24 * 3600


class LRUCache:
    def __init__(self, max_size=200):
        self.cache = OrderedDict()
        self.max_size = max_size
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
            return None

    def set(self, key, value):
        with self._lock:
            if key in self.cache:
                self.cache.move_to_end(key)
            self.cache[key] = value
            while len(self.cache) > self.max_size:
                self.cache.popitem(last=False)

    def clear(self):
        with self._lock:
            self.cache.clear()


class FileCache:
    def __init__(self, cache_dir=None):
        self.cache_dir = cache_dir or os.path.join(app_path("data"), "cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.db_path = os.path.join(self.cache_dir, "cache.db")
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self._init_db()

    def _init_db(self):
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                expire_at REAL NOT NULL
            )
            """
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_expire ON cache(expire_at)")
        self.conn.commit()

    @staticmethod
    def _key_to_hash(key: str) -> str:
        return hashlib.sha256(str(key).encode("utf-8")).hexdigest()

    def get(self, key, ttl=None):
        try:
            hashed_key = self._key_to_hash(key)
            with self._lock:
                row = self.conn.execute(
                    "SELECT value, expire_at FROM cache WHERE key = ?", (hashed_key,)
                ).fetchone()
            if row is None:
                return None
            value, expire_at = row
            if time.time() > expire_at:
                self.delete(key)
                return None
            return json.loads(value)
        except Exception as exc:  # noqa: BLE001 - 缓存失败不应影响主流程
            log("warning", f"缓存读取失败: {str(exc)[:100]}")
            return None

    def set(self, key, value, ttl=DEFAULT_TTL):
        try:
            hashed_key = self._key_to_hash(key)
            expire_at = time.time() + max(1, int(ttl or DEFAULT_TTL))
            data = json.dumps(value, ensure_ascii=False)
            with self._lock:
                self.conn.execute(
                    "INSERT OR REPLACE INTO cache (key, value, expire_at) VALUES (?, ?, ?)",
                    (hashed_key, data, expire_at),
                )
                self.conn.commit()
        except Exception as exc:  # noqa: BLE001
            log("warning", f"缓存写入失败: {str(exc)[:100]}")

    def delete(self, key):
        try:
            hashed_key = self._key_to_hash(key)
            with self._lock:
                self.conn.execute("DELETE FROM cache WHERE key = ?", (hashed_key,))
                self.conn.commit()
        except Exception as exc:  # noqa: BLE001
            log("warning", f"缓存删除失败: {str(exc)[:100]}")

    def clear_expired(self, ttl=None):
        try:
            with self._lock:
                cursor = self.conn.execute("DELETE FROM cache WHERE expire_at < ?", (time.time(),))
                self.conn.commit()
                return cursor.rowcount
        except Exception as exc:  # noqa: BLE001
            log("warning", f"清理过期缓存失败: {str(exc)[:100]}")
            return 0

    def clear_all(self):
        try:
            with self._lock:
                self.conn.execute("DELETE FROM cache")
                self.conn.commit()
        except Exception as exc:  # noqa: BLE001
            log("warning", f"清空缓存失败: {str(exc)[:100]}")

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass


class CacheManager:
    def __init__(self):
        self.memory = LRUCache(max_size=200)
        self.file = FileCache()
        log("info", "缓存管理器初始化完成")

    def get(self, key, ttl=None):
        """优先读内存，未命中再读文件缓存。"""
        value = self.memory.get(key)
        if value is not None:
            return value
        value = self.file.get(key)
        if value is not None:
            self.memory.set(key, value)
        return value

    def set(self, key, value, ttl=DEFAULT_TTL):
        """同时写内存与文件缓存，``ttl`` 单位秒。"""
        self.memory.set(key, value)
        self.file.set(key, value, ttl=ttl)

    def clear(self):
        self.memory.clear()
        self.file.clear_all()

    def close(self):
        self.file.close()
