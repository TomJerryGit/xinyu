# -*- coding: utf-8 -*-
"""导出首批 20 篇 / 40 题审核包，并统计审核耗时/通过率/修改率。

用法：
    python tools/review_batch.py --export
    python tools/review_batch.py --stats
"""
import argparse
import csv
import json
import os
import sqlite3

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "docs", "reviews", "batch20_curated.jsonl")
OUT_JSONL = os.path.join(BASE, "docs", "reviews", "batch20_questions.jsonl")
OUT_CSV = os.path.join(BASE, "docs", "reviews", "batch20_questions.csv")
DB = os.path.join(BASE, "data", "classics.db")


def load_questions():
    rows = []
    for line in open(SRC, encoding="utf-8"):
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def export_batch(size=20):
    rows = load_questions()
    works = []
    seen = set()
    for row in rows:
        if row["classic_id"] not in seen:
            seen.add(row["classic_id"])
            works.append(row["classic_id"])
        if len(works) >= size:
            break
    selected = [row for row in rows if row["classic_id"] in set(works)]
    # 关联审核队列 id，便于之后在 UI 审核
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    queue = {}
    for row in conn.execute("SELECT id,payload FROM ai_review_queue WHERE kind='reading_question' AND status='pending'"):
        try:
            payload = json.loads(row["payload"])
        except ValueError:
            continue
        queue[(payload.get("classic_id"), payload.get("cognitive"), payload.get("question"))] = row["id"]
    conn.close()
    for row in selected:
        row["queue_id"] = queue.get((row["classic_id"], row.get("cognitive"), row.get("question")), "")
        row["review_minutes"] = ""
        row["decision"] = "pending"
        row["reviewer"] = ""
        row["edited"] = ""
        row["edited_question"] = ""
        row["edited_answer"] = ""
        row["notes"] = ""
    with open(OUT_JSONL, "w", encoding="utf-8") as handle:
        for row in selected:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["queue_id", "classic_id", "title", "cognitive", "question", "draft_answer",
                         "draft_rubric", "decision", "reviewer", "review_minutes", "edited",
                         "edited_question", "edited_answer", "notes"])
        for row in selected:
            writer.writerow([row["queue_id"], row["classic_id"], row["title"], row["cognitive"],
                             row["question"], row["answer"], json.dumps(row.get("rubric", []), ensure_ascii=False),
                             row["decision"], "", "", "", "", "", ""])
    print("works", len(works), "questions", len(selected), "->", OUT_CSV)


def stats():
    if not os.path.exists(OUT_CSV):
        print("no batch csv")
        return
    with open(OUT_CSV, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    reviewed = [r for r in rows if r.get("decision") in ("approved", "rejected")]
    approved = [r for r in reviewed if r.get("decision") == "approved"]
    times = []
    edited = 0
    for row in reviewed:
        try:
            times.append(float(row.get("review_minutes") or 0))
        except ValueError:
            pass
        if str(row.get("edited", "")).lower() in ("1", "true", "yes", "y"):
            edited += 1
    print(json.dumps({
        "total": len(rows),
        "reviewed": len(reviewed),
        "approved": len(approved),
        "approval_rate": round(len(approved) / max(len(reviewed), 1) * 100, 1),
        "avg_minutes": round(sum(times) / max(len(times), 1), 2),
        "edit_rate": round(edited / max(len(reviewed), 1) * 100, 1),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()
    if args.stats:
        stats()
    else:
        export_batch()
