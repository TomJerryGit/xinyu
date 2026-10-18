# -*- coding: utf-8 -*-
"""经典库高质量整理与一次入库。

用法：
    python tools/curate_classics.py --dry-run
    python tools/curate_classics.py --apply

数据源（本地，不联网）：
    data/poetry_cache/{唐诗,宋词,诗经,楚辞,论语}.json
    resources/classics.json

原则：
* 以权威公共数据集/内置精选为主，不伪造译文、注释；
* 先备份数据库，再清洗旧数据、补朝代/二级分类/来源；
* 按“标题+作者”合并，保留原 ID（用户笔记/收藏不丢）；
* 删除明确垃圾（空正文、AI 失败、无引用的重复/编号标题）；
* 报告写入 data/classics_curation_report.json。
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
CURATED = os.path.join(BASE, "resources", "classics.json")
REPORT = os.path.join(BASE, "data", "classics_curation_report.json")

CATEGORY_DYNASTY = {
    "唐诗": "唐", "宋词": "宋", "宋诗": "宋", "元曲": "元",
    "诗经": "先秦", "楚辞": "战国", "论语": "春秋", "蒙学": "古代",
    "经典散文": "古代", "经部": "先秦", "子部": "先秦", "史部": "古代",
    "集部": "古代", "对联": "古代",
}
CATEGORY_SUB = {
    "唐诗": "集部/唐诗", "宋词": "集部/宋词", "宋诗": "集部/宋诗",
    "元曲": "集部/元曲", "楚辞": "集部/楚辞", "经典散文": "集部/古文",
    "诗经": "经部/诗经", "论语": "经部/论语", "经部": "经部",
    "子部": "子部/诸子", "史部": "史部/史传", "蒙学": "蒙学",
    "集部": "集部", "对联": "集部/对联",
}
CURATED_CATEGORY = {
    "诸子百家": ("子部", "子部/诸子"),
    "对联": ("集部", "集部/对联"),
    "经典散文": ("经典散文", "集部/古文"),
    "唐诗": ("唐诗", "集部/唐诗"),
    "宋词": ("宋词", "集部/宋词"),
    "楚辞": ("楚辞", "集部/楚辞"),
    "蒙学": ("蒙学", "蒙学"),
}
FAMOUS = {
    "静夜思", "春晓", "登鹳雀楼", "望庐山瀑布", "早发白帝城", "将进酒",
    "水调歌头·明月几时有", "念奴娇·赤壁怀古", "声声慢·寻寻觅觅", "如梦令·常记溪亭日暮",
    "关雎", "蒹葭", "离骚", "九歌·湘君", "兰亭集序", "岳阳楼记", "醉翁亭记",
    "滕王阁序", "归去来兮辞", "逍遥游", "鱼我所欲也", "劝学", "三字经",
}
NUMBER_PREFIX = re.compile(r"^\s*\d{1,4}\s*[.、]\s*")
SPACE = re.compile(r"[ \t\u3000]+")


def text(value):
    if isinstance(value, list):
        value = "\n".join(str(item) for item in value)
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def clean_title(value):
    title = SPACE.sub(" ", text(value)).strip()
    title = NUMBER_PREFIX.sub("", title).strip()
    if len(title) >= 2 and title[0] == "《" and title[-1] == "》":
        title = title[1:-1].strip()
    return title[:120]


def clean_content(value, title, author):
    content = text(value)
    lines = content.splitlines()
    while lines and (lines[0].strip() in (title, author) or not lines[0].strip()):
        lines.pop(0)
    content = "\n".join(lines)
    content = re.sub(r"\n{3,}", "\n\n", content).strip()
    return content


def key_of(title, author):
    return re.sub(r"[^\w\u4e00-\u9fff]", "", f"{title}|{author}".lower())


def content_key(content):
    normalized = re.sub(r"\s+", "", content or "")
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]


def content_prefix(content):
    return re.sub(r"\s+", "", content or "")[:40]


def known_category(category):
    return CURATED_CATEGORY.get(category, (category, CATEGORY_SUB.get(category, "")))


def make_record(title, author, dynasty, category, content, source, *, subcategory="", annotation="", tags="", famous=False):
    title = clean_title(title)
    author = SPACE.sub(" ", text(author)).strip() or "佚名"
    category, default_sub = known_category(category)
    subcategory = subcategory or default_sub
    dynasty = dynasty or CATEGORY_DYNASTY.get(category, "未知")
    content = clean_content(content, title, author)
    if not title or len(content) < 8:
        return None
    if len(content) > 30000:
        return None
    if "AI请求失败" in content or "API Key无效" in content:
        return None
    if not tags:
        tags = ",".join(part for part in (category, subcategory, dynasty) if part)
    elif isinstance(tags, (list, tuple)):
        tags = ",".join(str(item) for item in tags)
    else:
        tags = text(tags)
    difficulty = 1 if len(content) <= 40 else 2 if len(content) <= 120 else 3
    return {
        "id": "cur_" + hashlib.sha1(
            f"{key_of(title, author)}|{content_key(content)}".encode("utf-8")
        ).hexdigest()[:12],
        "title": title,
        "author": author,
        "dynasty": dynasty,
        "category": category,
        "subcategory": subcategory,
        "content": content,
        "translation": "",
        "annotation": text(annotation),
        "tags": tags,
        "source": source,
        "char_count": len(content),
        "is_famous": 1 if famous or title in FAMOUS else 0,
        "difficulty_level": difficulty,
        "verified": 1,
    }


def cache_records(limit_per_source=0):
    specs = {
        "唐诗": ("唐诗", "title", "author", "paragraphs", "唐", "local:chinese-poetry/tang"),
        "宋词": ("宋词", "rhythmic", "author", "paragraphs", "宋", "local:chinese-poetry/songci"),
        "诗经": ("诗经", "title", "author", "content", "先秦", "local:chinese-poetry/shijing"),
        "楚辞": ("楚辞", "title", "author", "content", "战国", "local:chinese-poetry/chuci"),
        "论语": ("论语", "chapter", "author", "paragraphs", "春秋", "local:chinese-poetry/lunyu"),
    }
    for name, (category, title_key, author_key, content_key, dynasty, source) in specs.items():
        path = os.path.join(CACHE, f"{name}.json")
        if not os.path.exists(path):
            continue
        rows = json.load(open(path, encoding="utf-8"))
        if limit_per_source:
            rows = rows[:limit_per_source]
        for item in rows:
            if not isinstance(item, dict):
                continue
            title = item.get(title_key) or item.get("title") or item.get("name") or ""
            author = item.get(author_key) or "佚名"
            if name == "论语":
                author = "孔子弟子"
            elif name == "诗经":
                author = "佚名"
            record = make_record(title, author, dynasty, category, item.get(content_key, ""), source)
            if record:
                yield record


def curated_records():
    if not os.path.exists(CURATED):
        return
    data = json.load(open(CURATED, encoding="utf-8"))
    if not isinstance(data, dict):
        return
    for category, rows in data.items():
        for item in rows if isinstance(rows, list) else []:
            if not isinstance(item, dict):
                continue
            record = make_record(
                item.get("title"), item.get("author"), item.get("dynasty", ""),
                category, item.get("content", ""), "bundled:classics.json",
                subcategory=item.get("subcategory", ""),
                annotation=item.get("annotation", ""),
                tags=item.get("tags", ""),
                famous=True,
            )
            if record:
                yield record


def backup_database():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = DB + f".pre_curate_{stamp}.bak"
    source = sqlite3.connect(DB)
    target = sqlite3.connect(path)
    source.backup(target)
    target.close()
    source.close()
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="真正写库；默认只 dry-run")
    parser.add_argument("--limit-per-source", type=int, default=0, help="调试用，每个缓存源最多导入多少条")
    parser.add_argument("--keep-duplicates", action="store_true", help="不清理无引用的重复/垃圾旧数据")
    args = parser.parse_args()

    sqlite3.connect(DB).close()
    backup = backup_database() if args.apply else ""
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    before = conn.execute("SELECT COUNT(*) FROM classics").fetchone()[0]
    refs = set()
    for table in ("user_notes", "favorites", "reading_history"):
        try:
            refs.update(row[0] for row in conn.execute(f"SELECT DISTINCT classic_id FROM {table}"))
        except sqlite3.Error:
            pass

    existing = [dict(row) for row in conn.execute("SELECT * FROM classics")]
    index = {}
    for row in existing:
        title = clean_title(row.get("title"))
        author = SPACE.sub(" ", text(row.get("author"))).strip() or "佚名"
        key = key_of(title, author)
        index.setdefault(key, []).append(row)
        # 清洗旧记录的标题/朝代/二级分类/来源
        if args.apply:
            new_dynasty = row.get("dynasty") or CATEGORY_DYNASTY.get(row.get("category"), "")
            new_sub = row.get("subcategory") or CATEGORY_SUB.get(row.get("category"), "")
            conn.execute(
                "UPDATE classics SET title=?, dynasty=?, subcategory=?, source=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (title or row.get("title"), new_dynasty or "未知", new_sub, row.get("source") or "legacy", row["id"]),
            )

    stats = {"candidates": 0, "inserted": 0, "updated": 0, "rejected": 0, "deleted": 0, "backup": backup}
    seen = set()
    categories = {}
    for record in list(curated_records()) + list(cache_records(args.limit_per_source)):
        stats["candidates"] += 1
        identity = key_of(record["title"], record["author"])
        unique = (identity, content_prefix(record["content"]))
        if unique in seen:
            continue
        seen.add(unique)
        categories[record["category"]] = categories.get(record["category"], 0) + 1
        matches = index.get(identity, [])
        target = None
        for row in matches:
            if content_prefix(row.get("content")) == unique[1]:
                target = row
                break
        if target is None and len(matches) == 1:
            target = matches[0]
        if target is not None:
            stats["updated"] += 1
            if args.apply:
                conn.execute(
                    """UPDATE classics SET title=?, author=?, dynasty=?, category=?, subcategory=?,
                       content=?, annotation=CASE WHEN ?<>'' THEN ? ELSE annotation END,
                       tags=CASE WHEN ?<>'' THEN ? ELSE tags END, source=?, char_count=?,
                       is_famous=?, difficulty_level=?, verified=1, updated_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (
                        record["title"], record["author"], record["dynasty"], record["category"],
                        record["subcategory"], record["content"], record["annotation"], record["annotation"],
                        record["tags"], record["tags"], record["source"], record["char_count"],
                        record["is_famous"], record["difficulty_level"], target["id"],
                    ),
                )
            continue
        if args.apply:
            conn.execute(
                """INSERT INTO classics
                   (id,title,author,dynasty,category,subcategory,content,translation,annotation,tags,source,
                    char_count,is_famous,difficulty_level,verified)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                (
                    record["id"], record["title"], record["author"], record["dynasty"], record["category"],
                    record["subcategory"], record["content"], "", record["annotation"], record["tags"],
                    record["source"], record["char_count"], record["is_famous"], record["difficulty_level"],
                ),
            )
        stats["inserted"] += 1

    # 清理：空正文、AI 失败、无引用重复；有笔记/收藏/阅读历史的保留
    if args.apply and not args.keep_duplicates:
        rows = [dict(row) for row in conn.execute("SELECT * FROM classics")]
        groups = {}
        for row in rows:
            key = (key_of(clean_title(row["title"]), row["author"]), content_key(row.get("content")))
            groups.setdefault(key, []).append(row)
        for group in groups.values():
            group.sort(key=lambda row: (int(row.get("verified") or 0), int(row.get("char_count") or 0)), reverse=True)
            for row in group[1:]:
                if row["id"] not in refs:
                    conn.execute("DELETE FROM classics WHERE id=?", (row["id"],))
                    stats["deleted"] += 1
        for row in rows:
            content = text(row.get("content"))
            if row["id"] in refs:
                continue
            if len(content) < 8 or "AI请求失败" in content or NUMBER_PREFIX.match(row["title"] or ""):
                conn.execute("DELETE FROM classics WHERE id=?", (row["id"],))
                stats["deleted"] += 1

    if args.apply:
        conn.commit()
        conn.execute("PRAGMA optimize")
    after = conn.execute("SELECT COUNT(*) FROM classics").fetchone()[0]
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "dry_run": not args.apply,
        "before": before,
        "after": after,
        "stats": stats,
        "imported_by_category": categories,
        "categories_after": [
            {"category": row[0], "count": row[1]}
            for row in conn.execute("SELECT category, COUNT(*) FROM classics GROUP BY category ORDER BY COUNT(*) DESC")
        ],
        "missing_dynasty": conn.execute("SELECT COUNT(*) FROM classics WHERE dynasty IS NULL OR TRIM(dynasty) IN ('','未知')").fetchone()[0],
    }
    conn.close()
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    print(json.dumps({k: report[k] for k in ("dry_run", "before", "after", "stats", "imported_by_category")}, ensure_ascii=False, indent=2))
    print("report:", REPORT)


if __name__ == "__main__":
    main()
