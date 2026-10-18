# 阶段 1 验收（V9.3.0）

## 交付

| 能力 | 入口 | 验证 |
|---|---|---|
| 启动打点 | `perf.py`、`data/perf/startup_latest.json` | 源码 3.24s 打点；打包可见 6.1s |
| 作业系统 | `jobs.py`、`submit_job/get_job/cancel_job/retry_job` | 完成/失败/取消/重试/断点续跑单测；教学、扩充接入 checkpoint |
| Tauri spike | `sidecar_server.py`、`static/js/web_shim.js`、`spike/tauri/` | 已编译；窗口 **0.56–2.7s**；嵌入式 sidecar 内部 **0.56s**；NSIS 18.7MB 安装包已验证 |
| 产品口径 | 文档/README | **splash 秒开，内容 4–7s 可用**，不再追求完整 <3s |
| 人工评审 | `evals/human_review.jsonl`、`evals/review.py` | 40 条（8×5）空评审表；需人工填写 1-5 分 |
| AI Gateway | `ai_gateway.py` | 所有 `generate` 调用统一走 Gateway；预算熔断、JSON 修复、缓存；单测 |
| 评测集 | `evals/cases.jsonl`、`evals/run_eval.py` | 200 条，mock 200/200 |
| 签名更新 | `updater.py`、`tools/sign_manifest.py` | Ed25519/SHA256/灰度单测 |
| 可观测性 | `metrics.py`、数据页「运行指标」 | 启动/AI/崩溃/作业指标 |

## 实测

- `pytest`：41 项通过（阶段 1 新增作业、Gateway、签名、评测、重试/断点、UI 状态）。
- `python evals/run_eval.py`：200/200，score 1.0（mock）。
- GUI 验收：8 个导航、1,058 篇、18 张卡片、7 个分页、7 个备份、搜索 39 篇、
  详情 7 个操作、命令面板 16 项，全部通过；新增全标签页审计。
- UI 审计：创作 27 字结果、赏析 95 字、教学背景/逐句、题库 202 字、
  运行指标 9 格、AI 预算 4 格、隐私文档 587 字，均通过。
- 打包：`dist/Xinyu/Xinyu.exe`（9.57 MB），onedir 目录约 100 MB。
- 启动：打点 3.23s；实际窗口可见 **6.1s**（上一版 12.2s，系统空闲时测得；
  最终复测时有其他 CPU 密集任务，实测 13.3s，说明对系统负载敏感）。
- 更新清单：`dist/update.json`，SHA256 已生成；签名需在发布环境执行。

## 仍需人工/外部完成

- 代码签名证书（Authenticode）与真实更新服务器。
- 200 条评测样例的人工金标准标注与历史基线。
- Tauri 外壳或进一步压缩 WebView2 首帧，才能到 2.5s。
- 真实模型 live 评测会消耗额度，未在自动测试中执行。
