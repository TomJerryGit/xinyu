# Tauri 2 外壳 spike

## 目标

用 Tauri 2 的 WebView2 窗口加载本机 sidecar 提供的 `http://127.0.0.1:18765/`，
替代 pywebview + pythonnet，验证能否把“窗口可见”压到 3 秒内。

## 前置

- Windows 10/11 + WebView2 Runtime
- Rust stable + MSVC Build Tools（本机已装：Rust 1.99.1、MSVC 14.44、Windows SDK 10.0.26100）
- Tauri CLI 不是必需：直接用 `cargo build --release`
- 先构建 sidecar：

```powershell
cd D:\xinyu
python build_sidecar.py
# dist\XinyuSidecar\XinyuSidecar.exe
```

## 运行

```powershell
# 先打开 VS 开发环境，确保 link.exe 在 PATH
call "D:\VSBuildTools\Common7\Tools\VsDevCmd.bat" -arch=x64

set RUSTUP_HOME=D:\Rust\rustup
set CARGO_HOME=D:\Rust\cargo
set CARGO_TARGET_DIR=D:\cargo-target\xinyu-tauri
set PATH=D:\Rust\cargo\bin;%PATH%
set XINYU_ROOT=D:\xinyu

cargo build --release --manifest-path D:\xinyu\spike\tauri\src-tauri\Cargo.toml
D:\cargo-target\xinyu-tauri\release\xinyu-tauri-spike.exe
```

Rust 会启动 `XinyuSidecar.exe --port 18765`（`CREATE_NO_WINDOW`），**立即显示本地 splash**，
后台等待端口就绪后导航到 `http://127.0.0.1:18765/`。“窗口可见”和“完整可用”是两个指标。

## CI（可选）

`.github/workflows/tauri-spike.yml` 在 `windows-latest` 上构建 sidecar + Tauri 并上传 artifact。
本机已经装好工具链，可直接 `cargo build`，CI 只在无工具链的机器上需要。

## 实测（本机）

- Tauri release 编译成功，20m18s；增量 3m29s。
- 窗口可见 **0.56–2.7s**（splash）。
- 嵌入式 Python sidecar：内部 **0.25–0.56s**；源码 bundle wall **1.22s**；
  安装目录首次 wall 3–7s（杀毒/进程开销）。
- 截图确认真实 1,056 篇、205,812 字、13 类、8 导航。
- 产品口径：**splash 秒开，内容 4–7s 可用。**

## 安装包

```powershell
python tools\prepare_tauri_bundle.py
& "D:\tools\nsis\nsis-3.13\Bin\makensis.exe" installer\tauri-spike.nsi
# dist\installer\Xinyu-Tauri-Spike-Setup-9.3.0.exe
```

安装包约 **18.7 MB**，安装后约 **66.9 MB**；包含 `sidecar\embedded\python` + `app`。
已验证静默安装、embedded sidecar 路径、卸载。Tauri CLI 没有安装，使用 NSIS 资源式打包。

## 已知限制

- 没有 Tauri CLI；用 `cargo build` + NSIS 资源式安装包替代。
- 产品口径已接受：splash <3s，内容 4–7s；完整 <3s 需要常驻预启动或 Rust 核心。
- 生产发布仍需要 Authenticode 证书、正式安装包签名与更新清单签名。
- 窗口加载的是 localhost HTTP；生产建议保留随机 token（已实现 `X-Xinyu-Token`）和
  只监听 127.0.0.1。
