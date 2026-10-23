# -*- coding: utf-8 -*-
"""古典文化数据库（SQLite）。

涵盖经史子集、诗词曲赋、蒙学经典等，提供检索、统计、收藏、
笔记、阅读历史与数据质量维护。
"""
import hashlib
import json
import re
import sqlite3

from migrations import Migrator
from utils import ensure_dir


class ClassicsDatabase:
    def __init__(self, db_path="data/classics.db", timeout=30):
        ensure_dir(db_path)
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False, timeout=timeout)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()
        try:
            columns = {row[1] for row in self.conn.execute("PRAGMA table_info(question_bank)")}
            if "cognitive" not in columns:
                self.conn.execute("ALTER TABLE question_bank ADD COLUMN cognitive TEXT DEFAULT '识记'")
                self.conn.commit()
            if "rubric" not in columns:
                self.conn.execute("ALTER TABLE question_bank ADD COLUMN rubric TEXT DEFAULT '[]'")
                self.conn.commit()
        except sqlite3.Error:
            pass
        self._migrator = Migrator(self.conn, db_path, "classics")
        self._migrator.apply(1, self._migration_v1, make_backup=self._has_data())
        self._create_indexes()

    def _has_data(self) -> bool:
        try:
            return self.conn.execute("SELECT COUNT(*) FROM classics").fetchone()[0] > 0
        except sqlite3.Error:
            return False

    def schema_version(self) -> int:
        return self._migrator.current()

    # ---------- 结构 ----------
    def _create_tables(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS classics (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                author TEXT NOT NULL DEFAULT '佚名',
                dynasty TEXT DEFAULT '未知',
                category TEXT NOT NULL DEFAULT '未分类',
                subcategory TEXT DEFAULT '',
                content TEXT NOT NULL DEFAULT '',
                translation TEXT DEFAULT '',
                annotation TEXT DEFAULT '',
                tags TEXT DEFAULT '',
                source TEXT DEFAULT '',
                char_count INTEGER DEFAULT 0,
                is_famous INTEGER DEFAULT 0,
                difficulty_level INTEGER DEFAULT 1,
                verified INTEGER DEFAULT 0,
                teaching_data TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS teaching_plans (
                classic_id TEXT NOT NULL,
                level TEXT NOT NULL,
                data TEXT NOT NULL,
                source TEXT DEFAULT '',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (classic_id, level)
            );
            CREATE TABLE IF NOT EXISTS ai_review_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                classic_id TEXT DEFAULT '',
                payload TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                reviewer TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reviewed_at TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_ai_review_status ON ai_review_queue(status);
            CREATE TABLE IF NOT EXISTS teaching_plan_versions (                id INTEGER PRIMARY KEY AUTOINCREMENT,
                classic_id TEXT NOT NULL,
                level TEXT NOT NULL,
                profile TEXT DEFAULT '',
                data TEXT NOT NULL,
                source TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_teaching_versions ON teaching_plan_versions(classic_id, level, profile);
            CREATE TABLE IF NOT EXISTS question_bank (
                id TEXT PRIMARY KEY,
                classic_id TEXT NOT NULL,
                category TEXT DEFAULT '',
                dynasty TEXT DEFAULT '',
                difficulty INTEGER DEFAULT 1,
                type TEXT DEFAULT '选择',
                question TEXT NOT NULL,
                options TEXT DEFAULT '[]',
                answer TEXT DEFAULT '',
                explanation TEXT DEFAULT '',
                cognitive TEXT DEFAULT '识记',
                rubric TEXT DEFAULT '[]',
                source TEXT DEFAULT 'rule',
                verified INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_question_bank_cat ON question_bank(category, difficulty);
            CREATE INDEX IF NOT EXISTS idx_question_bank_type ON question_bank(type);
            CREATE TABLE IF NOT EXISTS reading_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                classic_id TEXT NOT NULL,
                read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                read_duration INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS user_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                classic_id TEXT NOT NULL,
                note_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                classic_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS study_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                classic_ids TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS quiz_wrong (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT DEFAULT '',
                your_answer TEXT DEFAULT '',
                correct_answer TEXT DEFAULT '',
                explanation TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self.conn.commit()

    def _migration_v1(self):
        """v1：为旧数据库补齐新增列。

        注意：SQLite 的 ``ALTER TABLE ADD COLUMN`` 不允许 CURRENT_TIMESTAMP
        这类非常量默认值，因此时间列先以无默认值方式加入，再回填。
        """
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(classics)")}
        additions = {
            "verified": "INTEGER DEFAULT 0",
            "created_at": "TIMESTAMP",
            "updated_at": "TIMESTAMP",
            "teaching_data": "TEXT DEFAULT ''",
            "source": "TEXT DEFAULT ''",
            "translation_status": "TEXT DEFAULT ''",
            "annotation_status": "TEXT DEFAULT ''",
            "reviewed_by": "TEXT DEFAULT ''",
            "reviewed_at": "TIMESTAMP",
        }
        changed = False
        for name, definition in additions.items():
            if name not in columns:
                self.conn.execute(f"ALTER TABLE classics ADD COLUMN {name} {definition}")
                changed = True
        if changed:
            self.conn.execute(
                "UPDATE classics SET created_at = COALESCE(created_at, CURRENT_TIMESTAMP), "
                "updated_at = COALESCE(updated_at, CURRENT_TIMESTAMP)"
            )
            self.conn.commit()

    def _create_indexes(self):
        self.conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_classics_category ON classics(category);
            CREATE INDEX IF NOT EXISTS idx_classics_dynasty ON classics(dynasty);
            CREATE INDEX IF NOT EXISTS idx_classics_author ON classics(author);
            CREATE INDEX IF NOT EXISTS idx_classics_difficulty ON classics(difficulty_level);
            CREATE INDEX IF NOT EXISTS idx_classics_title ON classics(title);
            CREATE INDEX IF NOT EXISTS idx_classics_verified ON classics(verified);
            CREATE INDEX IF NOT EXISTS idx_classics_cat_dyn ON classics(category, dynasty);
            CREATE INDEX IF NOT EXISTS idx_classics_author_dyn ON classics(author, dynasty);
            """
        )
        self.conn.commit()

    # ---------- 写入 ----------
    @staticmethod
    def _fallback_id(item) -> str:
        seed = f"{item.get('title','')}|{item.get('author','')}|{item.get('content','')[:40]}"
        digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
        return f"classic_{digest}"

    def insert(self, item, commit=True):
        try:
            tags = item.get("tags", "")
            if isinstance(tags, (list, tuple)):
                tags = ",".join(str(tag) for tag in tags)
            self.conn.execute(
                """
                INSERT OR REPLACE INTO classics
                (id, title, author, dynasty, category, subcategory, content, translation,
                 annotation, tags, source, char_count, is_famous, difficulty_level, verified)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.get("id") or self._fallback_id(item),
                    item.get("title", "未知"),
                    item.get("author", "佚名") or "佚名",
                    item.get("dynasty", "未知") or "未知",
                    item.get("category", "未分类") or "未分类",
                    item.get("subcategory", ""),
                    item.get("content", ""),
                    item.get("translation", ""),
                    item.get("annotation", ""),
                    tags,
                    item.get("source", ""),
                    len(item.get("content", "")),
                    1 if item.get("is_famous") else 0,
                    int(item.get("difficulty_level", 1) or 1),
                    int(item.get("verified", 0) or 0),
                ),
            )
            if commit:
                self.conn.commit()
            return True
        except Exception as exc:  # noqa: BLE001 - 单条失败不应中断批量导入
            print(f"插入失败: {exc}")
            return False

    def batch_insert(self, items):
        count = 0
        for item in items:
            if self.insert(item):
                count += 1
        return count

    def delete_many(self, ids):
        ids = list(ids)
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        cursor = self.conn.execute(f"DELETE FROM classics WHERE id IN ({placeholders})", ids)
        self.conn.commit()
        return cursor.rowcount

    # ---------- 查询 ----------
    @staticmethod
    def _filters(keyword="", category="", dynasty="", author="", difficulty=None, verified_only=False):
        conditions = []
        params = []
        if keyword:
            conditions.append("(title LIKE ? OR author LIKE ? OR content LIKE ? OR tags LIKE ?)")
            kw = f"%{keyword}%"
            params.extend([kw, kw, kw, kw])
        if category:
            conditions.append("category = ?")
            params.append(category)
        if dynasty:
            conditions.append("dynasty = ?")
            params.append(dynasty)
        if author:
            conditions.append("author LIKE ?")
            params.append(f"%{author}%")
        if difficulty is not None:
            conditions.append("difficulty_level = ?")
            params.append(difficulty)
        if verified_only:
            conditions.append("verified = 1")
        return (" AND ".join(conditions) if conditions else "1=1"), params

    def search(self, keyword="", category="", dynasty="", author="", difficulty=None, limit=50, offset=0, verified_only=False):
        where_clause, params = self._filters(keyword, category, dynasty, author, difficulty, verified_only)
        query = (
            f"SELECT * FROM classics WHERE {where_clause} "
            "ORDER BY is_famous DESC, char_count DESC LIMIT ? OFFSET ?"
        )
        params.extend([int(limit), int(offset)])
        return [dict(row) for row in self.conn.execute(query, params).fetchall()]

    def count_search(self, keyword="", category="", dynasty="", author="", difficulty=None, verified_only=False):
        where_clause, params = self._filters(keyword, category, dynasty, author, difficulty, verified_only)
        return self.conn.execute(
            f"SELECT COUNT(*) FROM classics WHERE {where_clause}", params
        ).fetchone()[0]

    def get_notes_count(self, classic_id=None):
        if classic_id:
            return self.conn.execute(
                "SELECT COUNT(*) FROM user_notes WHERE classic_id = ?", (classic_id,)
            ).fetchone()[0]
        return self.conn.execute("SELECT COUNT(*) FROM user_notes").fetchone()[0]

    def get_favorites_count(self):
        return self.conn.execute("SELECT COUNT(*) FROM favorites").fetchone()[0]

    def optimize(self):
        """定期调用，让查询规划器保持最新统计信息。"""
        try:
            self.conn.execute("PRAGMA optimize")
            self.conn.commit()
            return True
        except Exception:
            return False


    def get_by_id(self, classic_id):
        row = self.conn.execute("SELECT * FROM classics WHERE id = ?", (classic_id,)).fetchone()
        return dict(row) if row else None

    def get_categories(self):
        return [
            dict(row)
            for row in self.conn.execute(
                "SELECT category, COUNT(*) as count FROM classics "
                "GROUP BY category ORDER BY count DESC"
            ).fetchall()
        ]

    def get_subcategories(self, category):
        return [
            dict(row)
            for row in self.conn.execute(
                "SELECT subcategory, COUNT(*) as count FROM classics WHERE category = ? "
                "GROUP BY subcategory ORDER BY count DESC",
                (category,),
            ).fetchall()
        ]

    def get_dynasties(self):
        return [
            dict(row)
            for row in self.conn.execute(
                "SELECT dynasty, COUNT(*) as count FROM classics GROUP BY dynasty ORDER BY count DESC"
            ).fetchall()
        ]

    def get_authors(self):
        return [
            dict(row)
            for row in self.conn.execute(
                "SELECT author, COUNT(*) as count FROM classics "
                "GROUP BY author ORDER BY count DESC LIMIT 200"
            ).fetchall()
        ]

    def get_random(self, category=""):
        if category:
            row = self.conn.execute(
                "SELECT * FROM classics WHERE category = ? ORDER BY RANDOM() LIMIT 1", (category,)
            ).fetchone()
        else:
            row = self.conn.execute("SELECT * FROM classics ORDER BY RANDOM() LIMIT 1").fetchone()
        return dict(row) if row else None

    def get_total_count(self):
        return self.conn.execute("SELECT COUNT(*) FROM classics").fetchone()[0]

    def get_stats(self):
        total = self.get_total_count()
        total_chars = self.conn.execute("SELECT SUM(char_count) FROM classics").fetchone()[0] or 0
        return {
            "total": total,
            "total_chars": total_chars,
            "categories": self.get_categories(),
            "dynasties": self.get_dynasties(),
            "authors_top": self.get_authors()[:20],
        }

    # ---------- 阅读/笔记/收藏 ----------
    def record_read(self, classic_id, duration=0):
        self.conn.execute(
            "INSERT INTO reading_history (classic_id, read_duration) VALUES (?, ?)",
            (classic_id, int(duration or 0)),
        )
        self.conn.commit()

    def get_reading_history(self, limit=50):
        return [
            dict(row)
            for row in self.conn.execute(
                """SELECT r.*, c.title, c.author, c.dynasty, c.category
                   FROM reading_history r JOIN classics c ON r.classic_id = c.id
                   ORDER BY r.read_at DESC LIMIT ?""",
                (int(limit),),
            ).fetchall()
        ]

    def add_note(self, classic_id, note_text):
        self.conn.execute(
            "INSERT INTO user_notes (classic_id, note_text) VALUES (?, ?)", (classic_id, note_text)
        )
        self.conn.commit()

    def get_notes(self, classic_id):
        return [
            dict(row)
            for row in self.conn.execute(
                "SELECT * FROM user_notes WHERE classic_id = ? ORDER BY created_at DESC",
                (classic_id,),
            ).fetchall()
        ]

    def delete_note(self, note_id):
        self.conn.execute("DELETE FROM user_notes WHERE id = ?", (int(note_id),))
        self.conn.commit()

    def add_favorite(self, classic_id):
        self.conn.execute("INSERT OR IGNORE INTO favorites (classic_id) VALUES (?)", (classic_id,))
        self.conn.commit()

    def remove_favorite(self, classic_id):
        self.conn.execute("DELETE FROM favorites WHERE classic_id = ?", (classic_id,))
        self.conn.commit()

    def get_favorites(self, limit=50):
        return [
            dict(row)
            for row in self.conn.execute(
                """SELECT f.*, c.title, c.author, c.dynasty, c.category
                   FROM favorites f JOIN classics c ON f.classic_id = c.id
                   ORDER BY f.created_at DESC LIMIT ?""",
                (int(limit),),
            ).fetchall()
        ]

    def is_favorite(self, classic_id):
        row = self.conn.execute(
            "SELECT COUNT(*) FROM favorites WHERE classic_id = ?", (classic_id,)
        ).fetchone()
        return row[0] > 0

    def create_study_plan(self, name, description, classic_ids):
        self.conn.execute(
            "INSERT INTO study_plans (name, description, classic_ids) VALUES (?, ?, ?)",
            (name, description, ",".join(classic_ids)),
        )
        self.conn.commit()

    def get_study_plans(self):
        return [
            dict(row)
            for row in self.conn.execute(
                "SELECT * FROM study_plans ORDER BY created_at DESC"
            ).fetchall()
        ]

    def get_reading_streak(self):
        rows = self.conn.execute(
            "SELECT DISTINCT date(read_at) as read_date FROM reading_history "
            "ORDER BY read_date DESC LIMIT 30"
        ).fetchall()
        if not rows:
            return 0
        from datetime import datetime

        streak = 1
        for index in range(1, len(rows)):
            try:
                previous = datetime.strptime(str(rows[index - 1]["read_date"])[:10], "%Y-%m-%d")
                current = datetime.strptime(str(rows[index]["read_date"])[:10], "%Y-%m-%d")
            except (ValueError, TypeError):
                break
            if (previous - current).days == 1:
                streak += 1
            else:
                break
        return streak

    def get_teaching_plan(self, classic_id, level="standard"):
        row = self.conn.execute(
            "SELECT data, source, updated_at FROM teaching_plans WHERE classic_id=? AND level=?",
            (classic_id, level),
        ).fetchone()
        if not row:
            return None
        try:
            data = json.loads(row["data"])
            data["_source"] = row["source"] or "cache"
            data["_updated_at"] = row["updated_at"]
            return data
        except (TypeError, ValueError):
            return None

    def save_teaching_plan(self, classic_id, level, data, source="ai"):
        self.conn.execute(
            """INSERT OR REPLACE INTO teaching_plans (classic_id, level, data, source, updated_at)
               VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (classic_id, level, json.dumps(data, ensure_ascii=False), source),
        )
        self.conn.commit()

    def save_teaching_version(self, classic_id, level, profile, data, source="teacher"):
        self.conn.execute(
            """INSERT INTO teaching_plan_versions (classic_id, level, profile, data, source)
               VALUES (?, ?, ?, ?, ?)""",
            (classic_id, level, profile or "", json.dumps(data, ensure_ascii=False), source),
        )
        self.conn.commit()

    def list_teaching_versions(self, classic_id, level, profile=""):
        rows = self.conn.execute(
            """SELECT id, source, created_at FROM teaching_plan_versions
               WHERE classic_id=? AND level=? AND profile=? ORDER BY id DESC LIMIT 20""",
            (classic_id, level, profile or ""),
        ).fetchall()
        return [dict(row) for row in rows]

    def enqueue_ai_review(self, kind, classic_id, payload):
        cursor = self.conn.execute(
            "INSERT INTO ai_review_queue (kind, classic_id, payload) VALUES (?, ?, ?)",
            (kind, classic_id or "", json.dumps(payload, ensure_ascii=False)),
        )
        self.conn.commit()
        return cursor.lastrowid

    def list_ai_review(self, status="pending", limit=50):
        rows = self.conn.execute(
            """SELECT id,kind,classic_id,payload,status,reviewer,notes,created_at
               FROM ai_review_queue WHERE status=? ORDER BY id DESC LIMIT ?""",
            (status, int(limit)),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["payload"] = json.loads(item["payload"])
            except (TypeError, ValueError):
                item["payload"] = {}
            result.append(item)
        return result

    def review_ai_item(self, review_id, decision, reviewer="", notes=""):
        if decision not in ("approved", "rejected"):
            return False
        self.conn.execute(
            """UPDATE ai_review_queue SET status=?, reviewer=?, notes=?, reviewed_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (decision, reviewer or "", notes or "", int(review_id)),
        )
        self.conn.commit()
        return True

    def get_ai_review(self, review_id):
        row = self.conn.execute(
            "SELECT id,kind,classic_id,payload,status,reviewer,notes,created_at FROM ai_review_queue WHERE id=?",
            (int(review_id),),
        ).fetchone()
        if not row:
            return None
        item = dict(row)
        try:
            item["payload"] = json.loads(item["payload"])
        except (TypeError, ValueError):
            item["payload"] = {}
        return item

    def update_verified(self, classic_id, verified=1):
        self.conn.execute(
            "UPDATE classics SET verified=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (int(verified), classic_id),
        )
        self.conn.commit()

    # ---------- 数据质量 ----------
    def improve_data_quality(self):
        """只做"可证明为真"的补全：为缺失标签的作品提取词频标签。

        不再用模板伪造译文或注释——那会让质量评分虚高，也会误导用户。
        """
        cursor = self.conn.execute(
            "SELECT id, content, tags FROM classics WHERE content IS NOT NULL AND content != ''"
        )
        updated = 0
        for row in cursor.fetchall():
            item = dict(row)
            if item.get("tags"):
                continue
            tags = self._extract_tags_from_content(item.get("content", ""))
            if tags:
                self.conn.execute("UPDATE classics SET tags=? WHERE id=?", (tags, item["id"]))
                updated += 1
        self.conn.commit()
        return updated

    @staticmethod
    def _extract_tags_from_content(content):
        """从内容中提取高频二字词作为标签（仅作检索辅助）。"""
        if not content:
            return ""
        words = re.findall(r"[\u4e00-\u9fff]{2,4}", content)
        if not words:
            return ""
        freq = {}
        for word in words:
            freq[word] = freq.get(word, 0) + 1
        top = sorted(freq.items(), key=lambda pair: pair[1], reverse=True)[:5]
        return ",".join(word for word, _ in top)

    def checkpoint(self):
        """把 WAL 内容合并回主库，保证备份得到一致快照。"""
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
