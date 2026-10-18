# -*- coding: utf-8 -*-
"""导出随安装包分发的经典种子（只含 verified 数据）。"""
import json
import os
import sqlite3
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "classics.db")
OUT = os.path.join(BASE, "resources", "classics_seed.json")


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT id,title,author,dynasty,category,subcategory,content,translation,
                  annotation,tags,source,char_count,is_famous,difficulty_level,verified
           FROM classics WHERE length(trim(content))>=8
           ORDER BY verified DESC, category, is_famous DESC, char_count DESC"""
    ).fetchall()
    conn.close()
    records = [dict(row) for row in rows]
    payload = {
        "version": 2,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "count": len(records),
        "records": records,
    }
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    print("seed:", len(records), "->", OUT, "size_mb=", round(os.path.getsize(OUT) / 1024 / 1024, 2))


if __name__ == "__main__":
    main()
