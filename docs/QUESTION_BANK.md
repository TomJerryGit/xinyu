# 基础题库与组卷

## 当前规模

本地 `data/classics.db` 已生成：

| 项目 | 数量 |
|---|---:|
| 基础题 | **10,513 道** |
| 题型 | 作者选择、朝代选择、分类选择 |
| 来源 | `rule`（规则生成，无 AI） |
| 校勘 | `verified=1` |

分类分布前列：

- 唐诗 3,539
- 宋词 2,988
- 元曲 1,699
- 经典散文 689
- 蒙学 679
- 诗经 610

## 表结构

```sql
question_bank(
  id, classic_id, category, dynasty, difficulty, type,
  question, options, answer, explanation, source, verified, created_at
)
```

## 组卷优先级

`generate_quiz(category, difficulty, count, types, blueprint)`：

1. `types == 选择` 且难度 1：
   - **基础卷**：本地题库 100%；
   - **能力卷/综合卷**：本地题库 + 教案开放题（带 Rubric，不自动判分）；
2. 题库不足：回退现有规则；
3. 只有显式选择 `新题（AI）` 或 `鉴赏题（AI）`：调用 AI；
4. 结果按分类/题量/蓝图缓存。

UI 会显示：

```text
组卷来源：本地题库 / 本地题库 + Rubric / AI/规则
```

## 认知标签与 Rubric

- 题库题目带 `cognitive`：当前基础题为「识记」；
- 能力卷/综合卷追加「简答」题，带三维量规：
  - 内容理解 40
  - 分析深度 40
  - 语言表达 20
- 开放题 `auto_gradable=false`，提交后显示「待教师按量规评分」，不进入错题本。


## 命令

```powershell
# 全量构建（本地）
python tools/build_question_bank.py --apply

# 重建
python tools/build_question_bank.py --apply --rebuild
```

安装包不带 10,513 道题（避免安装包膨胀）；首次在某分类组卷时按分类懒构建，
只生成该分类的题，通常不到 1 秒；之后直接查库。

## 质量边界

- 这些是**基础题**，不是鉴赏题；
- 规则题答案确定，但题干模板化；
- 鉴赏/开放题必须由 AI 生成并人工复核；
- 题库题目前不带“名篇优先”排序，后续可加 `is_famous` 权重。
