# -*- coding: utf-8 -*-
"""内容结构整理：精简元曲、归位古文、补充教材名篇。

用法：
    python tools/curate_content.py           # 只看计划
    python tools/curate_content.py --apply   # 备份后执行
"""
import argparse
import json
import os
import shutil
import sqlite3

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "classics.db")
PROSE = os.path.join(BASE, "resources", "curated_prose.json")
ARCHIVE_DIR = os.path.join(BASE, "data", "archive")

MASTER_AUTHORS = [
    "关汉卿", "马致远", "白朴", "王实甫", "郑光祖", "乔吉", "张可久", "张养浩",
    "睢景臣", "徐再思", "贯云石", "卢挚", "姚燧", "王和卿", "胡祗遹", "盍西村",
    "杨果", "商挺", "杜仁杰", "杨朝英", "周德清", "钟嗣成", "赵孟頫", "邓玉宾",
    "查德卿", "吴西逸", "孙周卿", "赵显宏", "李致远", "薛昂夫", "曹德", "王晔",
    "汪元亨", "刘时中", "鲜于必仁", "陈草庵", "张弘范", "伯颜", "奥敦周卿",
    "王恽", "刘因", "倪瓒", "顾德润", "钱霖", "杨维桢",
]

FAMOUS_TITLE_WORDS = [
    "天净沙", "山坡羊", "卖花声", "水仙子", "折桂令", "人月圆", "殿前欢",
    "清江引", "普天乐", "塞鸿秋", "醉太平", "朝天子", "四块玉", "沉醉东风",
    "一半儿", "阳春曲", "凭阑人", "小桃红", "潘妃曲", "耍孩儿", "哨遍",
    "梧桐雨", "西厢记", "窦娥冤", "汉宫秋", "倩女离魂", "墙头马上",
    "赵氏孤儿", "单刀会", "救风尘", "望江亭", "李逵负荆", "陈州粜米",
    "看钱奴", "秋胡戏妻", "货郎旦", "魔合罗", "铁拐李", "竹叶舟",
    "黄粱梦", "岳阳楼", "陈抟高卧", "任风子", "荐福碑", "青衫泪",
    "雁儿落", "得胜令", "喜春来", "梧叶儿", "红绣鞋", "寄生草",
    "寿阳曲", "蟾宫曲", "醉高歌",
]

RECLASSIFY = {
    "adv_99769": "五柳先生传", "ext_fbfadc684bdb": "兰亭集序",
    "ext_e047e0f49e3f": "北山移文", "ext_e538e8c62a3c": "归去来兮辞",
    "ext_f8bc2c00e5da": "桃花源记", "ext_ed1d4b53123d": "谏太宗十思疏",
    "ext_0f7d2e8edbc4": "陈情表", "hanfu_001": "归田赋",
    "shi_002": "史记·项羽本纪（节选）", "shi_003": "资治通鉴·赤壁之战（节选）",
    "cur_ec0874977e79": "劝学（节选）", "zhuzi_002": "鱼我所欲也",
    "adv_52558": "狼", "adv_36929": "赤壁赋", "adv_79921": "伤仲永",
    "adv_19198": "山市",
}

KEEP_YUANQU = 600


