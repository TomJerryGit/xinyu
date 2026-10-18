# -*- coding: utf-8 -*-
"""批量预热离线教案（不调用 AI）。

用法：
    python tools/warm_teaching_plans.py --limit 0 --levels standard
    python tools/warm_teaching_plans.py --limit 200 --levels beginner,standard,advanced

当前应用已支持“任意一篇首次打开时按需生成离线教案”（约 27ms），
本工具用于完全离线部署/老机器提前写入 SQLite。
"""
import argparse
import os
import sqlite3
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "classics.db")
sys.path.insert(0, BASE)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="0 = 全部")
    parser.add_argument("--levels", default="standard")
    args = parser.parse_args()
    from api import TeachingMixin

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    query = "SELECT * FROM classics WHERE verified=1 AND length(trim(content))>=8"
    params = []
    if args.limit > 0:
        query += " LIMIT ?"
        params.append(args.limit)
    rows = [dict(row) for row in conn.execute(query, params)]
    levels = [item.strip() for item in args.levels.split(",") if item.strip()]
    started = time.perf_counter()
    saved = 0
    for index, item in enumerate(rows, 1):
        for level in levels:
            plan = TeachingMixin._offline_teaching_plan(item, level)
            conn.execute(
                """INSERT OR REPLACE INTO teaching_plans (classic_id, level, data, source, updated_at)
                   VALUES (?, ?, ?, 'offline-prebuilt', CURRENT_TIMESTAMP)""",
                (item["id"], level, __import__("json").dumps(plan, ensure_ascii=False)),
            )
            saved += 1
        if index % 500 == 0:
            conn.commit()
            print("progress", index, "plans", saved)
    conn.commit()
    print("works", len(rows), "plans", saved, "seconds", round(time.perf_counter() - started, 2))
    conn.close()


if __name__ == "__main__":
    main()
