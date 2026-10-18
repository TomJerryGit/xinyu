# -*- coding: utf-8 -*-
"""本地运行指标。

追加写入 ``data/metrics.jsonl``，超过 2 MB 自动轮转。默认只在本地，
不联网；用于设置里的「运行指标」与诊断包。
"""
import json
import os
import threading
import time
from collections import Counter, defaultdict

from utils import app_path

_LOCK = threading.Lock()
_MAX_BYTES = 2 * 1024 * 1024
_MAX_LINES = 5000


def _path() -> str:
    return app_path("data", "metrics.jsonl")


def record(event: str, **fields):
    """记录一条指标；失败静默，绝不影响主流程。"""
    entry = {"ts": round(time.time(), 3), "event": str(event)}
    entry.update(fields)
    path = _path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with _LOCK:
            if os.path.exists(path) and os.path.getsize(path) > _MAX_BYTES:
                backup = path + ".1"
                try:
                    if os.path.exists(backup):
                        os.remove(backup)
                    os.replace(path, backup)
                except OSError:
                    pass
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        return


def recent(limit: int = _MAX_LINES):
    path = _path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()[-limit:]
    except OSError:
        return []
    rows = []
    for line in lines:
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def _p95(values):
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(len(ordered) * 0.95)) - 1)
    return round(ordered[max(0, index)], 1)


def summary(days: int = 7):
    cutoff = time.time() - days * 86400
    rows = [row for row in recent() if row.get("ts", 0) >= cutoff]
    startups = [row.get("total_ms", 0) for row in rows if row.get("event") == "startup"]
    ai_rows = [row for row in rows if row.get("event") == "ai_call"]
    ai_success = [row for row in ai_rows if row.get("success")]
    latencies = [row.get("latency_ms", 0) for row in ai_rows if row.get("latency_ms")]
    costs = sum(float(row.get("cost") or 0) for row in ai_rows)
    crashes = [row for row in rows if row.get("event") == "crash"]
    crash_rate = round(len(crashes) / len(startups) * 100, 2) if startups else 0.0
    jobs = [row for row in rows if row.get("event") == "job"]
    job_status = Counter(row.get("status", "unknown") for row in jobs)
    task_counts = Counter(row.get("task", "?") for row in ai_rows)
    per_day = defaultdict(lambda: {"calls": 0, "tokens": 0, "cost": 0.0})
    for row in ai_rows:
        day = time.strftime("%Y-%m-%d", time.localtime(row.get("ts", 0)))
        per_day[day]["calls"] += 1
        per_day[day]["tokens"] += int(row.get("tokens") or 0)
        per_day[day]["cost"] += float(row.get("cost") or 0)
    return {
        "days": days,
        "startups": {
            "count": len(startups),
            "last_ms": startups[-1] if startups else 0,
            "p95_ms": _p95(startups),
        },
        "ai": {
            "calls": len(ai_rows),
            "success": len(ai_success),
            "success_rate": round(len(ai_success) / len(ai_rows) * 100, 1) if ai_rows else 0,
            "p95_latency_ms": _p95(latencies),
            "tokens": sum(int(row.get("tokens") or 0) for row in ai_rows),
            "cost": round(costs, 6),
            "tasks": dict(task_counts.most_common(10)),
        },
        "crashes": len(crashes),
        "crash_rate": crash_rate,
        "jobs": {"count": len(jobs), "status": dict(job_status)},
        "daily": [
            {"date": day, **values}
            for day, values in sorted(per_day.items(), reverse=True)[:days]
        ],
    }


def startup_history(limit: int = 10):
    rows = [row for row in recent(2000) if row.get("event") == "startup"]
    return rows[-limit:][::-1]
