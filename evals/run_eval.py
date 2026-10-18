# -*- coding: utf-8 -*-
"""评测执行器。

用法：
    python evals/run_eval.py                 # mock，自检评测链路
    python evals/run_eval.py --live --limit 10
    python evals/run_eval.py --live          # 全量 200 条（会消耗模型额度）

评分是启发式 + 结构校验；正式发布建议叠加人工评分与 LLM 评审。
"""
import argparse
import json
import os
import sys
from collections import defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from json_utils import parse_json_object  # noqa: E402

CASES = os.path.join(BASE, "evals", "cases.jsonl")
RESULTS = os.path.join(BASE, "evals", "results", "latest.json")

BANNED = ("手机", "微信", "APP", "OK", "打卡", "流量", "互联网")

MOCK_RESPONSES = {
    "analysis": json.dumps({
        "background": "盛唐时期，诗人客居他乡。",
        "text_analysis": "以月光与霜色写思乡，语言凝练。",
        "artistic": "清冷、安静、含蓄。",
        "rhythm": "五言绝句，平仄基本合规。",
        "culture": "中秋与望月思乡的传统意象。",
        "teaching": "可引导学生找出诗中的视觉与触觉意象。",
    }, ensure_ascii=False),
    "creation": "空山新雨后，\n天气晚来秋。\n明月松间照，\n清泉石上流。",
    "polish": json.dumps({"suggestions": [
        {"original": "照", "replacements": ["映", "泻"], "reason": "更有动态与光泽"},
        {"original": "流", "replacements": ["鸣", "咽"], "reason": "增加声音层次"},
    ]}, ensure_ascii=False),
    "teaching": json.dumps({
        "lines": [{"original": "床前明月光", "translation": "床前洒满月光", "keywords": "明月", "rhetoric": "借景抒情", "structure": "起句"}],
        "exercises": [{"type": "选择", "question": "诗中写的是什么？", "options": ["月光", "雪", "雨", "风"], "answer": 0, "explanation": "首句写月光"}],
    }, ensure_ascii=False),
    "quiz": json.dumps({
        "questions": [{"type": "选择", "question": "作者是谁？", "options": ["李白", "杜甫", "王维", "苏轼"], "answer": 0, "explanation": "《静夜思》为李白所作。"}],
    }, ensure_ascii=False),
    "translate": "Before my bed the silver moonlight glows; I wonder if it is frost on the ground.",
    "classify": "唐诗",
    "rhetoric": "首句以月光与霜色对举，形成视觉对照；'举头'与'低头'构成动作对仗；全诗以叠字式的回环写思乡。",
}


def load_cases(limit=None):
    cases = []
    with open(CASES, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases[:limit] if limit else cases


def score_case(case, output):
    task = case["task"]
    required = case.get("required") or []
    if not output:
        return False, "空输出"
    if task in ("analysis", "polish", "teaching", "quiz"):
        data = parse_json_object(output, {})
        for key in required:
            if key not in data or data[key] in (None, "", [], {}):
                return False, f"缺少字段 {key}"
        return True, "结构完整"
    if task == "creation":
        if len(output) < 12:
            return False, "过短"
        if any(word in output for word in BANNED):
            return False, "含现代词汇"
        lines = [line for line in output.splitlines() if line.strip()]
        if len(lines) != 4:
            return False, "不是四句"
        return True, "四句完整"
    if task == "translate":
        letters = sum(1 for char in output if char.isascii() and char.isalpha())
        if letters < 20:
            return False, "英文过短"
        if any("\u4e00" <= char <= "\u9fff" for char in output):
            return False, "含中文残留"
        return True, "英文完整"
    if task == "classify":
        allowed = {"经部", "史部", "子部", "集部", "蒙学", "唐诗", "宋词", "宋诗", "元曲", "经典散文", "论语", "诗经", "楚辞"}
        return (output.strip() in allowed), "分类合法" if output.strip() in allowed else "分类不在候选内"
    if task == "rhetoric":
        return (len(output) >= 20), "有具体分析" if len(output) >= 20 else "分析过短"
    return True, "未定义任务"


def run(cases, generator, threshold=0.8):
    stats = defaultdict(lambda: {"total": 0, "passed": 0})
    failures = []
    for case in cases:
        output = generator(case)
        ok, reason = score_case(case, output)
        stats[case["task"]]["total"] += 1
        if ok:
            stats[case["task"]]["passed"] += 1
        else:
            failures.append({"id": case["id"], "task": case["task"], "reason": reason, "output": str(output)[:200]})
    total = sum(item["total"] for item in stats.values())
    passed = sum(item["passed"] for item in stats.values())
    score = passed / total if total else 0
    result = {
        "cases": total,
        "passed": passed,
        "score": round(score, 4),
        "threshold": threshold,
        "by_task": {
            task: {"total": item["total"], "passed": item["passed"], "score": round(item["passed"] / item["total"], 3)}
            for task, item in sorted(stats.items())
        },
        "failures": failures[:20],
    }
    os.makedirs(os.path.dirname(RESULTS), exist_ok=True)
    with open(RESULTS, "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps({key: result[key] for key in ("cases", "passed", "score", "by_task")}, ensure_ascii=False, indent=2))
    if failures:
        print("样例失败：", json.dumps(failures[:3], ensure_ascii=False, indent=2))
    return result


def live_generator():
    from api import API

    api = API()

    def generate(case):
        try:
            return api.ai.generate(case["task"], case["prompt"], ttl=0)
        except Exception as exc:  # noqa: BLE001
            return f"ERROR: {exc}"

    generate.close = api.close  # type: ignore[attr-defined]
    return generate, api


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--threshold", type=float, default=0.8)
    parser.add_argument("--baseline", default=os.path.join(BASE, "evals", "baseline.json"))
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--tolerance", type=float, default=0.02)
    args = parser.parse_args()
    cases = load_cases(args.limit or None)
    if args.live:
        generator, api = live_generator()
        try:
            result = run(cases, generator, threshold=args.threshold)
        finally:
            api.close()
    else:
        result = run(cases, lambda case: MOCK_RESPONSES.get(case["task"], ""), threshold=args.threshold)

    baseline = {}
    if os.path.exists(args.baseline):
        try:
            with open(args.baseline, "r", encoding="utf-8") as handle:
                baseline = json.load(handle)
        except ValueError:
            baseline = {}
    if baseline and result["score"] + args.tolerance < float(baseline.get("score", 0)):
        print(f"评测回退：{result['score']} < baseline {baseline.get('score')}（容差 {args.tolerance}）")
        return 1
    if args.update_baseline:
        with open(args.baseline, "w", encoding="utf-8") as handle:
            json.dump(
                {"score": result["score"], "cases": result["cases"], "at": __import__("time").strftime("%Y-%m-%d %H:%M:%S")},
                handle,
                ensure_ascii=False,
                indent=2,
            )
        print("baseline updated:", args.baseline)
    return 0 if result["score"] >= result["threshold"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
