# -*- coding: utf-8 -*-
"""规则基础题库：作者 / 朝代 / 分类三类选择题，全量、可复现、无需 AI。"""
import hashlib
import json
import os
import random
import re
import sqlite3

AUTHOR_PREFIX = re.compile(r"^[（(][^）)]{1,12}[）)]\s*")
BAD_AUTHORS = {"", "佚名", "不详", "不詳", "无名氏", "無名氏"}
BANK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "question_bank")


def clean_author(value):
    value = AUTHOR_PREFIX.sub("", str(value or "")).strip()
    return value


def _safe_name(category):
    return re.sub(r'[\\/:*?"<>|]', "_", category or "全部")


def load_prebuilt(category):
    """读取按分类预置的题库；没有文件时返回空列表。"""
    path = os.path.join(BANK_DIR, f"{_safe_name(category)}.json")
    if not os.path.exists(path):
        return []
    try:
        rows = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return []
    questions = []
    for row in rows if isinstance(rows, list) else []:
        try:
            questions.append({
                "type": row.get("type", "选择"), "question": row["question"],
                "options": row.get("options", []), "answer": int(row.get("answer", 0)),
                "explanation": row.get("explanation", ""), "id": row.get("id", ""),
                "classic_id": row.get("classic_id", ""), "cognitive": row.get("cognitive", "识记"),
                "rubric": row.get("rubric", "[]"),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return questions


def export_prebuilt(conn):
    """把当前 SQLite 题库按分类导出到 resources/question_bank/*.json。"""
    os.makedirs(BANK_DIR, exist_ok=True)
    conn.row_factory = sqlite3.Row
    categories = [r[0] for r in conn.execute("SELECT DISTINCT category FROM question_bank")]
    total = 0
    for category in categories:
        rows = []
        for row in conn.execute(
            """SELECT id,classic_id,type,question,options,answer,explanation,cognitive,rubric
               FROM question_bank WHERE category=? ORDER BY id""",
            (category,),
        ):
            try:
                options = json.loads(row["options"])
            except (TypeError, ValueError):
                continue
            rows.append({
                "id": row["id"], "classic_id": row["classic_id"], "type": row["type"],
                "question": row["question"], "options": options, "answer": row["answer"],
                "explanation": row["explanation"],
                "cognitive": row["cognitive"] if "cognitive" in row.keys() else "识记",
                "rubric": row["rubric"] if "rubric" in row.keys() else "[]",
            })
        path = os.path.join(BANK_DIR, f"{_safe_name(category)}.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(rows, handle, ensure_ascii=False, separators=(",", ":"))
        total += len(rows)
        print("exported", category, len(rows), "->", path)
    return total


def _stable_random(seed):
    return random.Random(int(hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8], 16))


def build_bank(conn, limit=0, rebuild=False, category=""):
    conn.row_factory = sqlite3.Row
    if rebuild:
        conn.execute("DELETE FROM question_bank")
        conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM question_bank").fetchone()[0]
    if count and not rebuild and not category:
        return count
    if category:
        existing = conn.execute("SELECT COUNT(*) FROM question_bank WHERE category=?", (category,)).fetchone()[0]
        if existing and not rebuild:
            return count
    query = "SELECT id,title,author,dynasty,category FROM classics WHERE verified=1"
    params = []
    if category:
        query += " AND category=?"
        params.append(category)
    if limit > 0:
        query += " LIMIT ?"
        params.append(limit)
    works = conn.execute(query, params).fetchall()
    authors = sorted({clean_author(r[0]) for r in conn.execute("SELECT DISTINCT author FROM classics")} - BAD_AUTHORS)
    dynasties = [r[0] for r in conn.execute("SELECT DISTINCT dynasty FROM classics WHERE dynasty NOT IN ('','未知')")]
    categories = [r[0] for r in conn.execute("SELECT DISTINCT category FROM classics WHERE category NOT IN ('','未分类')")]
    rows = []
    seen = set()

    def add(work, kind, question, correct, pool, explanation):
        correct = clean_author(correct)
        if correct in BAD_AUTHORS:
            return
        pool = [clean_author(x) for x in pool if clean_author(x) not in BAD_AUTHORS and clean_author(x) != correct]
        if len(pool) < 3:
            return
        rng = _stable_random(work["id"] + kind)
        options = [correct] + rng.sample(pool, 3)
        rng.shuffle(options)
        qid = "qb_" + hashlib.sha1(f"{work['id']}|{kind}".encode("utf-8")).hexdigest()[:16]
        if qid in seen:
            return
        seen.add(qid)
        rows.append((
            qid, work["id"], work["category"] or "", work["dynasty"] or "", 1, "选择",
            question, json.dumps(options, ensure_ascii=False), options.index(correct), explanation, "识记",
        ))

    for work in works:
        author = clean_author(work["author"])
        if author not in BAD_AUTHORS:
            add(work, "author", f"《{work['title']}》的作者是谁？", author, authors,
                f"《{work['title']}》的作者是{author}。")
        if work["dynasty"] and work["dynasty"] != "未知":
            add(work, "dynasty", f"《{work['title']}》属于哪个朝代？", work["dynasty"], dynasties,
                f"《{work['title']}》属于{work['dynasty']}。")
        if work["category"]:
            add(work, "category", f"《{work['title']}》属于哪一分类？", work["category"], categories,
                f"《{work['title']}》属于{work['category']}。")

    conn.executemany(
        """INSERT OR REPLACE INTO question_bank
           (id,classic_id,category,dynasty,difficulty,type,question,options,answer,explanation,cognitive,source,verified)
           VALUES (?,?,?,?,?,?,?,?,?,?,?, 'rule',1)""",
        rows,
    )
    conn.commit()
    return len(rows)


def sample_bank(conn, category="", count=5):
    conn.row_factory = sqlite3.Row
    query = "SELECT * FROM question_bank WHERE verified=1"
    params = []
    if category:
        query += " AND category=?"
        params.append(category)
    query += " ORDER BY RANDOM() LIMIT ?"
    params.append(max(1, int(count)))
    rows = conn.execute(query, params).fetchall()
    questions = []
    for row in rows:
        try:
            options = json.loads(row["options"])
        except (TypeError, ValueError):
            continue
        questions.append({
            "type": row["type"], "question": row["question"], "options": options,
            "answer": int(row["answer"]), "explanation": row["explanation"],
            "id": row["id"], "classic_id": row["classic_id"],
            "cognitive": row["cognitive"] if "cognitive" in row.keys() else "识记",
            "rubric": row["rubric"] if "rubric" in row.keys() else "[]",
        })
    return questions


def bank_stats(conn):
    conn.row_factory = sqlite3.Row
    total = conn.execute("SELECT COUNT(*) FROM question_bank").fetchone()[0]
    by_cat = [dict(r) for r in conn.execute(
        "SELECT category,COUNT(*) n FROM question_bank GROUP BY category ORDER BY n DESC")]
    return {"total": total, "by_category": by_cat}
