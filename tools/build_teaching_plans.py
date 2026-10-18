# -*- coding: utf-8 -*-
"""生成内置教学教案（离线骨架，供首次打开秒显）。

预置不是 AI 成品，逐句译文/注释仍标记待补充；它的价值是：
不联网、不花钱、立即有教学目标/重点/逐句框架/练习/作业/板书。
"""
import argparse
import json
import os
import sqlite3
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "classics.db")
OUT = os.path.join(BASE, "resources", "teaching_plans.json")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=80)
    args = parser.parse_args()
    sys.path.insert(0, BASE)
    from api import TeachingMixin

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT * FROM classics WHERE verified=1 AND char_count BETWEEN 8 AND 600
           ORDER BY is_famous DESC, char_count ASC LIMIT ?""",
        (max(1, args.limit),),
    ).fetchall()
    # 再补每个分类的代表作，避免全是唐诗
    for category in ("宋词", "诗经", "楚辞", "论语", "经部", "子部", "史部", "蒙学", "汉赋", "魏晋南北朝", "明清小品", "经典散文", "元曲"):
        extra = conn.execute(
            """SELECT * FROM classics WHERE category=? AND verified=1 AND char_count BETWEEN 8 AND 600
               ORDER BY is_famous DESC, char_count ASC LIMIT 2""",
            (category,),
        ).fetchall()
        rows.extend(extra)
    dedup = {}
    for row in rows:
        dedup[row["id"]] = dict(row)
    plans = {}
    for item in dedup.values():
        for level in ("beginner", "standard", "advanced"):
            plan = TeachingMixin._offline_teaching_plan(item, level)
            plan["_source"] = "prebuilt"
            plans[f"{item['id']}|{level}"] = plan
    payload = {"version": 1, "count": len(plans), "plans": plans}
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    print("works", len(dedup), "plans", len(plans), "size_mb", round(os.path.getsize(OUT) / 1024 / 1024, 2))
    conn.close()


if __name__ == "__main__":
    main()
