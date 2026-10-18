# -*- coding: utf-8 -*-
"""从经典库生成 200 条评测用例（8 类任务 × 25 条）。

注意：这些是"可执行评测用例"，不等同于人工金标准；正式发布前需人工抽检
并逐步替换为人工标注的期望答案。
"""
import json
import os
import sqlite3
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

DB = os.path.join(BASE, "data", "classics.db")
OUT = os.path.join(BASE, "evals", "cases.jsonl")

TOPICS = [
    "秋夜", "江南", "边塞", "送别", "明月", "春雨", "登高", "归乡",
    "孤舟", "落花", "故人", "长江", "黄河", "青山", "白雪", "梅花",
    "竹林", "渔火", "钟声", "雁字", "斜阳", "流水", "夜雨", "早春", "寒江",
]

CLASSIFY_OPTIONS = [
    "经部", "史部", "子部", "集部", "蒙学", "唐诗",
    "宋词", "宋诗", "元曲", "经典散文", "论语", "诗经", "楚辞",
]

ANALYSIS_REQUIRED = ["background", "text_analysis", "artistic", "rhythm", "culture", "teaching"]


def fetch_poems(limit=25):
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, title, author, dynasty, category, content FROM classics "
        "WHERE length(content) >= 24 AND category IN ('唐诗','宋诗','宋词','元曲','诗经','楚辞') "
        "ORDER BY is_famous DESC, char_count DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def build():
    poems = fetch_poems(25)
    if len(poems) < 25:
        raise SystemExit(f"经典库不足 25 篇: {len(poems)}")
    cases = []

    for index, poem in enumerate(poems, 1):
        cases.append({
            "id": f"analysis_{index:03d}",
            "task": "analysis",
            "prompt": (
                f"请对《{poem['title']}》{poem['author']}进行六维深度赏析，只输出 JSON："
                '{"background":"","text_analysis":"","artistic":"","rhythm":"","culture":"","teaching":""}\n'
                f"原文：{poem['content'][:400]}"
            ),
            "required": ANALYSIS_REQUIRED,
            "rubric": ["引用原文", "六维完整", "无编造事实"],
        })

    for index, topic in enumerate(TOPICS, 1):
        cases.append({
            "id": f"creation_{index:03d}",
            "task": "creation",
            "prompt": f"写一首五言绝句，主题：{topic}。要求：平仄合规、意象凝练、禁止现代词汇。只输出诗。",
            "required": [],
            "rubric": ["四句", "每句五字", "无现代词汇", "有完整意境"],
        })

    for index, poem in enumerate(poems, 1):
        cases.append({
            "id": f"polish_{index:03d}",
            "task": "polish",
            "prompt": (
                "请为下面的诗句提供 1-6 个炼字建议，只输出 JSON："
                '{"suggestions":[{"original":"","replacements":["",""],"reason":""}]}\n'
                f"诗句：{poem['content'][:120]}"
            ),
            "required": ["suggestions"],
            "rubric": ["替换字合理", "理由具体", "不改变原意"],
        })

    for index, poem in enumerate(poems, 1):
        cases.append({
            "id": f"teaching_{index:03d}",
            "task": "teaching",
            "prompt": (
                f"请为《{poem['title']}》做逐句讲解与练习，只输出 JSON："
                '{"lines":[{"original":"","translation":"","keywords":"","rhetoric":"","structure":""}],'
                '"exercises":[{"type":"选择","question":"","options":["A","B","C","D"],"answer":0,"explanation":""}]}\n'
                f"原文：{poem['content'][:300]}"
            ),
            "required": ["lines", "exercises"],
            "rubric": ["逐句对应", "练习可作答", "解析准确"],
        })

    for index, poem in enumerate(poems, 1):
        cases.append({
            "id": f"quiz_{index:03d}",
            "task": "quiz",
            "prompt": (
                f"为《{poem['title']}》设计 3 道选择题，只输出 JSON："
                '{"questions":[{"type":"选择","question":"","options":["A","B","C","D"],"answer":0,"explanation":""}]}\n'
                f"原文：{poem['content'][:300]}"
            ),
            "required": ["questions"],
            "rubric": ["题干清晰", "选项不重复", "答案与解析一致"],
        })

    for index, poem in enumerate(poems, 1):
        cases.append({
            "id": f"translate_{index:03d}",
            "task": "translate",
            "prompt": f"请将下面的中文诗词翻译成英文，保留意境，只输出译文：\n{poem['content'][:200]}",
            "required": [],
            "rubric": ["英文完整", "保留意象", "无中文残留"],
        })

    for index, poem in enumerate(poems, 1):
        cases.append({
            "id": f"classify_{index:03d}",
            "task": "classify",
            "prompt": (
                "请把下面作品归入一个分类，只回复分类名："
                + "、".join(CLASSIFY_OPTIONS)
                + f"\n《{poem['title']}》{poem['content'][:200]}"
            ),
            "required": [],
            "rubric": ["分类在候选内", "与体裁/内容一致"],
        })

    for index, poem in enumerate(poems, 1):
        cases.append({
            "id": f"rhetoric_{index:03d}",
            "task": "rhetoric",
            "prompt": (
                "请分析下面诗句的对仗、典故与叠字，用 3 句话说明：\n"
                f"{poem['content'][:160]}"
            ),
            "required": [],
            "rubric": ["指出具体手法", "引用原文", "不空泛"],
        })

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as handle:
        for case in cases:
            handle.write(json.dumps(case, ensure_ascii=False) + "\n")
    print("cases:", len(cases), "->", OUT)


if __name__ == "__main__":
    build()
