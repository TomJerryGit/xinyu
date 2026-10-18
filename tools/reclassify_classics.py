# -*- coding: utf-8 -*-
"""把旧库中错放在“集部”的唐诗/宋词/元曲/诸子/蒙学重新归类，并统一作者繁简。

用法：python tools/reclassify_classics.py --apply
"""
import argparse
import json
import os
import sqlite3
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "classics.db")
REPORT = os.path.join(BASE, "data", "classics_reclassify_report.json")

SUB = {
    "唐诗": "集部/唐诗", "宋词": "集部/宋词", "宋诗": "集部/宋诗",
    "元曲": "集部/元曲", "楚辞": "集部/楚辞", "经典散文": "集部/古文",
    "经部": "经部", "子部": "子部/诸子", "史部": "史部/史传",
    "蒙学": "蒙学", "诗经": "经部/诗经", "论语": "经部/论语", "集部": "集部",
}
DYNASTY = {"唐诗": "唐", "宋词": "宋", "宋诗": "宋", "元曲": "元", "楚辞": "战国", "诗经": "先秦", "论语": "春秋"}
ZI_TITLES = {"《老子》", "《庄子》", "《孟子》", "《荀子》", "《韩非子》", "《墨子》", "《太平广记》", "《列子》", "《淮南子》", "老子", "庄子", "孟子", "荀子", "韩非子", "墨子", "列子", "淮南子"}
MENG_TITLES = {"千家诗", "训蒙诗", "训蒙绝句", "小学集注", "三字经", "百家姓", "千字文", "弟子规"}
YUAN_TITLES = {"西厢记·长亭送别", "琵琶记·糟糠自厌", "汉宫秋·梅花酒", "赵氏孤儿·煞尾", "赵氏孤儿·油葫芦", "窦娥冤·滚绣球", "高祖还乡·耍孩儿", "卖花声·怀古"}
TANG_TITLES = {"长恨歌", "琵琶行", "春江花月夜", "将进酒", "池上"}


def classify(row):
    title = row["title"] or ""
    dynasty = row["dynasty"] or ""
    category = row["category"] or ""
    if str(row["id"]).startswith("楚辞_"):
        return "楚辞"
    if title in ZI_TITLES:
        return "子部"
    if title == "五柳先生传":
        return "经典散文"
    if title in MENG_TITLES:
        return "蒙学"
    if title in YUAN_TITLES:
        return "元曲"
    if title in TANG_TITLES:
        return "唐诗"
    if category == "集部":
        if dynasty in ("唐", "唐代"):
            return "唐诗"
        if dynasty in ("宋", "宋代", "北宋", "南宋"):
            return "宋词" if "·" in title else "宋诗"
        if dynasty in ("元", "元代"):
            return "元曲"
        if title.endswith("赋") or title in ("赤壁赋",):
            return "经典散文"
    if category == "经典散文" and dynasty in ("近现代", "现代", "当代"):
        return "经典散文"
    return category


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        from opencc import OpenCC

        cc = OpenCC("t2s")
    except Exception:
        cc = None
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    if args.apply:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = DB + f".pre_reclassify_{stamp}.bak"
        target = sqlite3.connect(backup)
        conn.backup(target)
        target.close()
    rows = [dict(row) for row in conn.execute("SELECT id,title,author,dynasty,category,subcategory,content FROM classics")]
    changes = []
    for row in rows:
        new_category = classify(row)
        new_sub = SUB.get(new_category, row["subcategory"] or "")
        new_dynasty = row["dynasty"] or DYNASTY.get(new_category, "")
        if new_category == "经典散文" and row["dynasty"] in ("近现代", "现代", "当代"):
            new_sub = "现代散文"
        new_author = cc.convert(row["author"] or "") if cc else (row["author"] or "")
        if (new_category, new_sub, new_dynasty, new_author) != (row["category"], row["subcategory"], row["dynasty"], row["author"]):
            changes.append({"id": row["id"], "title": row["title"], "old": row["category"], "new": new_category})
            if args.apply:
                conn.execute(
                    "UPDATE classics SET category=?, subcategory=?, dynasty=?, author=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (new_category, new_sub, new_dynasty, new_author, row["id"]),
                )
    if args.apply:
        conn.commit()
    report = {"dry_run": not args.apply, "changes": len(changes), "sample": changes[:30]}
    with open(REPORT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    conn.close()


if __name__ == "__main__":
    main()
