# -*- coding: utf-8 -*-
"""把 batch20_questions.csv 的审核决定写回审核队列/题库。

用法：python tools/apply_review_batch.py --apply
只处理 decision=approved/rejected 的行。
"""
import argparse
import csv
import json
import os
import sqlite3
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(BASE, "docs", "reviews", "batch20_questions.csv")
DB = os.path.join(BASE, "data", "classics.db")
sys.path.insert(0, BASE)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    rows = list(csv.DictReader(open(CSV_PATH, encoding="utf-8-sig", newline="")))
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    applied = 0
    for row in rows:
        decision = (row.get("decision") or "").strip().lower()
        if decision not in ("approved", "rejected"):
            continue
        qid = (row.get("queue_id") or "").strip()
        if not qid:
            continue
        current = conn.execute("SELECT payload FROM ai_review_queue WHERE id=?", (qid,)).fetchone()
        if not current:
            continue
        try:
            payload = json.loads(current["payload"])
        except ValueError:
            payload = {}
        if row.get("edited_question"):
            payload["question"] = row["edited_question"]
        if row.get("edited_answer"):
            payload["answer"] = row["edited_answer"]
        payload["reviewer"] = row.get("reviewer", "")
        if not args.apply:
            applied += 1
            continue
        conn.execute(
            """UPDATE ai_review_queue SET payload=?, status=?, reviewer=?, notes=?,
               reviewed_at=CURRENT_TIMESTAMP WHERE id=?""",
            (json.dumps(payload, ensure_ascii=False), decision, row.get("reviewer", ""),
             row.get("notes", ""), qid),
        )
        if decision == "approved":
            work = conn.execute("SELECT category,dynasty FROM classics WHERE id=?", (row["classic_id"],)).fetchone()
            conn.execute(
                """INSERT OR REPLACE INTO question_bank
                   (id,classic_id,category,dynasty,difficulty,type,question,options,answer,explanation,
                    cognitive,rubric,source,verified)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'reviewed',1)""",
                (f"review_{qid}", row["classic_id"], work["category"] if work else "",
                 work["dynasty"] if work else "", 2, "简答", payload.get("question", ""), "[]",
                 payload.get("answer", ""), payload.get("explanation", ""),
                 payload.get("cognitive", "分析"), json.dumps(payload.get("rubric", []), ensure_ascii=False)),
            )
        applied += 1
    if args.apply:
        conn.commit()
    conn.close()
    print(("applied" if args.apply else "would_apply"), applied)


if __name__ == "__main__":
    main()
