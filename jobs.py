# -*- coding: utf-8 -*-
"""可取消、可恢复的本地作业系统。

长任务（教学备课、智能扩充、预览导入）通过 ``JobManager`` 在后台线程执行，
状态写入 SQLite；前端轮询进度并可取消。应用重启后，运行中的任务标记为
``interrupted``，待处理任务会继续执行。
"""
import json
import os
import sqlite3
import threading
import time
import traceback
import uuid
from datetime import datetime

from logger import log
from metrics import record as record_metric


class JobCancelled(Exception):
    pass


class JobManager:
    def __init__(self, db_path, handlers, max_workers=2):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.handlers = dict(handlers or {})
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_db()
        self._threads = [
            threading.Thread(target=self._worker, daemon=True, name=f"xinyu-job-{index}")
            for index in range(max(1, int(max_workers)))
        ]
        for thread in self._threads:
            thread.start()

    def _init_db(self):
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'pending',
                    progress REAL NOT NULL DEFAULT 0,
                    message TEXT DEFAULT '',
                    result TEXT DEFAULT '',
                    error TEXT DEFAULT '',
                    cancel INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, created_at);
                """
            )
            self._conn.execute(
                "UPDATE jobs SET status='interrupted', error=?, updated_at=? "
                "WHERE status='running'",
                ("应用退出时任务被中断", datetime.now().isoformat(timespec="seconds")),
            )
            columns = {row[1] for row in self._conn.execute("PRAGMA table_info(jobs)").fetchall()}
            if "checkpoint" not in columns:
                self._conn.execute("ALTER TABLE jobs ADD COLUMN checkpoint TEXT DEFAULT ''")
            self._conn.commit()

    # ---------- 提交/查询 ----------
    def submit(self, kind: str, payload: dict) -> str:
        if kind not in self.handlers:
            raise ValueError(f"不支持的任务类型: {kind}")
        job_id = uuid.uuid4().hex
        now = datetime.now().isoformat(timespec="seconds")
        with self._lock:
            self._conn.execute(
                "INSERT INTO jobs (id, kind, payload, status, created_at, updated_at) "
                "VALUES (?, ?, ?, 'pending', ?, ?)",
                (job_id, kind, json.dumps(payload or {}, ensure_ascii=False), now, now),
            )
            self._conn.commit()
        return job_id

    def get(self, job_id: str):
        with self._lock:
            row = self._conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row(row, include_result=True) if row else None

    def list(self, limit: int = 20):
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",
                (max(1, min(100, int(limit or 20))),),
            ).fetchall()
        return [self._row(row, include_result=False) for row in rows]

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            row = self._conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not row:
                return False
            status = row["status"]
            if status == "pending":
                self._conn.execute(
                    "UPDATE jobs SET status='cancelled', message=?, updated_at=? WHERE id=?",
                    ("已取消", self._now(), job_id),
                )
            elif status == "running":
                self._conn.execute(
                    "UPDATE jobs SET cancel=1, message=?, updated_at=? WHERE id=?",
                    ("正在取消…", self._now(), job_id),
                )
            else:
                return False
            self._conn.commit()
        return True

    def retry(self, job_id: str) -> bool:
        """把失败/中断/取消的作业重新排队。"""
        with self._lock:
            row = self._conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not row or row["status"] not in ("failed", "interrupted", "cancelled"):
                return False
            self._conn.execute(
                "UPDATE jobs SET status='pending', progress=0, message=?, error='', "
                "result='', cancel=0, updated_at=? WHERE id=?",
                ("重试排队中", self._now(), job_id),
            )
            self._conn.commit()
        return True

    def is_cancelled(self, job_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT cancel FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return bool(row and row["cancel"])

    def save_checkpoint(self, job_id: str, data) -> bool:
        """保存任务级快照；JSON 序列化失败时返回 False。"""
        try:
            encoded = json.dumps(data, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return False
        with self._lock:
            self._conn.execute(
                "UPDATE jobs SET checkpoint=?, updated_at=? WHERE id=?",
                (encoded, self._now(), job_id),
            )
            self._conn.commit()
        return True

    def get_checkpoint(self, job_id: str):
        with self._lock:
            row = self._conn.execute(
                "SELECT checkpoint FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
        if not row or not row["checkpoint"]:
            return {}
        try:
            data = json.loads(row["checkpoint"])
            return data if isinstance(data, dict) else {}
        except ValueError:
            return {}

    # ---------- 执行 ----------
    def _worker(self):
        while not self._stop.is_set():
            job = self._claim()
            if not job:
                self._stop.wait(0.3)
                continue
            self._run(job)

    def _claim(self):
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM jobs WHERE status='pending' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if not row:
                return None
            self._conn.execute(
                "UPDATE jobs SET status='running', progress=1, message=?, updated_at=? WHERE id=?",
                ("开始执行", self._now(), row["id"]),
            )
            self._conn.commit()
            return dict(row)

    def _run(self, job):
        job_id = job["id"]
        started = time.time()
        handler = self.handlers.get(job["kind"])

        def progress(value, message=""):
            if self.is_cancelled(job_id):
                raise JobCancelled()
            self._update(job_id, progress=max(0, min(100, float(value))), message=message)

        def cancelled():
            return self.is_cancelled(job_id)

        def checkpoint(data):
            return self.save_checkpoint(job_id, data)

        def resume():
            return self.get_checkpoint(job_id)

        progress.checkpoint = checkpoint
        progress.get_checkpoint = resume

        try:
            if not handler:
                raise ValueError(f"任务处理器不存在: {job['kind']}")
            payload = json.loads(job.get("payload") or "{}")
            result = handler(payload, progress, cancelled)
            if cancelled():
                raise JobCancelled()
            self._finish(job_id, "done", result=result, progress=100, message="完成")
            status = "done"
        except JobCancelled:
            self._finish(job_id, "cancelled", message="已取消")
            status = "cancelled"
        except Exception as exc:  # noqa: BLE001 - 作业边界需要记录失败
            # 处理器可能以普通异常放弃执行；只要用户已请求取消，就按取消处理
            if cancelled():
                self._finish(job_id, "cancelled", message="已取消")
                status = "cancelled"
            else:
                log("error", f"作业 {job['kind']} 失败: {str(exc)[:240]}")
                self._finish(
                    job_id,
                    "failed",
                    error=f"{exc}\n{traceback.format_exc()[-1500:]}",
                    message="执行失败",
                )
                status = "failed"
        finally:
            record_metric(
                "job",
                kind=job["kind"],
                status=status,
                duration_ms=round((time.time() - started) * 1000, 1),
                job_id=job_id,
            )

    def _finish(self, job_id, status, result=None, error="", progress=None, message=""):
        values = []
        sql = "UPDATE jobs SET status=?, error=?, updated_at=?"
        values.extend([status, error or "", self._now()])
        if result is not None:
            sql += ", result=?"
            values.append(json.dumps(result, ensure_ascii=False, default=str))
        if progress is not None:
            sql += ", progress=?"
            values.append(float(progress))
        if message:
            sql += ", message=?"
            values.append(message)
        sql += " WHERE id=?"
        values.append(job_id)
        with self._lock:
            self._conn.execute(sql, values)
            self._conn.commit()

    def _update(self, job_id, progress=None, message=None):
        with self._lock:
            if progress is not None:
                self._conn.execute(
                    "UPDATE jobs SET progress=?, message=?, updated_at=? WHERE id=?",
                    (float(progress), message or "", self._now(), job_id),
                )
            else:
                self._conn.execute(
                    "UPDATE jobs SET message=?, updated_at=? WHERE id=?",
                    (message or "", self._now(), job_id),
                )
            self._conn.commit()

    @staticmethod
    def _now():
        return datetime.now().isoformat(timespec="seconds")

    @staticmethod
    def _row(row, include_result=True):
        keys = row.keys()
        item = {
            "id": row["id"],
            "kind": row["kind"],
            "status": row["status"],
            "progress": round(float(row["progress"] or 0), 1),
            "message": row["message"] or "",
            "error": row["error"] or "",
            "cancel_requested": bool(row["cancel"]),
            "has_checkpoint": bool(row["checkpoint"]) if "checkpoint" in keys else False,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        if include_result:
            try:
                item["payload"] = json.loads(row["payload"] or "{}")
            except ValueError:
                item["payload"] = {}
            try:
                item["result"] = json.loads(row["result"]) if row["result"] else None
            except ValueError:
                item["result"] = row["result"]
        return item

    def shutdown(self):
        self._stop.set()
        for thread in getattr(self, "_threads", []):
            if thread.is_alive():
                thread.join(timeout=2)
        try:
            self._conn.close()
        except Exception:
            pass
