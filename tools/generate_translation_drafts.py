# -*- coding: utf-8 -*-
"""为 300 篇名篇生成译文/注释草案（不直接写入正式字段）。

产物：
  data/reviews/translation_selected_300.jsonl
  data/reviews/translation_drafts.jsonl
  data/reviews/translation_review.csv

草案必须经人工复核后，用 tools/review_translations.py 写回数据库。
"""
import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "classics.db")
REVIEW_DIR = os.path.join(BASE, "data", "reviews")
SELECTED = os.path.join(REVIEW_DIR, "translation_selected_300.jsonl")
DRAFTS = os.path.join(REVIEW_DIR, "translation_drafts.jsonl")
CSV_PATH = os.path.join(REVIEW_DIR, "translation_review.csv")

QUOTAS = [
    ("唐诗", 65), ("宋词", 60), ("诗经", 30), ("宋诗", 25), ("元曲", 25),
    ("楚辞", 12), ("论语", 10), ("经典散文", 20), ("魏晋南北朝", 10),
    ("明清小品", 10), ("蒙学", 15), ("汉赋", 1), ("子部", 5), ("史部", 2), ("经部", 10),
]


def select(limit=300):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows, seen = [], set()
    for category, quota in QUOTAS:
        items = conn.execute(
            """SELECT id,title,author,dynasty,category,content,char_count,is_famous
               FROM classics
               WHERE category=? AND verified=1 AND char_count BETWEEN 8 AND 600
               ORDER BY is_famous DESC, char_count ASC LIMIT ?""",
            (category, quota),
        ).fetchall()
        for item in items:
            if item["id"] not in seen:
                seen.add(item["id"])
                rows.append(dict(item))
    if len(rows) < limit:
        extra = conn.execute(
            """SELECT id,title,author,dynasty,category,content,char_count,is_famous
               FROM classics WHERE verified=1 AND char_count BETWEEN 8 AND 600
               ORDER BY is_famous DESC, char_count ASC LIMIT ?""",
            (limit * 3,),
        ).fetchall()
        for item in extra:
            if len(rows) >= limit:
                break
            if item["id"] not in seen:
                seen.add(item["id"])
                rows.append(dict(item))
    conn.close()
    return rows[:limit]


def call_batch(engine, works):
    payload = json.dumps(
        [{"id": w["id"], "title": w["title"], "author": w["author"], "content": w["content"]} for w in works],
        ensure_ascii=False,
    )
    prompt = (
        "你是严谨的古籍编辑。对下列中国古典作品逐篇给出：\n"
        "1) translation：现代汉语直译，忠实原意、保留意象，不添加原文没有的内容；\n"
        "2) annotation：2-4 句注释，解释难词、典故、背景；不确定的地方写“待考”。\n"
        "只输出 JSON 数组，每项为 {\"id\":\"作品id\",\"translation\":\"...\",\"annotation\":\"...\"}。"
        "不要 Markdown，不要输出原文。\n作品：\n" + payload
    )
    raw = engine.generate(prompt)
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0]
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end > start:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def call_one(engine, work):
    prompt = (
        "你是严谨的古籍编辑。把下面这篇中国古典作品翻译成现代汉语，并写 2-4 句注释。\n"
        "只输出 JSON 对象：{\"id\":\"给定id\",\"translation\":\"...\",\"annotation\":\"...\"}。"
        "不要 Markdown，不要输出原文，不要编造不确定的典故。\n"
        f"id={work['id']}\n标题：{work['title']}\n作者：{work['author']}\n原文：{work['content']}"
    )
    raw = str(engine.generate(prompt) or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        data = json.loads(raw[start : end + 1])
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-tokens", type=int, default=2000)
    parser.add_argument("--single", action="store_true")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    os.makedirs(REVIEW_DIR, exist_ok=True)
    selected = select(max(1, args.limit))
    with open(SELECTED, "w", encoding="utf-8") as handle:
        for item in selected:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    print("selected", len(selected))

    done = set()
    if args.resume and os.path.exists(DRAFTS):
        for line in open(DRAFTS, encoding="utf-8"):
            try:
                item = json.loads(line)
                if item.get("status") in ("pending", "approved"):
                    done.add(item["id"])
            except Exception:
                pass
    sys.path.insert(0, BASE)
    from engine import LazyEngine

    engine = LazyEngine()
    if not engine.is_configured():
        raise SystemExit("AI 未配置，无法生成草案")
    try:
        engine._ensure().max_tokens = max(512, args.max_tokens)
    except Exception:
        pass
    pending = [item for item in selected if item["id"] not in done]
    print("pending", len(pending), "already", len(done))
    if args.single:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading

        lock = threading.Lock()
        with open(DRAFTS, "a", encoding="utf-8") as handle:
            def work_one(work):
                try:
                    result = call_one(engine, work)
                except Exception:
                    result = {}
                record = {
                    "id": work["id"], "title": work["title"], "author": work["author"],
                    "category": work["category"], "original": work["content"],
                    "translation": str(result.get("translation") or "").strip(),
                    "annotation": str(result.get("annotation") or "").strip(),
                    "status": "pending" if result.get("translation") else "failed",
                    "reviewer": "", "reviewed_at": "",
                    "model": getattr(engine, "model", ""),
                    "generated_at": datetime.now().isoformat(timespec="seconds"),
                }
                with lock:
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                    handle.flush()
                return record["status"]
            with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
                futures = [pool.submit(work_one, work) for work in pending]
                for index, future in enumerate(as_completed(futures), 1):
                    print("single", index, "of", len(futures), future.result())
    else:
        with open(DRAFTS, "a", encoding="utf-8") as handle:
            for start in range(0, len(pending), args.batch_size):
                batch = pending[start : start + args.batch_size]
                started = time.perf_counter()
                items = call_batch(engine, batch)
                by_id = {str(item.get("id")): item for item in items if isinstance(item, dict)}
                for work in batch:
                    result = by_id.get(work["id"], {})
                    record = {
                        "id": work["id"],
                        "title": work["title"],
                        "author": work["author"],
                        "category": work["category"],
                        "original": work["content"],
                        "translation": str(result.get("translation") or "").strip(),
                        "annotation": str(result.get("annotation") or "").strip(),
                        "status": "pending" if result else "failed",
                        "reviewer": "",
                        "reviewed_at": "",
                        "model": getattr(engine, "model", ""),
                        "generated_at": datetime.now().isoformat(timespec="seconds"),
                    }
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                handle.flush()
                print("batch", start // args.batch_size + 1, "of", (len(pending) + args.batch_size - 1) // args.batch_size,
                      "items", len(items), "seconds", round(time.perf_counter() - started, 1))

    records = []
    for line in open(DRAFTS, encoding="utf-8"):
        try:
            records.append(json.loads(line))
        except Exception:
            pass
    import csv

    with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "title", "author", "category", "original", "translation", "annotation", "status", "reviewer", "notes"])
        for record in records:
            writer.writerow([
                record["id"], record["title"], record["author"], record["category"], record["original"],
                record["translation"], record["annotation"], record["status"], record["reviewer"], "",
            ])
    print("drafts", len(records), "csv", CSV_PATH)


if __name__ == "__main__":
    main()
