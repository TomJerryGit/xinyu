# -*- coding: utf-8 -*-
"""人工复核 300 篇译文/注释草案。

用法：
    python tools/review_translations.py --list
    # 编辑 data/reviews/translation_review.csv，把 status 改为 approved/rejected，填写 reviewer
    python tools/review_translations.py --from-csv --apply
"""
import argparse
import csv
import json
import os
import sqlite3
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "classics.db")
DRAFTS = os.path.join(BASE, "data", "reviews", "translation_drafts.jsonl")
CSV_PATH = os.path.join(BASE, "data", "reviews", "translation_review.csv")


def read_drafts():
    rows = []
    if not os.path.exists(DRAFTS):
        return rows
    for line in open(DRAFTS, encoding="utf-8"):
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def write_drafts(rows):
    with open(DRAFTS, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(rows):
    with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "title", "author", "category", "original", "translation", "annotation", "status", "reviewer", "notes"])
        for row in rows:
            writer.writerow([row.get("id", ""), row.get("title", ""), row.get("author", ""), row.get("category", ""),
                             row.get("original", ""), row.get("translation", ""), row.get("annotation", ""),
                             row.get("status", "pending"), row.get("reviewer", ""), row.get("notes", "")])


def apply_rows(rows):
    conn = sqlite3.connect(DB)
    applied = 0
    for row in rows:
        if row.get("status") != "approved" or not row.get("translation"):
            continue
        conn.execute(
            """UPDATE classics SET translation=?, annotation=?, translation_status='approved',
               annotation_status=?, reviewed_by=?, reviewed_at=CURRENT_TIMESTAMP,
               updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (row["translation"], row.get("annotation", ""),
             "approved" if row.get("annotation") else "", row.get("reviewer", "reviewer"), row["id"]),
        )
        applied += 1
    conn.commit()
    conn.close()
    return applied


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--from-csv", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--approve", default="")
    parser.add_argument("--reject", default="")
    parser.add_argument("--reviewer", default="")
    args = parser.parse_args()
    rows = read_drafts()
    by_id = {row["id"]: row for row in rows}

    if args.approve:
        for cid in [x.strip() for x in args.approve.split(",") if x.strip()]:
            if cid in by_id:
                by_id[cid]["status"] = "approved"
                by_id[cid]["reviewer"] = args.reviewer
                by_id[cid]["reviewed_at"] = datetime.now().isoformat(timespec="seconds")
    if args.reject:
        for cid in [x.strip() for x in args.reject.split(",") if x.strip()]:
            if cid in by_id:
                by_id[cid]["status"] = "rejected"
                by_id[cid]["reviewer"] = args.reviewer
                by_id[cid]["reviewed_at"] = datetime.now().isoformat(timespec="seconds")

    if args.from_csv and os.path.exists(CSV_PATH):
        with open(CSV_PATH, encoding="utf-8-sig", newline="") as handle:
            for csv_row in csv.DictReader(handle):
                cid = csv_row.get("id", "")
                if cid in by_id:
                    by_id[cid]["status"] = (csv_row.get("status") or "pending").strip().lower()
                    by_id[cid]["reviewer"] = csv_row.get("reviewer", "")
                    by_id[cid]["notes"] = csv_row.get("notes", "")
                    if csv_row.get("translation"):
                        by_id[cid]["translation"] = csv_row["translation"]
                    if csv_row.get("annotation"):
                        by_id[cid]["annotation"] = csv_row["annotation"]

    rows = list(by_id.values())
    write_drafts(rows)
    write_csv(rows)
    if args.apply:
        print("applied", apply_rows(rows))
    if args.list:
        pending = [row for row in rows if row.get("status") == "pending"]
        print("total", len(rows), "pending", len(pending), "approved", sum(1 for r in rows if r.get("status") == "approved"))
        for row in pending[:30]:
            print(row["id"], row["title"], row["author"])
    print("csv", CSV_PATH)


if __name__ == "__main__":
    main()
