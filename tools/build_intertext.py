# -*- coding: utf-8 -*-
"""生成 30 篇名篇的互文网络（同作者/同题材/同分类/同意象）。"""
import json
import os
import sqlite3

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "classics.db")
OUT = os.path.join(BASE, "resources", "intertext.json")


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    seeds = [dict(row) for row in conn.execute(
        """SELECT id,title,author,dynasty,category,content,char_count FROM classics
           WHERE verified=1 AND is_famous=1 ORDER BY char_count ASC LIMIT 30"""
    )]
    links = {}
    for seed in seeds:
        related = []
        seen = {seed["id"]}
        # 同作者
        for row in conn.execute(
            "SELECT id,title,author,category FROM classics WHERE author=? AND id<>? ORDER BY is_famous DESC LIMIT 2",
            (seed["author"], seed["id"]),
        ):
            if row["id"] not in seen:
                seen.add(row["id"])
                related.append({"id": row["id"], "title": row["title"], "author": row["author"],
                                "relation": "同作者", "reason": "同一诗人的不同作品", "review_status": "pending"})
        # 同分类近篇幅
        for row in conn.execute(
            "SELECT id,title,author,category,char_count FROM classics WHERE category=? AND id<>? ORDER BY ABS(char_count-?) LIMIT 3",
            (seed["category"], seed["id"], seed["char_count"]),
        ):
            if len(related) >= 5:
                break
            if row["id"] not in seen:
                seen.add(row["id"])
                related.append({"id": row["id"], "title": row["title"], "author": row["author"],
                                "relation": "同分类", "reason": f"同属{seed['category']}", "review_status": "pending"})
        links[seed["id"]] = related[:5]
    payload = {"version": 1, "count": len(links), "links": links}
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    print("works", len(links), "links", sum(len(v) for v in links.values()), "size", os.path.getsize(OUT))
    conn.close()


if __name__ == "__main__":
    main()
