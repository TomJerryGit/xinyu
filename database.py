# -*- coding: utf-8 -*-
"""作品库与手札数据库（SQLite，WAL）。"""
import sqlite3

from utils import ensure_dir


class Database:
    def __init__(self, db_path="data/works.db", timeout=30):
        ensure_dir(db_path)
        self.conn = sqlite3.connect(db_path, check_same_thread=False, timeout=timeout)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self._create_tables()

    def _create_tables(self):
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS works (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                genre TEXT NOT NULL DEFAULT '',
                style TEXT NOT NULL DEFAULT '',
                topic TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL DEFAULT '',
                time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS journals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL DEFAULT '',
                genre TEXT NOT NULL DEFAULT '',
                topic TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL DEFAULT '',
                critique TEXT NOT NULL DEFAULT '',
                mood TEXT NOT NULL DEFAULT ''
            )
            """
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_works_time ON works(time DESC)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_works_topic ON works(topic)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_works_genre ON works(genre)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_journals_date ON journals(date)")
        self.conn.commit()

    def save(self, genre, style, topic, content):
        self.conn.execute(
            "INSERT INTO works (genre, style, topic, content) VALUES (?, ?, ?, ?)",
            (genre, style, topic, content),
        )
        self.conn.commit()

    def search(self, keyword=""):
        if keyword:
            return self.conn.execute(
                "SELECT * FROM works WHERE topic LIKE ? OR content LIKE ? ORDER BY time DESC",
                (f"%{keyword}%", f"%{keyword}%"),
            ).fetchall()
        return self.conn.execute("SELECT * FROM works ORDER BY time DESC").fetchall()

    def search_dicts(self, keyword="", limit=None):
        """返回字典列表，便于直接通过 js_api 传给前端。"""
        sql = "SELECT id, genre, style, topic, content, time FROM works"
        params = []
        if keyword:
            sql += " WHERE topic LIKE ? OR content LIKE ?"
            params.extend([f"%{keyword}%", f"%{keyword}%"])
        sql += " ORDER BY time DESC"
        if limit:
            sql += " LIMIT ?"
            params.append(int(limit))
        keys = ("id", "genre", "style", "topic", "content", "time")
        return [dict(zip(keys, row)) for row in self.conn.execute(sql, params).fetchall()]

    def count(self):
        return self.conn.execute("SELECT COUNT(*) FROM works").fetchone()[0]


    def delete(self, work_id):
        self.conn.execute("DELETE FROM works WHERE id = ?", (int(work_id),))
        self.conn.commit()

    def get_by_id(self, work_id):
        return self.conn.execute("SELECT * FROM works WHERE id = ?", (int(work_id),)).fetchone()

    def save_journal(self, date, genre, topic, content, critique="", mood=""):
        self.conn.execute(
            "INSERT INTO journals (date, genre, topic, content, critique, mood) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (date, genre, topic, content, critique, mood),
        )
        self.conn.commit()

    def get_journals(self, limit=30):
        return self.conn.execute(
            "SELECT * FROM journals ORDER BY id DESC LIMIT ?", (int(limit),)
        ).fetchall()

    def checkpoint(self):
        try:
            self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self.conn.commit()
            return True
        except Exception:
            return False

    def close(self):
        try:
            self.conn.commit()
        except Exception:
            pass
        self.conn.close()
