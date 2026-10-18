# 心语 AI 评测集

## 结构

- `cases.jsonl`：200 条用例，8 类任务 × 25 条：
  analysis / creation / polish / teaching / quiz / translate / classify / rhetoric。
- `run_eval.py`：执行器，支持 mock 与 live。
- `results/latest.json`：最近一次结果。

## 用法

```bash
# 自检评测链路（不联网）
python evals/run_eval.py

# 真实模型，前 10 条
python evals/run_eval.py --live --limit 10

# 全量（会消耗额度）
python evals/run_eval.py --live
```

## 重要说明

当前用例是**可执行评测用例**，不是人工金标准：

- 结构校验能发现 JSON 失败、缺字段、格式跑偏；
- 质量评分（准确性、风格、教学可用性）仍需人工抽检与 LLM 评审；
- 正式发布前建议每类抽 20% 人工打分，并把历史最佳输出固化为回归基线。

## 发布门禁建议

- mock 评测必须 100%；
- live 评测分数不得低于上一版本基线；
- 出现 P0 安全用例失败（违法、侵权、严重事实错误）直接阻断发布。

```bash
# 首次建立基线
python evals/run_eval.py --live --update-baseline

# 之后每次发布前对比基线（默认容差 2%）
python evals/run_eval.py --live --baseline evals/baseline.json
```

`--baseline` 对比是分数门禁，不替代人工评审。

## 人工评审（40 条）

```bash
python tools/make_human_review.py       # 固定抽 40 条，生成空评审表
python evals/review.py list             # 查看
python evals/review.py score --id analysis_021 --score 4 --output "模型输出..." --notes "..." --reviewer "张三"
python evals/review.py report           # 40 条未全部完成时返回非 0
```

评审表默认 40 条全部为 `pending`、`score=null`。**必须由人工阅读输出后打分**，
AI 生成的分数不能称为人工金标准。建议 1=不可用，3=可用但有明显问题，5=可直接发布。
