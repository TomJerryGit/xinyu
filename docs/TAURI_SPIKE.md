# Tauri 外壳 spike 结论

## 本机工具链（已安装，最小化）

| 工具 | 状态 |
|---|---|
| Rust / cargo | **1.99.1**，安装到 `D:\Rust`（minimal profile） |
| VS Build Tools 2022 | **17.14.42**，仅 C++ 工作负载，安装到 `D:\VSBuildTools` |
| MSVC | **14.44.35207** |
| Windows SDK | **10.0.26100.0** |
| Tauri CLI | 未装；直接用 `cargo build --release` |
| WebView2 Runtime | 已安装（116.0.1938.62） |

实际磁盘占用：**约 16 GB**（C 盘约 7.4 GB，D 盘约 8.9 GB，含 1.3 GB cargo target）。
“省空间”仍不是 2–3 GB，MSVC + Windows SDK 是硬成本。

## 实测

| 项目 | 结果 |
|---|---|
| Tauri release 编译 | **成功**，20m18s；增量 3m29s |
| Tauri exe | `dist/tauri-spike/xinyu-tauri-spike.exe`，8.6 MB |
| **窗口可见（splash）** | **0.56–2.7s** |
| PyInstaller sidecar | 3.47–6.64s |
| **嵌入式 Python sidecar（内部）** | **0.25–0.56s** |
| 嵌入式 sidecar（源码 bundle，wall） | **1.22s** |
| 嵌入式 sidecar（安装目录，wall） | 3–7s（首次杀毒扫描/进程开销） |
| 页面内容 | 真实 1,056 篇、205,812 字、13 类、8 导航 |

> 结论：嵌入式 runtime 把“业务侧”压到 0.56s 内，但安装目录首次启动仍受
> 杀毒扫描/进程创建影响；Tauri 窗口 <3s 稳定达到，完整页面仍是 4–7s。

## 安装包（NSIS）

没有继续等 Tauri CLI（编译超过 40 分钟），改用官方 NSIS 3.13 便携包手工打包；
sidecar 作为 **嵌入资源目录** 随安装包分发：

| 项目 | 结果 |
|---|---|
| 安装包 | `dist/installer/Xinyu-Tauri-Spike-Setup-9.3.0.exe`，**18.7 MB** |
| 安装后 | 约 **66.9 MB**，含 `sidecar\embedded\python` + `app` |
| 安装/卸载 | `/S` 静默安装、卸载均通过 |
| sidecar 加载 | 验证从 `%LOCALAPPDATA%\Programs\XinyuTauriSpike\sidecar\embedded\...` 启动 |
| Authenticode | 自签名测试证书可签名，但状态 `UnknownError`（不受信任）；无正式证书 |

## 产品口径（已确定）

V9.3 接受：

> **splash 秒开（<3s 可见），诗词库内容 4–7s 可用。**

不再为“完整内容 <3s”继续 micro-optimize；后续若要打破，需要 Rust 核心或预启动常驻
sidecar，而不是继续改 Python 导入。

## 关键设计

```text
Tauri 进程
  ├─ 立即显示正式 splash（窗口 0.56–2.7s 可见）
  ├─ 启动 sidecar\embedded\python\python.exe app\sidecar_server.py
  ├─ 后台等待 127.0.0.1:18765（若已有预启动 sidecar 则跳过）
  └─ 就绪后 window.navigate("http://127.0.0.1:18765/")
```

关键文件：

- `spike/tauri/src-tauri/src/main.rs`
- `spike/tauri/src-tauri/tauri.conf.json`
- `spike/tauri/README.md`
- `sidecar_server.py`
- `static/js/web_shim.js`

## 下一步

1. 产品口径已接受：splash <3s，内容 4–7s；
2. 若要“完整 <3s”，做常驻预启动 sidecar（登录启动）或 Rust 核心；
3. 正式发布仍需 Authenticode 证书与更新清单签名；
4. 安装包可继续做代码签名、自动更新与崩溃上报。

## CI（已保留）

`.github/workflows/tauri-spike.yml` 仍可用于无本机工具链的机器；
但本机已经装好工具链，可直接 `cargo build`，不需要 CI 也能复现。
