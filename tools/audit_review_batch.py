# -*- coding: utf-8 -*-
"""对第一批 40 题做机器预检；只标记问题，不做审核决定。"""
import csv
import json
import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "docs", "reviews", "batch20_questions.jsonl")
OUT_CSV = os.path.join(BASE, "docs", "reviews", "batch20_precheck.csv")
OUT_MD = os.path.join(BASE, "docs", "reviews", "batch20_precheck.md")

EN = re.compile(r"[A-Za-z]{2,}")


def flags_for(row, seen):
    flags = []
    answer = row.get("answer", "") or ""
    question = row.get("question", "") or ""
    if EN.search(answer):
        flags.append("答案含英文/未翻译")
    if EN.search(question):
        flags.append("题干含英文")
    if len(answer.strip()) < 25:
        flags.append("答案过短")
    if answer.strip().startswith("参考"):
        flags.append("答案疑似占位")
    if "??" in answer or "�" in answer:
        flags.append("答案乱码")
    if question.startswith("结合原文，用自己的话概括") or "表达了怎样的情感或主旨？结合原文" in question:
        flags.append("模板化题干")
    if question in seen:
        flags.append("题干重复")
    seen.add(question)
    rubric = row.get("rubric", [])
    try:
        points = sum(int(x.get("points", 0)) for x in rubric)
    except Exception:
        points = 0
    if points != 100:
        flags.append(f"Rubric分数={points}")
    return flags


def main():
    rows = []
    for line in open(SRC, encoding="utf-8"):
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    seen = set()
    report = []
    for row in rows:
        flags = flags_for(row, seen)
        report.append({
            "queue_id": row.get("queue_id", ""), "classic_id": row.get("classic_id", ""),
            "title": row.get("title", ""), "cognitive": row.get("cognitive", ""),
            "question": row.get("question", ""), "flags": "；".join(flags) or "无明显机器问题",
            "suggested": "先修再审" if flags else "可优先人工审",
        })
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=report[0].keys())
        writer.writeheader()
        writer.writerows(report)
    flagged = [r for r in report if r["flags"] != "无明显机器问题"]
    with open(OUT_MD, "w", encoding="utf-8") as handle:
        handle.write("# 第一批 40 题机器预检\n\n")
        handle.write("> 预检只标记问题，不构成人工通过。\n\n")
        handle.write(f"- 总题数：{len(report)}\n")
        handle.write(f"- 有机器问题：{len(flagged)}\n")
        handle.write(f"- 可优先人工审：{len(report) - len(flagged)}\n\n")
        handle.write("## 问题题\n\n")
        for row in flagged:
            handle.write(f"- {row['title']} / {row['cognitive']} / `{row['queue_id']}`：{row['flags']}\n")
    print("questions", len(report), "flagged", len(flagged))


if __name__ == "__main__":
    main()
