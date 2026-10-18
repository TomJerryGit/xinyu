# -*- coding: utf-8 -*-
"""构建全量基础题库：python tools/build_question_bank.py --apply"""
import argparse
import os
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "classics.db")
sys.path.insert(0, BASE)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    from question_bank import build_bank
    from classics_database import ClassicsDatabase

    db = ClassicsDatabase(DB)
    conn = db.conn
    started = time.perf_counter()
    if args.apply:
        count = build_bank(conn, limit=args.limit, rebuild=args.rebuild)
    else:
        count = conn.execute("SELECT COUNT(*) FROM question_bank").fetchone()[0]
    print("question_bank", count, "seconds", round(time.perf_counter() - started, 2))
    conn.close()


if __name__ == "__main__":
    main()
