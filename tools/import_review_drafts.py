# -*- coding: utf-8 -*-
"""把 100 篇名篇的译文草案转成理解/分析题草案，并统一进入审核队列。

注意：这是“草案”，不是人工校勘成品；审核通过后才会进入 question_bank。
"""
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRAFTS = os.path.join(BASE, "data", "reviews", "translation_drafts.jsonl")
OUT = os.path.join(BASE, "data", "reviews", "reading_questions_100.jsonl")
sys.path.insert(0, BASE)


def main():
    from classics_database import ClassicsDatabase

    by_id = {}
    for line in open(DRAFTS, encoding="utf-8"):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("status") == "pending" and row.get("translation"):
            by_id[row["id"]] = row
    works = list(by_id.values())[:100]
    questions = []
    for row in works:
        title = row.get("title", "")
        cid = row.get("id", "")
        questions.append({
            "classic_id": cid, "title": title, "type": "简答", "cognitive": "理解",
            "question": f"结合原文，用自己的话概括《{title}》的主要内容。",
            "answer": row.get("translation", ""),
            "explanation": "参考译文；评分看是否抓住人物、景物与事件。",
            "rubric": [
                {"dimension": "内容准确", "points": 60, "criteria": "覆盖原文主要信息，无漏译"},
                {"dimension": "语言表达", "points": 40, "criteria": "通顺、连贯，不是逐字硬译"},
            ],
        })
        questions.append({
            "classic_id": cid, "title": title, "type": "简答", "cognitive": "分析",
            "question": f"《{title}》表达了怎样的情感或主旨？结合原文具体分析。",
            "answer": row.get("annotation", "") or "参考：结合意象、动作或议论句，说明情感与依据。",
            "explanation": "开放题，按量规人工评分。",
            "rubric": [
                {"dimension": "观点明确", "points": 30, "criteria": "准确概括情感/主旨"},
                {"dimension": "原文依据", "points": 40, "criteria": "引用词句并说明作用"},
                {"dimension": "分析深度", "points": 30, "criteria": "能联系意象、结构或背景"},
            ],
        })
    with open(OUT, "w", encoding="utf-8") as handle:
        for item in questions:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    db = ClassicsDatabase(os.path.join(BASE, "data", "classics.db"))
    queued = 0
    existing = []
    for row in db.conn.execute("SELECT payload FROM ai_review_queue WHERE kind='reading_question'"):
        try:
            existing.append(json.loads(row[0]))
        except Exception:
            pass
    keys = {(x.get("classic_id"), x.get("cognitive")) for x in existing}
    for item in questions:
        if (item["classic_id"], item["cognitive"]) in keys:
            continue
        db.enqueue_ai_review("reading_question", item["classic_id"], item)
        queued += 1
    # 译文草案也进入同一队列
    existing_t = []
    for row in db.conn.execute("SELECT payload FROM ai_review_queue WHERE kind='translation_draft'"):
        try:
            existing_t.append(json.loads(row[0]))
        except Exception:
            pass
    tkeys = {x.get("classic_id") for x in existing_t}
    tqueued = 0
    for row in works:
        if row["id"] in tkeys:
            continue
        db.enqueue_ai_review("translation_draft", row["id"], {
            "classic_id": row["id"], "title": row.get("title", ""),
            "translation": row.get("translation", ""), "annotation": row.get("annotation", ""),
        })
        tqueued += 1
    print("works", len(works), "questions", len(questions), "queued_questions", queued, "queued_translations", tqueued)
    db.conn.close()


if __name__ == "__main__":
    main()