def title_priority(title):
    for i, word in enumerate(FAMOUS_TITLE_WORDS):
        if word in title:
            return i
    return 9999


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    before = dict(conn.execute("SELECT category,COUNT(*) n FROM classics GROUP BY category").fetchall())

    rows = [dict(r) for r in conn.execute(
        "SELECT id,title,author,category,char_count,verified,is_famous FROM classics WHERE category='元曲'"
    )]
    # 1. 名句/名篇优先，最多 150 条，避免“曲牌名”把范围放大
    keep = {}
    famous = sorted(
        [r for r in rows if title_priority(r["title"]) < 9999],
        key=lambda x: (title_priority(x["title"]), x["char_count"] or 0),
    )
    for row in famous[:150]:
        keep[row["id"]] = (0, title_priority(row["title"]), row["char_count"] or 0)
    # 2. 代表作家，每人先保留 12 首
    by_author = {}
    for row in rows:
        if row["id"] in keep:
            continue
        if row["author"] in MASTER_AUTHORS:
            by_author.setdefault(row["author"], []).append(row)
    for author, items in by_author.items():
        items.sort(key=lambda x: (title_priority(x["title"]), x["char_count"] or 0))
        for row in items[:12]:
            keep[row["id"]] = (1, title_priority(row["title"]), row["char_count"] or 0)
    # 3. 代表作家其余作品中补齐
    if len(keep) < KEEP_YUANQU:
        rest = sorted(
            [r for r in rows if r["id"] not in keep and r["author"] in MASTER_AUTHORS],
            key=lambda x: (title_priority(x["title"]), x["char_count"] or 0),
        )
        for row in rest:
            keep[row["id"]] = (2, title_priority(row["title"]), row["char_count"] or 0)
            if len(keep) >= KEEP_YUANQU:
                break
    # 4. 极端情况下从非无名氏补齐
    if len(keep) < KEEP_YUANQU:
        rest = sorted(
            [r for r in rows if r["id"] not in keep and r["author"] != "无名氏"],
            key=lambda x: (x["char_count"] or 0),
        )
        for row in rest:
            keep[row["id"]] = (3, 9999, row["char_count"] or 0)
            if len(keep) >= KEEP_YUANQU:
                break
    keep_ids = set(keep.keys())
    removed = [r for r in rows if r["id"] not in keep_ids]
    print("yuanqu_before", len(rows), "keep", len(keep_ids), "remove", len(removed))
    print("yesterday_keep_authors", len({r["author"] for r in rows if r["id"] in keep_ids}))

    prose = json.load(open(PROSE, encoding="utf-8"))
    print("prose_supplement", len(prose), "reclassify", len(RECLASSIFY))
    if not args.apply:
        print("dry-run only")
        return

    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    backup = DB + ".before_curation"
    if not os.path.exists(backup):
        shutil.copy2(DB, backup)
    with open(os.path.join(ARCHIVE_DIR, "yuanqu_removed.jsonl"), "w", encoding="utf-8") as handle:
        for row in removed:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    conn.execute("CREATE TEMP TABLE keep_yuanqu (id TEXT PRIMARY KEY)")
    conn.executemany("INSERT OR IGNORE INTO keep_yuanqu(id) VALUES (?)", [(x,) for x in keep_ids])
    conn.execute("DELETE FROM classics WHERE category='元曲' AND id NOT IN (SELECT id FROM keep_yuanqu)")
    conn.execute("DROP TABLE keep_yuanqu")

    # 归位被错分的古文
    for cid in RECLASSIFY:
        conn.execute(
            "UPDATE classics SET category='经典散文', verified=1 WHERE id=?",
            (cid,),
        )
    # 去重：同题同作者保留信息更全的一条
    dups = conn.execute(
        """SELECT title,author,COUNT(*) n FROM classics WHERE category='经典散文'
           GROUP BY title,author HAVING n>1"""
    ).fetchall()
    for title, author, _ in dups:
        items = conn.execute(
            "SELECT id,verified,is_famous,length(content) n FROM classics WHERE category='经典散文' AND title=? AND author=? ORDER BY verified DESC,is_famous DESC,n DESC",
            (title, author),
        ).fetchall()
        for row in items[1:]:
            conn.execute("DELETE FROM classics WHERE id=?", (row["id"],))

    # 补充教材名篇
    inserted = 0
    for item in prose:
        exists = conn.execute(
            "SELECT 1 FROM classics WHERE title=? AND author=?", (item["title"], item["author"])
        ).fetchone()
        if exists:
            continue
        conn.execute(
            """INSERT OR REPLACE INTO classics
               (id,title,author,dynasty,category,subcategory,content,translation,annotation,tags,source,
                char_count,is_famous,difficulty_level,verified)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (item["id"], item["title"], item["author"], item.get("dynasty", "未知"),
             item.get("category", "经典散文"), item.get("subcategory", ""), item["content"], "",
             item.get("annotation", ""), "", item.get("source", "curated_2026"),
             len(item["content"]), int(item.get("is_famous", 1)), int(item.get("difficulty_level", 2)),
             int(item.get("verified", 1))),
        )
        inserted += 1

    # 清理派生数据中的孤儿
    for table, col in (
        ("question_bank", "classic_id"), ("teaching_plans", "classic_id"),
        ("teaching_plan_versions", "classic_id"), ("ai_review_queue", "classic_id"),
        ("reading_history", "classic_id"), ("user_notes", "classic_id"),
    ):
        try:
            conn.execute(f"DELETE FROM {table} WHERE {col} NOT IN (SELECT id FROM classics)")
        except sqlite3.Error:
            pass
    conn.commit()
    after = dict(conn.execute("SELECT category,COUNT(*) n FROM classics GROUP BY category").fetchall())
    print("inserted_prose", inserted)
    print("before", before)
    print("after", after)
    print("total", conn.execute("SELECT COUNT(*) FROM classics").fetchone()[0])
    print("archive", os.path.join(ARCHIVE_DIR, "yuanqu_removed.jsonl"))
    conn.close()


if __name__ == "__main__":
    main()
