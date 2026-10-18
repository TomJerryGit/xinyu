# 生产级构建与发布

## 1. 构建发行目录

```powershell
python -m pip install -r requirements-dev.txt
python -m pip install pyinstaller
python build.py
```

产物：`dist\Xinyu\Xinyu.exe`（onedir，启动快，便于签名与增量更新）。

需要单文件便携版时：

```powershell
python build.py --onefile
# dist\Xinyu.exe
```

onedir 是生产默认；单文件冷启动会慢很多，只适合 U 盘/临时分发。

## 2. 生成更新清单

```powershell
powershell -ExecutionPolicy Bypass -File tools\build_release.ps1
```

会输出：

- `dist\Xinyu\Xinyu.exe`
- `dist\update.json`：版本、文件名、SHA256、大小、发布时间
- 如果本机安装了 Inno Setup 6：`dist\installer\Xinyu-Setup-<版本>.exe`

## 3. Authenticode 代码签名（必须）

生产发布必须用 OV/EV 代码签名证书签名 `Xinyu.exe` 与安装包，否则 SmartScreen 会拦截。

```powershell
# 证书在当前用户证书库（推荐 CI 用 PFX）
$env:XINYU_SIGN_CERT_THUMBPRINT = "ABCDEF..."
# 或
$env:XINYU_SIGN_PFX = "D:\secrets\xinyu.pfx"
$env:XINYU_SIGN_PASSWORD = "***"

powershell -ExecutionPolicy Bypass -File tools\sign_artifacts.ps1 -Files dist\Xinyu\Xinyu.exe
```

`build_release.ps1` 会在生成安装包前自动签 exe，并在安装包生成后签安装包；
**必须先签名再算 SHA256**，否则更新校验会失败。

更新服务器/灰度/回滚的完整说明见 [UPDATE_SERVER.md](UPDATE_SERVER.md)。

## 4. 更新源与签名

生成密钥（只做一次，私钥不要提交）：

```powershell
python tools/sign_manifest.py init --key update_private.key
# 输出 public_key，填入 updater.BUILTIN_UPDATE_PUBLIC_KEY
# 或构建环境变量 XINYU_UPDATE_PUBLIC_KEY
```

`dist\update.json` 需要包含 `version`、`url`、`sha256`；签名：

```powershell
python tools/sign_manifest.py sign --key update_private.key --manifest dist\update.json
```

把 `update.json` 与安装包上传到 HTTPS 静态站点，在「设置 → 更新源」填入
`update.json` 的 URL。客户端会：

1. 校验 Ed25519 签名（公钥不匹配/未签名直接拒绝）；
2. 按 `rollout` 百分比做稳定灰度；
3. 下载后校验 SHA256；
4. 启动安装程序并退出。

清单可选 `rollback` 字段，用于运营回滚：

```json
"rollback": {
  "version": "9.2.1",
  "url": "https://example.com/xinyu/Xinyu-Setup-9.2.1.exe",
  "sha256": "..."
}
```

客户端 API `rollback_update` 会下载并启动该安装包；回滚前先确认备份与数据库
迁移兼容（新库可能无法被旧版本读取，回滚需同时恢复升级前备份）。

## 5. 数据目录

- 安装版：`%APPDATA%\Xinyu`
- 便携版：exe 旁放一个空文件 `portable.flag`，数据写在 exe 目录
- 可用环境变量 `XINYU_DATA_DIR` 覆盖

卸载不会删除 `%APPDATA%\Xinyu`，避免误删用户作品；需要在系统中手动清理。

## 6. 灰度与回滚

- `rollout` 为 0–100，客户端用 `install_id + version` 做稳定哈希，同一设备结果固定。
- 建议按 5% → 25% → 100% 三档放量，每档观察崩溃率、启动 p95、AI 成功率。
- 回滚：清单提供 `rollback` 安装包，客户端 `rollback_update` 下载并启动；
  若数据库已迁移，必须先恢复升级前备份，不能只降级 exe。

## 7. 发布前检查

- [ ] `python -m pytest -q` 全绿
- [ ] `python test_runner.py` 全绿
- [ ] 干净 Windows 虚拟机安装/启动/卸载
- [ ] 升级旧版本（含数据库迁移备份）成功
- [ ] 备份/恢复演练
- [ ] 签名与时间戳
- [ ] `update.json` 的 SHA256 与产物一致
- [ ] 隐私政策/用户协议可打开
- [ ] 诊断包不包含 API Key 与作品正文
