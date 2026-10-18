# -*- coding: utf-8 -*-
"""人工评审表：查看、打分、汇总。

评审表是空的；必须由人工阅读 prompt/output 后填写 1-5 分。
AI 不能代替“人工金标准”。
"""
import argparse
import json
import os
from collections import defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(BASE, "evals", "human_review.jsonl")


def load():
    if not os.path.exists(PATH):
        return []
    return [json.loads(line) for line in open(PATH, encoding="utf-8") if line.strip()]


def save(rows):
    temp = PATH + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(temp, PATH)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    score = sub.add_parser("score")
    score.add_argument("--id", required=True)
    score.add_argument("--score", type=int, choices=range(1, 6), required=True)
    score.add_argument("--notes", default="")
    score.add_argument("--reviewer", default="")
    score.add_argument("--output", default="")
    report = sub.add_parser("report")
    report.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()

    rows = load()
    if args.command == "list":
        for row in rows:
            print(row["id"], row["task"], row.get("status"), row.get("score"), row["prompt"][:60].replace("\n", " "))
        print("total", len(rows), "reviewed", sum(1 for row in rows if row.get("score")))
        return 0
    if args.command == "score":
        for row in rows:
            if row["id"] == args.id:
                row["score"] = args.score
                row["notes"] = args.notes
                row["reviewer"] = args.reviewer
                row["status"] = "reviewed"
                if args.output:
                    row["output"] = args.output
                save(rows)
                print("scored", args.id, args.score)
                return 0
        print("not found", args.id)
        return 1
    reviewed = [row for row in rows if row.get("score")]
    by_task = defaultdict(list)
    for row in reviewed:
        by_task[row["task"]].append(row["score"])
    print(json.dumps({
        "total": len(rows),
        "reviewed": len(reviewed),
        "average": round(sum(row["score"] for row in reviewed) / len(reviewed), 2) if reviewed else 0,
        "by_task": {task: round(sum(vals) / len(vals), 2) for task, vals in sorted(by_task.items())},
    }, ensure_ascii=False, indent=2))
    if len(reviewed) < len(rows) and not args.allow_partial:
        print("未完成：仍有未评审用例")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
