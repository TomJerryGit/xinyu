# 内容校勘与审核状态

> 本文件区分“已生成草案”与“已完成人工校勘”。当前没有把草案冒充成品。

## 一、100 篇阅读题

### 第一批 20 篇 / 40 题

已切出可计时审核包：

- `docs/reviews/batch20_curated.jsonl`（逐篇命制题）
- `docs/reviews/batch20_questions.csv`
- `docs/reviews/batch20_precheck.md`（机器预检）
- 统计：`python tools/review_batch.py --stats`
- 回写：`python tools/apply_review_batch.py --apply`

状态：**40 题已重置为 pending（之前点击通过不计入实质审核）。**

这 40 题不是“概括主要内容/表达什么情感”的模板题，而是按每篇原文命制的具体题（如“疑”的释义、动作顺序、以声衬静、典故作用等）。机器预检 0 条硬错误，但仍需教师逐题确认。

| 项目 | 数量 |
|---|---:|
| 名篇 | 20 |
| 理解题 | 20 |
| 分析题 | 20 |
| 合计 | **40** |
| 软件 approved | **0** |
| 实质人工审核 | **0** |

### 完整 100 篇

| 项目 | 数量 |
|---|---:|
| 名篇 | 100 |
| 理解题草案 | 100 |
| 分析题草案 | 100 |
| 合计 | **200 道** |
| 软件 approved | **0**（点击结果已全部重置） |
| 实质人工审核 | **0** |
| 当前待审 | **188** |

来源：

- 100 篇已有 AI 译文/注释草案的名篇；
- 理解题参考答案来自译文草案；
- 分析题参考答案来自注释草案；
- 全部标 `draft`，进入 `ai_review_queue`。

文件：

```text
data/reviews/reading_questions_100.jsonl
```

**注意**：这不是 200 道高质量成品题。译文/注释本身尚未人工复核，题目只是可审核草稿。

## 二、统一审核队列

`ai_review_queue` 当前待审核：

| 类型 | 数量 | 说明 |
|---|---:|---|
| `reading_question` | 188 | 40 道逐篇命制 + 148 道旧题 |
| `translation_draft` | 114 | 20 篇古文新译文 + 94 条旧点击通过已回退 |
| `teaching_plan` | 1 | AI 教案 |
| 合计 | **303** | 全部待人工审核 |

审核入口：数据管理 →「AI 审核队列」。

审核控制台支持：

- 单题计时；
- 修改题干/答案/译文/注释；
- 通过/拒绝；
- 自动记录耗时、是否修改、审核人；
- 实时统计通过率、平均耗时、修改率。

CSV 入口仍保留，适合离线批量审核。

通过后的落库行为：

- `translation_draft` → 写入作品译文/注释，状态 `approved`；
- `reading_question` / `quiz_question` → 写入 `question_bank`，`source=reviewed`；
- 审核通过的阅读题会进入能力卷/综合卷的开放题池。

## 三、互文关系

| 项目 | 数量 |
|---|---:|
| 名篇 | 30 |
| 机器关系 | 140 |
| 人工校勘通过 | **0** |

文件：

```text
data/reviews/intertext_30_review.csv
docs/reviews/intertext_batch1_10.csv
docs/reviews/intertext_batch2_10.csv
docs/reviews/intertext_batch3_10.csv
```

回写：

```powershell
python tools/apply_intertext_review.py --batch 1 --apply
```

当前 UI 标记「待校勘」。CSV 列：

```text
source_id, source_title, target_id, target_title,
relation, reason, status, reviewer, notes
```

需要人工逐条确认：

- 同作者是否真的可比；
- 同分类是否只是分类巧合；
- 是否应改为“同意象/同主题/同典故”；
- 是否删除弱关系。

## 四、真实班级试点

文件：`docs/PILOT_KIT.md`

状态：**材料已准备，尚未进入学校**。

未完成：

- 学校招募
- 家长/学生告知
- 4 周课堂执行
- 教师访谈、学生问卷
- 基于数据的 V10 优先级调整

## 五、完成标准

### 100 篇阅读题

- 200 道全部有人工 `approved/rejected`；
- 因元曲精简，56 道旧通用题已移除，保留 144 道待审；
- 40 道逐篇命制题是第一批重点；
- 通过的题进入能力卷；
- 至少 80 道可用于真实课堂。

### 互文

- 30 篇 × 3–5 条关系全部人工确认；
- 弱关系删除；
- UI 不再显示「待校勘」。

### 班级试点

- 1 个班完成 4 周；
- 教师愿意第二次使用；
- 开放题可按 Rubric 批改；
- 形成一页改进清单。

## 六、当前结论

**内容生产已完成“可审核的草案”，尚未完成“人工校勘”。**

下一步不是继续生成，而是：

1. 先审核 20 篇（40 题），验证审核效率；
2. 再批量审核剩余 80 篇；
3. 同步校勘 30 篇互文；
4. 带 1 个班试点能力卷 + Rubric。
