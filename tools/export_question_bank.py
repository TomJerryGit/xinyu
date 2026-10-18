# -*- coding: utf-8 -*-
"""导出按分类题库到 resources/question_bank/*.json，供安装包预置。"""
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "classics.db")
sys.path.insert(0, BASE)


def main():
    from classics_database import ClassicsDatabase
    from question_bank import export_prebuilt

    db = ClassicsDatabase(DB)
    total = export_prebuilt(db.conn)
    print("total", total)
    db.conn.close()


if __name__ == "__main__":
    main()
