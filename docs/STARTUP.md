# 启动性能专项

## 实测（同一台 Windows 10 / Python 3.9.8 机器）

### 优化前（V9.2.1）

| 阶段 | 累计耗时 |
|---|---|
| 路径/环境 | 0.13s |
| `import webview` | 2.25s |
| 其余模块导入（API/引擎） | 4.36s |
| `CloudEngine` 初始化（`import openai` + 客户端） | 7.84s |
| API 完成 | 7.87s |
| WebView2 加载完成 | 10.30s |

### 优化后（V9.3.0）

| 阶段 | 累计耗时 |
|---|---|
| 路径/环境 | 0.09s |
| `import webview` | 1.06s |
| API/模块导入 | 1.43s |
| 惰性引擎初始化 | 1.43s（不再阻塞） |
| API 完成 | 1.46s |
| WebView2 加载完成 | **3.24s** |

**源码启动打点 10.3s → 3.2s（约 -69%）；打包版实际窗口可见 12.2s → 6.1s（约 -50%）**。

> 说明：`window_loaded` 打点约 3.2s，但 WebView2 首帧真正可见还要约 2.9s；
> 因此以“窗口可见”为准，打包版是 **6.1s**，不是 3.2s。
> 该数字在系统空闲时测得；本机同时运行其他 CPU 密集型任务时，实测会波动到
> 20–36 秒（pythonnet/WebView2 初始化对 CPU 竞争非常敏感）。

### 打包版（onedir，V9.3.0）

| 阶段 | 累计耗时 |
|---|---|
| `import webview` | 0.85s |
| 模块导入完成 | 1.30s |
| API 初始化完成 | 1.42s |
| WebView2 DOM 加载（打点） | 3.23s |
| **窗口实际可见** | **6.1s** |

### 源码版（V9.3.0）

| 阶段 | 累计耗时 |
|---|---|
| 模块导入完成 | 1.43s |
| API 初始化完成 | 1.46s |
| WebView2 DOM 加载 | 3.24s |

### 做了什么

1. `LazyEngine`：首屏只读配置，第一次 AI 调用才 `import openai`、创建客户端。
2. `cryptography` 惰性导入：密钥文件不在 import 期创建。
3. `PIL/pypinyin` 从 API 顶层导入改为方法内按需导入。
4. 启动打点 `perf.py` 写入 `data/perf/startup.jsonl`，指标面板可看最近启动。
5. 打包版使用 onedir（避免 onefile 解压），并显式收集 webview/pythonnet/clr_loader。

## 耗时剩下的两块

| 块 | 约耗时 | 说明 |
|---|---|---|
| `import webview`（pythonnet/CLR） | 0.9–1.6s | pywebview 的 Windows 后端初始化 |
| WebView2 创建与首帧 | 3.2–4.6s | 含 DOM 加载 + 首帧可见 |

Python 业务初始化已经降到 30–50ms，继续优化 Python 代码收益很小。

## Tauri 外壳评估

| 方案 | 启动 | 改造成本 | 风险 |
|---|---|---|---|
| 保持 pywebview + 惰性加载（当前） | 打点 3.2s / 实际 6.1s | 已完成 | 中：pythonnet/WebView2 受环境影响 |
| Tauri 壳 + Python sidecar（已实测） | 窗口 **0.56–2.7s**；内容 **4–7s** | 已完成 | 已接受产品口径；完整 <3s 需常驻预启动/Rust 核心 |
| Rust/.NET 重写核心 | <1.5s | 3–6 个月 | 高：AI/数据库/内容全部重写 |

**结论**：Tauri 已经证明“窗口可见 <3s”可达；嵌入式 sidecar 业务初始化已降到 0.56s，
但 WebView2 首帧/杀毒/进程开销让完整内容仍在 4–7s。**V9.3 接受这个产品口径**，
不再为完整 <3s 继续 micro-optimize；要打破需常驻预启动或 Rust 核心。

## 如何复测

```bash
python app.py
# 窗口出现后查看 data/perf/startup_latest.json
```

或在「数据管理 → 运行指标」查看最近启动与 p95。

## 注意

- 打包版启动还受杀毒软件扫描/首次运行影响，冷启动可能比源码慢 1–2 秒。
- 本机 WebView2 Runtime 版本较旧（116），升级运行时可改善首帧。
