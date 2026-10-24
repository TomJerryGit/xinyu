# -*- coding: utf-8 -*-
"""给新增 20 篇古文补译文/注释草案，并加入审核队列。

用法：python tools/add_prose_translations.py --apply
"""
import argparse
import json
import os
import shutil
import sqlite3

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "classics.db")
PROSE = os.path.join(BASE, "resources", "curated_prose.json")
TRANS = os.path.join(BASE, "resources", "curated_prose_translations.json")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    prose = json.load(open(PROSE, encoding="utf-8"))
    trans = json.load(open(TRANS, encoding="utf-8"))
    ids = {item["id"] for item in prose}
    missing = sorted(set(trans) - ids)
    if missing:
        raise SystemExit(f"unknown ids: {missing}")
    if not args.apply:
        print("would_update", len(trans), "drafts")
        return

    backup = DB + ".before_prose_translations"
    if not os.path.exists(backup):
        shutil.copy2(DB, backup)
    conn = sqlite3.connect(DB)
    updated = queued = 0
    for item in prose:
        data = trans.get(item["id"])
        if not data:
            continue
        item["translation"] = data["translation"]
        item["annotation"] = data["annotation"]
        conn.execute(
            """UPDATE classics SET translation=?,annotation=?,translation_status='draft',
               annotation_status='draft',updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (data["translation"], data["annotation"], item["id"]),
        )
        existing = conn.execute(
            "SELECT 1 FROM ai_review_queue WHERE kind='translation_draft' AND classic_id=? AND status='pending'",
            (item["id"],),
        ).fetchone()
        if not existing:
            payload = {
                "classic_id": item["id"], "title": item["title"],
                "translation": data["translation"], "annotation": data["annotation"],
            }
            conn.execute(
                "INSERT INTO ai_review_queue (kind,classic_id,payload) VALUES ('translation_draft',?,?)",
                (item["id"], json.dumps(payload, ensure_ascii=False)),
            )
            queued += 1
        updated += 1
    conn.commit()
    conn.close()
    json.dump(prose, open(PROSE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("updated", updated, "queued", queued)


if __name__ == "__main__":
    main()
