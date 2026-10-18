# -*- coding: utf-8 -*-
"""从 200 条用例中抽 40 条做人工评审表（每类 5 条，固定随机种子）。"""
import json
import os
import random

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES = os.path.join(BASE, "evals", "cases.jsonl")
OUT = os.path.join(BASE, "evals", "human_review.jsonl")
TASKS = ["analysis", "creation", "polish", "teaching", "quiz", "translate", "classify", "rhetoric"]


def main():
    rows = [json.loads(line) for line in open(CASES, encoding="utf-8") if line.strip()]
    rng = random.Random(42)
    selected = []
    for task in TASKS:
        pool = [row for row in rows if row["task"] == task]
        selected.extend(rng.sample(pool, min(5, len(pool))))
    with open(OUT, "w", encoding="utf-8") as handle:
        for row in selected:
            handle.write(json.dumps({
                "id": row["id"],
                "task": row["task"],
                "prompt": row["prompt"],
                "rubric": row.get("rubric", []),
                "output": "",
                "score": None,
                "reviewer": "",
                "notes": "",
                "status": "pending",
            }, ensure_ascii=False) + "\n")
    print("human review:", len(selected), "->", OUT)


if __name__ == "__main__":
    main()
