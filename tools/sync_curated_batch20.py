# -*- coding: utf-8 -*-
"""将首批 20 篇的人工命制题同步到审核队列和 CSV。"""
import csv
import json
import os
import sqlite3

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "docs", "reviews", "batch20_curated.jsonl")
DB = os.path.join(BASE, "data", "classics.db")
OUT_JSONL = os.path.join(BASE, "docs", "reviews", "batch20_questions.jsonl")
OUT_CSV = os.path.join(BASE, "docs", "reviews", "batch20_questions.csv")


def main():
    rows = [json.loads(line) for line in open(SRC, encoding="utf-8") if line.strip()]
    ids = []
    for row in rows:
        if row["classic_id"] not in ids:
            ids.append(row["classic_id"])
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    placeholders = ",".join("?" for _ in ids)
    conn.execute(
        f"DELETE FROM ai_review_queue WHERE kind='reading_question' AND classic_id IN ({placeholders})",
        ids,
    )
    queue = {}
    for row in rows:
        rid = conn.execute(
            "INSERT INTO ai_review_queue (kind,classic_id,payload) VALUES ('reading_question',?,?)",
            (row["classic_id"], json.dumps(row, ensure_ascii=False)),
        ).lastrowid
        queue[(row["classic_id"], row["cognitive"], row["question"])] = rid
    conn.commit()
    for row in rows:
        row["queue_id"] = queue[(row["classic_id"], row["cognitive"], row["question"])]
        row["review_minutes"] = ""
        row["decision"] = "pending"
        row["reviewer"] = ""
        row["edited"] = ""
        row["edited_question"] = ""
        row["edited_answer"] = ""
        row["notes"] = ""
    with open(OUT_JSONL, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["queue_id", "classic_id", "title", "cognitive", "question", "draft_answer",
                         "draft_rubric", "decision", "reviewer", "review_minutes", "edited",
                         "edited_question", "edited_answer", "notes"])
        for row in rows:
            writer.writerow([row["queue_id"], row["classic_id"], row["title"], row["cognitive"],
                             row["question"], row["answer"], json.dumps(row.get("rubric", []), ensure_ascii=False),
                             "pending", "", "", "", "", "", ""])
    conn.close()
    print("works", len(ids), "questions", len(rows), "->", OUT_CSV)


if __name__ == "__main__":
    main()
