# 第一批审核操作手册（20 篇 / 40 题）

> 目标：用 1 小时验证“审核是否可行”，不是一次审完 200 题。

## 一、材料

- 题目包：`docs/reviews/batch20_questions.csv`
- 同内容 JSONL：`docs/reviews/batch20_questions.jsonl`
- 互文第一批：`docs/reviews/intertext_batch1_10.csv`
- 统计命令：

```powershell
python tools/review_batch.py --stats
```

## 二、1 小时流程

| 时间 | 动作 |
|---|---|
| 0–5 分钟 | 读 Rubric，明确“通过/修改/拒绝”标准 |
| 5–55 分钟 | 审 40 题，平均 75 秒/题 |
| 55–60 分钟 | 统计通过率、修改率、平均耗时 |

### 用软件内审核控制台

数据管理 →「AI 审核队列」：

- 每题显示 **计时器**；
- 可直接修改题干、答案/译文、注释；
- 填写审核人与备注；
- 通过/拒绝后自动记录：
  - `review_minutes`
  - `edited`
  - `reviewer`
  - `notes`
- 顶部实时显示：已审、通过率、平均分钟/题、修改率。

CSV 方式仍然保留，适合离线批量审核。

### 每题填法

CSV 字段：

```text
decision       approved / rejected
reviewer       审核人
review_minutes 本题耗时（分钟，可小数）
edited         1=修改过，0=未修改
edited_question 修改后的题干（可空）
edited_answer   修改后的答案（可空）
notes          问题说明
```

### 判定标准

**通过**：

- 题干清楚，指向明确；
- 答案正确，能由原文支持；
- Rubric 可用于评分；
- 不是纯识记题（理解/分析目标）。

**修改后通过**：

- 题干有歧义；
- 答案有错字/表述问题；
- Rubric 维度不全。

**拒绝**：

- 答案错误；
- 文本依据不足；
- 题目与目标不符；
- 无法在 1 分钟内判断对错。

## 三、Go / No-Go

### 继续扩到 80 篇

- 40 题在 **≤60 分钟**内完成；
- 通过率 **≥70%**；
- 修改率 **≤30%**；
- 没有出现“无法判断答案”的题超过 5 道。

### 停止并改流程

- 40 题超过 90 分钟；
- 通过率低于 50%；
- 超过 10 题答案无法核实；
- 教师认为题目不可用于课堂。

## 四、互文校勘

每批 10 篇，约 20–30 分钟：

```text
intertext_batch1_10.csv
intertext_batch2_10.csv
intertext_batch3_10.csv
```

判定：

- `approved`：关系成立，理由准确；
- `rejected`：关系弱/错误；
- `notes`：改成“同意象/同主题/同典故”等更准确关系。

## 五、审核后

1. 先统计第一批：

```powershell
python tools/review_batch.py --stats
```

2. 只把 approved 的题通过数据管理 → AI 审核队列写入题库，或使用：

```powershell
python tools/apply_review_batch.py --apply
```

3. 互文按批次回写：

```powershell
python tools/apply_intertext_review.py --batch 1 --apply
```

4. 修改过的题，先在 CSV 里改好，再回写；
5. 不改代码，不继续生成新题，直到第一批数据出来。

## 六、当前状态

- 40 题：全部 `pending`
- 互文 140 条：全部 `pending`
- 人工通过：**0**

不要把 `pending` 说成“已完成”。
