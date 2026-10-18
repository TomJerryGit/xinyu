# 心语 V9.3.0 · 古典诗词 AI 工作站

> 秦汉唐宋，文脉传承

心语是一款 Windows 桌面端的古典诗词创作与国学教学工具：以 AI 生成为入口，
配合格律检测、六维赏析、教学工坊、题库、经典文库、二创工坊、数据管理与图片导出，
覆盖"创作—学习—教学—沉淀"的完整流程。

技术栈：Python 3.8+ / pywebview（WebView2）/ SQLite / 原生 HTML·CSS·JS。

---

## 快速开始

```bash
# 1. 安装依赖（必须使用项目自带的 requirements.txt）
python -m pip install -r requirements.txt

# 2. 启动
python app.py
```

Windows 下也可以双击 `启动心语.bat`。

首次启动会优先导入随包分发的 **3,090 篇经典种子**（13 类，其中 2,399 篇校勘数据），无需联网；种子缺失时才回退到 7 篇内置范文。

### 配置 AI

首次使用需要填写 API Key：

1. 打开「设置 → API 设置」；
2. 选择服务商（DeepSeek / 通义千问 / 智谱 / Moonshot / OpenAI）；
3. 填入 Key，点击「测试连接」，成功后「保存设置」。

Key 会使用 Fernet 加密后写入 `data/settings.json`，密钥保存在 `data/.secret.key`。
也可以通过环境变量 `DEEPSEEK_API_KEY` 提供默认 Key。

> 离线能力：如果安装 `llama-cpp-python` 并放置 `models/poem.gguf`，可切换到本地引擎；
> 默认不包含模型文件。

---

## 功能

| 模块 | 能力 |
|---|---|
| 概览 | 统计卡片、每日一诗、最近阅读、分类/朝代分布、快捷操作 |
| 创作 | 五/七言绝句、五/七言律诗、词牌、歌词、散文；3 个候选；炼字；转体裁；竖排；复制；保存/导出 |
| 格律 | 绝句、律诗平仄近似检测；词牌明确提示人工核对 |
| 赏析 | 六维深度赏析（背景/解读/意境/格律/文化/教学），失败时给出离线兜底 |
| 二创 | 步韵、仿写、反写、扩写、缩写、现代文改写；英/日翻译；修辞分析；两篇对比 |
| 教学 | 背景溯源、逐句精讲、赏析、练习题、作者信息、学习进度与笔记 |
| 题库 | 选择/判断/填空/默写/出处题；限时挑战；错题本；历史成绩 |
| 文库 | 1,000+ 篇经典；关键词 + 分类分页检索；收藏、笔记、朗读、质量评分 |
| 数据 | 健康检查、质量报告、一键清洗（先备份）、快速扩充、预览审核、用量统计、阅读历史、创作画像、备份中心、插件列表 |
| 导出 | TXT、横排图、信笺、扇面、对联、春联、社交卡片（统一输出到 `exports/`） |
| 朗读 | 系统语音合成；音色/风格/语速；全文/逐句 |
| 交互 | `Ctrl+K` 命令面板、宣纸/水墨/夜间主题、Toast/状态栏/加载遮罩、快捷键 |

### V9.3 新增（阶段 1）

- 经典库扩充到 **3,090 篇 / 13 类**：唐诗、宋词、诗经、楚辞、论语、宋诗、元曲、蒙学、经史子集、经典散文；2,399 篇 `verified=1`，首启自动合并种子。
- 新增二级分类、来源、校勘标识；详见 `docs/CLASSICS_TAXONOMY.md`。
- 启动性能：打点 10.3s → 3.2s，打包版实际窗口可见 12.2s → 6.1s；
- 作业系统：长任务进度、取消、重启恢复；
- AI Gateway：预算、路由、JSON 结构化、缓存；200 条评测集；
- 签名更新：Ed25519 manifest、SHA256、灰度、下载/安装；
- 运行指标：启动、AI 成功率/延迟/成本、崩溃率、作业；
- Tauri spike：窗口可见 0.56–2.24s；sidecar 3.47–6.64s，完整可用仍 >3s；
- 详见 [docs/STARTUP.md](docs/STARTUP.md)、[docs/TAURI_SPIKE.md](docs/TAURI_SPIKE.md) 与 [docs/RELEASE.md](docs/RELEASE.md)。

### V9.2 新增

- 概览仪表盘与每日一诗；
- 经典详情的二创、翻译、修辞、对比与笔记；
- 用量、阅读历史、创作画像、备份中心、插件面板；
- 服务端分页检索与 TTL 缓存；
- `Ctrl+K` 命令面板与三套主题；
- 全新视觉系统与响应式布局。

