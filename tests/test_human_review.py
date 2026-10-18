# -*- coding: utf-8 -*-
"""人工评审表完整性测试。"""
from evals import review


def test_human_review_has_40_cases():
    rows = review.load()
    assert len(rows) == 40
    counts = {}
    for row in rows:
        counts[row["task"]] = counts.get(row["task"], 0) + 1
        assert row["status"] == "pending"
        assert row["score"] is None
    assert sorted(counts.values()) == [5] * 8
