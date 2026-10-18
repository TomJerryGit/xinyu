# 心语阶段 0 验收记录（生产级底座）

日期：2026-10-17 · 版本 9.2.1

## 已完成

| 能力 | 实现 | 位置 |
|---|---|---|
| 可写数据目录 | 安装版 `%APPDATA%\Xinyu`；便携版 `portable.flag`；`XINYU_DATA_DIR` 覆盖 | `utils.py` |
| 单实例 | Windows `msvcrt` / POSIX `flock`；第二实例唤起已有窗口 | `single_instance.py`、`app.py` |
| 数据库迁移 | `schema_migrations`、迁移前在线备份、失败回滚 | `migrations.py`、`classics_database.py` |
| 统一错误契约 | 公开 API 未捕获异常 → `{"__error__": {code,message}}`；前端转 Error | `errors.py`、`api.py`、`main.js` |
| 崩溃捕获 | 主线程/子线程 excepthook → `data/crash` | `crash_reporter.py`、`app.py` |
| 诊断包 | 不含 Key/正文的 zip（系统信息/日志/DB 统计/脱敏设置） | `crash_reporter.py` |
| 隐私与数据权利 | 隐私政策/用户协议；导出个人数据；输入 DELETE 清空并先备份 | `legal.py`、`api.py`、`index.html` |
| CI | Windows + Python 3.11 + Node 20：lint、pytest、import、JS 语法 | `.github/workflows/ci.yml` |
| 构建/安装 | `Xinyu.exe`、`update.json`（SHA256）、Inno Setup 脚本 | `build.py`、`tools/build_release.ps1`、`installer/xinyu.iss` |
| 发布文档 | 签名、安装包、更新源、数据目录、发布检查清单 | `docs/RELEASE.md` |

## 验证

- `pytest`：22 项通过（含迁移、迁移备份、错误契约、诊断包、分页）。
- 单实例：同一进程第二次 acquire 返回 False；释放后可重新获取。
- 真实库迁移：`schema_version=1`，1,056 行保留，生成 `classics.db.pre_v0_to_v1_*.bak`。
- 诊断包：`settings.redacted.json` 中 `api_key="***"`；包含 system/db_stats/app.log。
- 打包：
  - onedir 产物 `dist/Xinyu/Xinyu.exe`（9.5 MB），发行目录约 100.8 MB；
  - 打包后真实启动，窗口标题 `心语 V9.2.1`，数据目录按 `XINYU_DATA_DIR` 生效；
  - 冷启动到窗口可见 **约 12.2 秒**（onedir，首次运行），未达到 2.5 秒 SLO；
  - `dist/update.json` 已生成（版本 / SHA256 / 大小 / 时间）。
- JS 语法、pyflakes、pytest（22）、内置自检（27）全部通过。

## 已知问题（进入阶段 1 优先处理）

1. **打包冷启动 14.5s**：pythonnet/.NET + WebView2 + 100MB 目录导致。
   下一步评估 Tauri/.NET 外壳，或把 Python 核心改为本地 sidecar 后延迟加载；
   在此之前不建议把"启动快"作为宣传点。
2. 代码签名证书、真实更新服务器、签名 manifest 校验未接入。
3. API Key 仍在 Fernet 文件方案；迁移到 Windows DPAPI。
4. 作业系统（进度/取消）、E2E 自动化、AI 评测集与发布门禁未完成。
5. 可观测性仅本地日志/诊断包，没有崩溃上报服务。
