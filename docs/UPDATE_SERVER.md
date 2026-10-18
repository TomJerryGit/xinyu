# 更新服务器、签名、灰度与回滚

## 1. HTTPS 更新源

更新源只需要静态 HTTPS 文件服务（S3/CloudFront、OSS、nginx 均可）：

```text
https://download.example.com/xinyu/
  update.json
  Xinyu-Setup-9.3.0.exe
  Xinyu-Setup-9.2.1.exe   # 回滚用，可选
```

要求：

- 必须 HTTPS，证书有效；不要用自签名证书。
- `update.json` 使用 `application/json`，`Cache-Control: no-cache`。
- 安装包使用不可变 URL（文件名带版本），`Cache-Control: public, max-age=31536000, immutable`。
- 服务器不需要 CORS（客户端是 native requests，不是浏览器）。
- 不要在同一 URL 覆盖旧安装包；保留至少两个历史版本用于回滚。

`update.json` 示例：

```json
{
  "version": "9.3.0",
  "url": "https://download.example.com/xinyu/Xinyu-Setup-9.3.0.exe",
  "sha256": "…",
  "size": 12345678,
  "rollout": 5,
  "notes": "阶段 1",
  "signature": "base64(ed25519(...))",
  "rollback": {
    "version": "9.2.1",
    "url": "https://download.example.com/xinyu/Xinyu-Setup-9.2.1.exe",
    "sha256": "…"
  }
}
```

## 2. 正式公钥

```powershell
python tools/sign_manifest.py init --key update_private.key
# 输出 public_key
```

把公钥填入 `updater.BUILTIN_UPDATE_PUBLIC_KEY`（推荐编译进产物）或设置构建环境
`XINYU_UPDATE_PUBLIC_KEY`。私钥只放 CI secret，绝不进仓库/安装包。

生成清单：

```powershell
$env:XINYU_UPDATE_PRIVATE_KEY = "D:\secrets\update_private.key"
$env:XINYU_UPDATE_URL = "https://download.example.com/xinyu/update.json"
$env:XINYU_ROLLOUT = "5"
powershell -ExecutionPolicy Bypass -File tools\build_release.ps1
```

签名覆盖 `version|url|sha256`（有 rollback 时还覆盖 rollback 的 url/sha）。
客户端没有公钥时会接受未签名清单；生产必须配置公钥，否则等于关闭更新验签。

## 3. Authenticode

- 购买 OV/EV 代码签名证书（推荐 EV，SmartScreen 信誉更好）。
- 在 CI secret 中保存 PFX/密码或证书 thumbprint。
- `build_release.ps1` 会签 exe、安装包；**签名后**才计算 SHA256。
- 验证：

```powershell
Get-AuthenticodeSignature dist\Xinyu\Xinyu.exe | Format-List
```

本机当前没有 Authenticode 证书，`dist\update.json` 是未签名的开发清单。

## 4. 灰度 5% → 25% → 100%

```powershell
python tools/set_rollout.py --file dist\update.json --rollout 5
# 上传 update.json
# 观察 24h：崩溃率、启动 p95、AI 成功率、回滚请求
python tools/set_rollout.py --file dist\update.json --rollout 25
# 观察 24h
python tools/set_rollout.py --file dist\update.json --rollout 100
```

客户端用 `install_id + version` 做稳定哈希，同一设备在同一版本上的灰度结果固定。
`rollout` 不在 Ed25519 签名范围内（它只控制分发比例，不控制包内容）。

放量门禁建议：

| 档位 | 最低观察时长 | 阻断条件 |
|---|---|---|
| 5% | 24h | 崩溃率 > 基线 2 倍，或启动 p95 明显恶化 |
| 25% | 24h | AI 成功率下降 > 5%，或出现数据损坏 |
| 100% | — | 前两档无阻断 |

## 5. 回滚

1. 把 `update.json` 的 `version` 改回上一版（或提供 `rollback` 字段）。
2. 用上一版安装包 URL/SHA256；客户端 `rollback_update` 下载并启动安装程序。
3. 若新版本已迁移数据库，必须同时恢复升级前备份；旧 exe 不能直接读新 schema。
4. 回滚后 24h 内不要再次自动放量。

## 6. 发布检查

- [ ] exe 与安装包 Authenticode 签名有效
- [ ] `update.json` 的 SHA256 对应**已签名**产物
- [ ] Ed25519 签名校验通过，公钥已编译进客户端
- [ ] HTTPS 可访问，`update.json` 不缓存
- [ ] 5% 灰度可被目标设备命中，非目标设备提示“灰度未覆盖”
- [ ] 回滚安装包与备份可用
