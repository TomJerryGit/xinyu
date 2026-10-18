# -*- coding: utf-8 -*-
"""导入扩展经典：元曲全量、唐诗三百首、千家诗、古文观止、四书、蒙学。

数据源是本地 data/poetry_cache 下的 chinese-poetry 公共 JSON；只入库原文，
不伪造译文/注释。用法：python tools/import_extended_classics.py --apply
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "classics.db")
CACHE = os.path.join(BASE, "data", "poetry_cache")
REPORT = os.path.join(BASE, "data", "extended_import_report.json")

try:
    from opencc import OpenCC
    CONVERT = OpenCC("t2s").convert
except Exception:
    CONVERT = lambda value: value


def txt(value):
    if isinstance(value, list):
        value = "\n".join(str(x) for x in value)
    return CONVERT(str(value or "").replace("\r\n", "\n").strip())


def clean_title(value):
    value = txt(value)
    value = re.sub(r"^\s*\d{1,4}\s*[.、]\s*", "", value)
    if len(value) >= 2 and value[0] == "《" and value[-1] == "》":
        value = value[1:-1]
    return value[:120]


def iter_paragraphs(node):
    if isinstance(node, dict):
        if isinstance(node.get("paragraphs"), list) and (node.get("chapter") or node.get("title")):
            yield node
        for value in node.values():
            yield from iter_paragraphs(value)
    elif isinstance(node, list):
        for value in node:
            yield from iter_paragraphs(value)


def dynasty_of(value):
    value = txt(value)
    for key in ("先秦", "秦", "汉", "三国", "魏", "晋", "东晋", "南朝", "北朝", "南北朝", "唐", "五代", "宋", "北宋", "南宋", "元", "明", "清"):
        if value.startswith(key) or f"：{key}" in value:
            return key
    return "古代"


def record(title, author, dynasty, category, subcategory, content, source, famous=False):
    title = clean_title(title)
    content = txt(content)
    if not title or len(content) < 8 or len(content) > 60000:
        return None
    if "AI请求失败" in content:
        return None
    author = txt(author) or "佚名"
    difficulty = 1 if len(content) <= 40 else 2 if len(content) <= 120 else 3
    key = f"{title}|{author}|{content[:60]}"
    return {
        "id": "ext_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12],
        "title": title,
        "author": author,
        "dynasty": dynasty,
        "category": category,
        "subcategory": subcategory,
        "content": content,
        "translation": "",
        "annotation": "",
        "tags": ",".join(x for x in (category, subcategory, dynasty) if x),
        "source": source,
        "char_count": len(content),
        "is_famous": 1 if famous else 0,
        "difficulty_level": difficulty,
        "verified": 1,
    }


def load(name):
    path = os.path.join(CACHE, name + ".json")
    if not os.path.exists(path):
        return None
    return json.load(open(path, encoding="utf-8"))


def build_records():
    records = []
    yuanqu = load("元曲")
    if isinstance(yuanqu, list):
        for item in yuanqu:
            if isinstance(item, dict):
                rec = record(item.get("title"), item.get("author"), "元", "元曲", "集部/元曲",
                             item.get("paragraphs", ""), "local:chinese-poetry/yuanqu")
                if rec:
                    records.append(rec)

    for name, category, sub, famous in (
        ("唐诗三百首", "唐诗", "集部/唐诗", True),
        ("千家诗", "蒙学", "蒙学/千家诗", True),
    ):
        data = load(name)
        if not data:
            continue
        source = f"local:chinese-poetry/{name}"
        for item in iter_paragraphs(data):
            title = item.get("chapter") or item.get("title") or ""
            author = item.get("author") or ("佚名" if name == "千家诗" else "")
            rec = record(title, author, "唐" if category == "唐诗" else "宋", category, sub,
                         item.get("paragraphs", ""), source, famous)
            if rec:
                records.append(rec)

    guwen = load("古文观止")
    if guwen:
        for item in iter_paragraphs(guwen):
            author = txt(item.get("author"))
            dynasty = dynasty_of(author or item.get("source", ""))
            if dynasty in ("三国", "魏", "晋", "东晋", "南朝", "北朝", "南北朝"):
                category, sub = "魏晋南北朝", "集部/魏晋南北朝"
            elif dynasty in ("明", "清"):
                category, sub = "明清小品", "集部/明清小品"
            elif dynasty == "汉" and "赋" in clean_title(item.get("chapter")):
                category, sub = "汉赋", "集部/汉赋"
            else:
                category, sub = "经典散文", "集部/古文"
            rec = record(item.get("chapter"), author.split("：")[-1] if "：" in author else author,
                         dynasty, category, sub, item.get("paragraphs", ""),
                         "local:chinese-poetry/guwenguanzhi", True)
            if rec:
                records.append(rec)

    for name, chapter_author, category, sub, dynasty in (
        ("大学", "曾子", "经部", "经部/大学", "先秦"),
        ("中庸", "子思", "经部", "经部/中庸", "先秦"),
    ):
        data = load(name)
        if isinstance(data, dict) and data.get("paragraphs"):
            rec = record(data.get("chapter") or name, chapter_author, dynasty, category, sub,
                         data["paragraphs"], f"local:chinese-poetry/{name}", True)
            if rec:
                records.append(rec)

    mengzi = load("孟子")
    if isinstance(mengzi, list):
        for item in mengzi:
            if isinstance(item, dict):
                rec = record(f"孟子·{item.get('chapter','')}", "孟子及弟子", "战国", "经部", "经部/孟子",
                             item.get("paragraphs", ""), "local:chinese-poetry/mengzi", True)
                if rec:
                    records.append(rec)

    for name, dynasty, author in (
        ("三字经", "宋", "王应麟"), ("百家姓", "宋", "佚名"), ("千字文", "南朝梁", "周兴嗣"),
        ("弟子规", "清", "李毓秀"), ("声律启蒙", "清", "车万育"), ("文字蒙求", "清", "王筠"),
        ("幼学琼林", "明", "程登吉"),
    ):
        data = load(name)
        if isinstance(data, dict):
            content = data.get("paragraphs") or data.get("content") or ""
            rec = record(data.get("title") or name, data.get("author") or author, dynasty,
                         "蒙学", "蒙学", content, f"local:chinese-poetry/{name}", True)
            if rec:
                records.append(rec)
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    records = build_records()
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    if args.apply:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = DB + f".pre_extended_{stamp}.bak"
        target = sqlite3.connect(backup)
        conn.backup(target)
        target.close()
    existing = {}
    for row in conn.execute("SELECT id,title,author,content FROM classics"):
        key = f"{clean_title(row['title'])}|{txt(row['author'])}|{txt(row['content'])[:60]}"
        existing.setdefault(key, row["id"])
    added = updated = skipped = 0
    seen = set()
    for rec in records:
        key = f"{rec['title']}|{rec['author']}|{rec['content'][:60]}"
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        if key in existing:
            updated += 1
            if args.apply:
                conn.execute(
                    """UPDATE classics SET category=?, subcategory=?, dynasty=?, source=?, char_count=?,
                       is_famous=MAX(is_famous,?), verified=1, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                    (rec["category"], rec["subcategory"], rec["dynasty"], rec["source"],
                     rec["char_count"], rec["is_famous"], existing[key]),
                )
            continue
        added += 1
        if args.apply:
            conn.execute(
                """INSERT INTO classics
                   (id,title,author,dynasty,category,subcategory,content,translation,annotation,tags,source,
                    char_count,is_famous,difficulty_level,verified)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                (rec["id"], rec["title"], rec["author"], rec["dynasty"], rec["category"],
                 rec["subcategory"], rec["content"], rec["translation"], rec["annotation"],
                 rec["tags"], rec["source"], rec["char_count"], rec["is_famous"], rec["difficulty_level"]),
            )
    if args.apply:
        conn.commit()
        conn.execute("PRAGMA optimize")
    report = {
        "dry_run": not args.apply, "source_records": len(records),
        "added": added, "updated": updated, "skipped": skipped,
        "total": conn.execute("SELECT COUNT(*) FROM classics").fetchone()[0],
        "categories": [dict(row) for row in conn.execute(
            "SELECT category,COUNT(*) n FROM classics GROUP BY category ORDER BY n DESC")],
    }
    with open(REPORT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    conn.close()


if __name__ == "__main__":
    main()
