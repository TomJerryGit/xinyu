# -*- coding: utf-8 -*-
"""导出 30 篇互文关系人工校勘表（当前是机器关系，status=pending）。"""
import csv
import json
import os
import sqlite3

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "classics.db")
SRC = os.path.join(BASE, "resources", "intertext.json")
OUT = os.path.join(BASE, "data", "reviews", "intertext_30_review.csv")


def main():
    payload = json.load(open(SRC, encoding="utf-8"))
    links = payload.get("links", {})
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    titles = {r["id"]: r["title"] for r in conn.execute("SELECT id,title FROM classics")}
    conn.close()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    count = 0
    with open(OUT, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["source_id", "source_title", "target_id", "target_title", "relation", "reason",
                         "status", "reviewer", "notes"])
        for source_id, rows in links.items():
            for row in rows:
                writer.writerow([source_id, titles.get(source_id, ""), row.get("id", ""),
                                 titles.get(row.get("id", ""), row.get("title", "")),
                                 row.get("relation", ""), row.get("reason", ""), "pending", "", ""])
                count += 1
    print("rows", count, "->", OUT)


if __name__ == "__main__":
    main()
