# -*- coding: utf-8 -*-
"""把 30 篇互文校勘表拆成 10 篇一批。"""
import csv
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "docs", "reviews", "intertext_30_review.csv")
OUT_DIR = os.path.join(BASE, "docs", "reviews")


def main():
    with open(SRC, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    by_source = {}
    order = []
    for row in rows:
        sid = row["source_id"]
        if sid not in by_source:
            by_source[sid] = []
            order.append(sid)
        by_source[sid].append(row)
    for batch in range(0, len(order), 10):
        selected = order[batch:batch + 10]
        out = os.path.join(OUT_DIR, f"intertext_batch{batch // 10 + 1}_10.csv")
        with open(out, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            for sid in selected:
                writer.writerows(by_source[sid])
        print("batch", batch // 10 + 1, "works", len(selected),
              "rows", sum(len(by_source[x]) for x in selected), "->", out)


if __name__ == "__main__":
    main()
