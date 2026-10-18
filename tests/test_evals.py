# -*- coding: utf-8 -*-
"""评测集完整性测试。"""
from evals.run_eval import MOCK_RESPONSES, load_cases, run


def test_eval_cases_are_200():
    cases = load_cases()
    assert len(cases) == 200
    tasks = {case["task"] for case in cases}
    assert tasks == {
        "analysis", "creation", "polish", "teaching",
        "quiz", "translate", "classify", "rhetoric",
    }


def test_eval_mock_passes_threshold():
    cases = load_cases()
    result = run(cases, lambda case: MOCK_RESPONSES.get(case["task"], ""))
    assert result["score"] == 1.0