### 明确的能力边界

- 词牌格律**未实现**自动检测，界面会提示"请人工核对"，不会给出假结论。
- 扩充与赏析依赖在线大模型；无 Key 或无网络时只能使用离线兜底内容。
- 翻译、修辞分析、创作画像等后端能力暂未接入界面。

---

## 项目结构

```
心语/
├── app.py                 # 入口：切换工作目录、创建窗口、启动
├── api.py                 # 业务 API（按领域拆成 6 个 Mixin）
├── engine.py              # 云端/本地双引擎 + API Key 加密
├── version.py             # 版本号唯一来源
├── html_ui.py             # 模板 + CSS + JS 内联
├── templates/index.html   # 界面骨架
├── static/css|js          # 样式与前端控制器
├── database.py            # 作品库/手札
├── classics_database.py   # 经典库
├── classics_importer.py   # 内置范文与 JSON 导入
├── online_importer.py     # chinese-poetry 数据下载/导入
├── backup_manager.py      # 备份与恢复
├── cache_manager.py       # 内存 LRU + SQLite 缓存
├── exporter.py            # PIL 排版导出
├── poetry_checker.py      # 平仄/入声检测
├── style_manager.py       # 体裁与诗人风格库
├── updater.py             # 版本与更新检查
├── utils.py               # 路径、原子写入、权限
├── logger.py              # 轮转日志
├── tests/                 # pytest：核心逻辑 + 前后端契约
└── data/                  # 运行时数据（数据库、密钥、日志）
```

---

## 数据与安全

- **数据目录**：源码运行时是项目目录；安装版默认 `%APPDATA%\Xinyu`；
  便携版在 exe 旁放一个空文件 `portable.flag` 即可；也可用 `XINYU_DATA_DIR` 覆盖。
- `data/` 保存数据库、设置、聊天记录、备份；`exports/` 保存导出图片、文本与诊断包。
- 单实例：重复启动会唤起已有窗口，不会两个进程同时写库。
- 数据库迁移：`schema_migrations` 记录版本，迁移前自动生成 `.pre_vX.bak` 备份。
- 备份 zip **默认排除** `.secret.key`、`app.log`、`*.wal/*.shm` 与缓存；备份前会执行
  WAL checkpoint，避免恢复到半个事务。
- API Key 只以密文形式落盘；`.secret.key` 放在同一目录下，属于"防止误看"级别，
  不等同于操作系统级密钥库。若需更强保护，请迁移到 Windows DPAPI/凭据管理器。
- 崩溃：未捕获异常写入 `data/crash/`；「设置 → 导出诊断」生成不含 Key 与正文的 zip。
- 隐私/数据权利：「设置 → 隐私政策 / 用户协议」可查看；可导出个人数据、清空个人数据
  （清空前自动备份）。
- 所有数据库查询均使用参数化 SQL；界面渲染对 AI/导入内容做 HTML 转义，并启用 CSP。

### 历史遗留提醒

`1.创建目录说明/`、`app_v82_backup.py` 属于历史资料，其中的明文 Key 已替换为占位符。
如果你曾在别处使用过 `sk-e731…` 开头的 Key，请立即到服务商控制台吊销并重新生成。

---

## 测试

```bash
python test_runner.py        # 内置自检（不联网）
python -m pytest -q          # 完整回归（需安装 pytest）
python -m pyflakes api.py ...  # 静态检查
```

契约测试会校验：

- `main.js` 调用的每个方法都在 `API` 中存在；
- `index.html` 的每个内联事件都有 JS 实现；
- `requirements.txt` 声明了实际用到的运行时依赖；
- 数据库迁移会保留旧数据并生成升级前备份。

CI 配置见 `.github/workflows/ci.yml`（Windows + Python 3.11 + Node 20）。

---

## 打包与发布

```bash
python -m pip install pyinstaller
python build.py            # onedir：dist/Xinyu/Xinyu.exe（推荐）
python build.py --onefile  # 单文件便携版：dist/Xinyu.exe
```

完整发布流程（签名、安装包、update.json）见
[docs/RELEASE.md](docs/RELEASE.md)。

安装版数据写到 `%APPDATA%\Xinyu`，不再要求程序目录可写；`data/`、`exports/`、
`backups/` 不打入安装包。

---

## 更新日志

见 [CHANGELOG.md](CHANGELOG.md)。

## 许可与致谢

诗词语料来自 [chinese-poetry](https://github.com/chinese-poetry/chinese-poetry)（MIT）。
本项目仅用于学习与个人创作辅助，生成内容请自行校核。
