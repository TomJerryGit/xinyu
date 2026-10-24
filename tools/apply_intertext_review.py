# -*- coding: utf-8 -*-
"""把互文批次的审核结果写回 resources/intertext.json。

用法：python tools/apply_intertext_review.py --batch 1 --apply
"""
import argparse
import csv
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(BASE, "resources", "intertext.json")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, default=1)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    csv_path = os.path.join(BASE, "docs", "reviews", f"intertext_batch{args.batch}_10.csv")
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8-sig", newline="")))
    payload = json.load(open(RES, encoding="utf-8"))
    links = payload.get("links", {})
    approved = rejected = 0
    for row in rows:
        status = (row.get("status") or "").strip().lower()
        if status not in ("approved", "rejected"):
            continue
        source = row.get("source_id")
        target = row.get("target_id")
        for link in links.get(source, []):
            if link.get("id") == target:
                if status == "approved":
                    link["review_status"] = "approved"
                    if row.get("relation"):
                        link["relation"] = row["relation"]
                    if row.get("reason"):
                        link["reason"] = row["reason"]
                    approved += 1
                else:
                    link["review_status"] = "rejected"
                    rejected += 1
                break
    if args.apply:
        json.dump(payload, open(RES, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(("applied" if args.apply else "would_apply"), "approved", approved, "rejected", rejected)


if __name__ == "__main__":
    main()
