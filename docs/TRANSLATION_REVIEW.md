# 300 篇译文/注释草案与人工复核

## 当前状态

- 已选 **300 篇**：`data/reviews/translation_selected_300.jsonl`
- AI 草案：**109 篇成功**，191 篇因模型空返回/网络超时失败
- 草案状态：全部为 `pending`，**没有任何一篇被标成“已复核”**
- 复核表：`data/reviews/translation_review.csv`

> 这不是 300 篇成品。AI 只生成草案；没有人类复核就不能写入正式译文，也不能标 `verified`。
> 本轮不会把未复核内容冒充定稿。

## 为什么没到 300

DeepSeek 批量请求大量返回不完整 JSON 或空内容；单篇提示可成功，但并发/串行重试仍只有约 1/3 成功。
继续消耗 API 也不能保证质量，因此停在“可复核草案”阶段，而不是刷满 300 个低质结果。

## 人工复核流程

1. 打开 CSV：

```text
data/reviews/translation_review.csv
```

2. 对 `status=pending` 的行：
   - 核对 `translation` 是否忠实、无扩写；
   - 核对 `annotation` 的典故/难词是否准确；
   - 填 `reviewer`（复核人）；
   - 通过：`status=approved`；不通过：`status=rejected`；
   - 可直接修改 `translation`/`annotation` 列。

3. 回写数据库：

```powershell
python tools/review_translations.py --from-csv --apply
```

只有 `approved` 且有 `translation` 的行会写入；写入后：

- `translation_status='approved'`
- `annotation_status='approved'`（有注释时）
- `reviewed_by`、`reviewed_at` 记录

4. UI 详情页会显示“译文（已复核）”；草案阶段显示“AI 草案，待复核”。

## 重试失败项

```powershell
python tools/generate_translation_drafts.py --limit 300 --single --workers 1 --resume
```

`--resume` 只跳过 `pending`/`approved`，失败项会重试；成功后覆盖同 ID 的最后一条记录。

## 质量门禁

- 正文 `verified=1` 与译文 `translation_status=approved` 是两件事；
- 译文通过人工复核前，不进入“精选译文”；
- 后续先复核 100 篇，再扩大到 300，避免一次性放过错误。
