# -*- coding: utf-8 -*-
"""版本信息、更新检查、签名校验与灰度。

更新源通过 ``XINYU_UPDATE_URL`` 或 ``data/settings.json`` 的 ``update.url`` 配置。
更新清单格式：

```json
{
  "version": "9.3.0",
  "url": "https://example.com/Xinyu-Setup-9.3.0.exe",
  "sha256": "...",
  "signature": "base64(ed25519(version|url|sha256))",
  "rollout": 25,
  "notes": "..."
}
```

公钥通过编译期常量 ``BUILTIN_UPDATE_PUBLIC_KEY`` 或
``XINYU_UPDATE_PUBLIC_KEY`` 环境变量提供（base64 raw Ed25519 public key）。
"""
import base64
import hashlib
import os
import subprocess
import uuid

from logger import log
from utils import app_path, resource_path, safe_json_load, safe_json_save
from version import APP_NAME, AUTHOR, CODENAME, VERSION, version_tuple


class _RequestsProxy:
    """惰性导入 requests，避免 API 首屏加载。"""

    def __getattr__(self, name):
        import requests

        return getattr(requests, name)


requests = _RequestsProxy()

DEFAULT_UPDATE_URL = os.getenv("XINYU_UPDATE_URL", "").strip()
BUILTIN_UPDATE_PUBLIC_KEY = ""  # 发布时填入 base64 公钥，或使用环境变量


def _public_key() -> str:
    return (os.getenv("XINYU_UPDATE_PUBLIC_KEY", "").strip() or BUILTIN_UPDATE_PUBLIC_KEY).strip()


def signing_payload(version: str, url: str, sha256: str, rollback_url: str = "", rollback_sha256: str = "") -> bytes:
    payload = f"{version}|{url}|{sha256}"
    if rollback_url or rollback_sha256:
        payload += f"|{rollback_url}|{rollback_sha256}"
    return payload.encode("utf-8")


def verify_signature(version: str, url: str, sha256: str, signature: str, public_key: str, rollback_url: str = "", rollback_sha256: str = "") -> bool:
    """校验 Ed25519 签名；任何异常都视为失败。"""
    if not (version and url and sha256 and signature and public_key):
        return False
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key))
        key.verify(
            base64.b64decode(signature),
            signing_payload(version, url, sha256, rollback_url, rollback_sha256),
        )
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False
    except Exception:
        return False


class Updater:
    def __init__(self):
        self.current = VERSION
        self.update_info = None
        self.update_url = DEFAULT_UPDATE_URL or self._url_from_settings()

    @staticmethod
    def _settings():
        data = safe_json_load(app_path("data", "settings.json"), {})
        return data if isinstance(data, dict) else {}

    def _url_from_settings(self):
        return str((self._settings().get("update") or {}).get("url", "")).strip()

    def _install_id(self) -> str:
        settings = self._settings()
        update = settings.setdefault("update", {})
        install_id = str(update.get("install_id", "")).strip()
        if install_id:
            return install_id
        install_id = uuid.uuid4().hex
        update["install_id"] = install_id
        settings["update"] = update
        safe_json_save(app_path("data", "settings.json"), settings)
        return install_id

    def in_rollout(self, rollout, version) -> bool:
        """稳定灰度：同一设备对同一版本的结果固定。"""
        try:
            percent = max(0, min(100, int(rollout)))
        except (TypeError, ValueError):
            percent = 100
        if percent >= 100:
            return True
        if percent <= 0:
            return False
        digest = hashlib.sha256(f"{self._install_id()}|{version}".encode("utf-8")).hexdigest()
        return int(digest[:8], 16) % 100 < percent

    def check_update(self):
        """返回统一结构的检查结果（含签名与灰度状态）。"""
        result = {
            "has_update": False,
            "current": self.current,
            "latest": "",
            "url": "",
            "sha256": "",
            "signature_verified": False,
            "rollout": 100,
            "rollback": {},
            "message": "",
        }
        if not self.update_url:
            result["message"] = "未配置更新源，可在设置中填写 update.url"
            return result

        try:
            resp = requests.get(self.update_url, timeout=6)
            if resp.status_code != 200:
                result["message"] = f"更新服务不可用（HTTP {resp.status_code}）"
                return result
            data = resp.json()
            latest = str(data.get("tag_name") or data.get("version") or "").lstrip("vV")
            if not latest:
                result["message"] = "更新源返回格式不正确"
                return result

            url = str(data.get("url") or data.get("html_url") or "").strip()
            sha256 = str(data.get("sha256") or "").strip().lower()
            signature = str(data.get("signature") or "").strip()
            rollout = data.get("rollout", 100)
            rollback = data.get("rollback") if isinstance(data.get("rollback"), dict) else {}
            result.update(latest=latest, url=url, sha256=sha256, rollout=rollout, rollback=rollback)
            self.update_info = {
                "version": latest, "url": url, "sha256": sha256,
                "signature": signature, "rollback": rollback,
            }

            key = _public_key()
            if signature:
                if not key:
                    result["message"] = "更新包已签名，但客户端未配置公钥，已拒绝"
                    return result
                if not verify_signature(
                    latest, url, sha256, signature, key,
                    str(rollback.get("url", "")), str(rollback.get("sha256", "")),
                ):
                    result["message"] = "更新包签名校验失败，已拒绝"
                    log("warning", f"更新签名校验失败: {latest}")
                    return result
                result["signature_verified"] = True
            elif key:
                result["message"] = "更新包未签名，已按安全策略拒绝"
                return result

            if version_tuple(latest) <= version_tuple(self.current):
                result["message"] = "已是最新版本"
                return result
            if not self.in_rollout(rollout, latest):
                result["message"] = f"新版本正在灰度（{rollout}%），暂未覆盖本机"
                return result

            self.update_info = {
                "version": latest,
                "notes": data.get("body", "") or data.get("notes", ""),
                "url": url,
                "sha256": sha256,
                "signature": signature,
                "rollback": rollback,
            }
            result.update(has_update=True, message="发现新版本")
            return result
        except Exception as exc:  # noqa: BLE001 - 更新检查失败不影响使用
            log("warning", f"检查更新失败: {str(exc)[:100]}")
            result["message"] = "检查更新失败，请检查网络"
            return result

    def download_update(self, url: str = "", expected_sha256: str = ""):
        """下载更新包并校验 SHA256；返回 {success,path/message}。"""
        target_url = url or (self.update_info or {}).get("url", "")
        if not target_url:
            return {"success": False, "message": "没有可下载的更新地址"}
        expected = (expected_sha256 or (self.update_info or {}).get("sha256", "")).strip().lower()
        directory = app_path("exports")
        os.makedirs(directory, exist_ok=True)
        filename = os.path.basename(target_url.split("?")[0]) or f"Xinyu-Update-{self.current}.exe"
        path = os.path.join(directory, filename)
        try:
            with requests.get(target_url, stream=True, timeout=60) as response:
                response.raise_for_status()
                with open(path, "wb") as handle:
                    for chunk in response.iter_content(chunk_size=1 << 16):
                        if chunk:
                            handle.write(chunk)
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "message": f"下载失败: {str(exc)[:160]}"}
        if expected:
            with open(path, "rb") as handle:
                digest = hashlib.sha256(handle.read()).hexdigest()
            if digest != expected:
                try:
                    os.remove(path)
                except OSError:
                    pass
                return {"success": False, "message": "更新包 SHA256 校验失败，已删除"}
        return {"success": True, "path": path, "message": "下载并校验完成"}

    def rollback_update(self, url: str = "", sha256: str = ""):
        """下载并启动上一版本安装包（回滚需由运营在清单中提供 rollback）。"""
        info = self.update_info or {}
        target_url = url or str((info.get("rollback") or {}).get("url", ""))
        target_sha = sha256 or str((info.get("rollback") or {}).get("sha256", ""))
        if not target_url:
            return {"success": False, "message": "清单未提供可回滚版本"}
        downloaded = self.download_update(target_url, target_sha)
        if not downloaded.get("success"):
            return downloaded
        return self.install_update(downloaded["path"])

    @staticmethod
    def install_update(path: str):
        """启动安装程序；调用方应在成功后退出应用。"""
        if not path or not os.path.exists(path):
            return {"success": False, "message": "安装包不存在"}
        try:
            subprocess.Popen([path, "/SILENT", "/NORESTART"], close_fds=True)
            return {"success": True, "message": "已启动安装程序，应用即将退出"}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "message": f"启动安装程序失败: {exc}"}

    def get_changelog(self):
        for path in (resource_path("CHANGELOG.md"), app_path("CHANGELOG.md")):
            if not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    return handle.read()
            except Exception:
                continue
        return "暂无更新日志"


class VersionManager:
    @staticmethod
    def get_version():
        return VERSION

    @staticmethod
    def get_full_info():
        return {
            "version": VERSION,
            "name": APP_NAME,
            "codename": CODENAME,
            "author": AUTHOR,
            "features": [
                "概览仪表盘",
                "AI智能创作",
                "格律检测",
                "推敲炼字",
                "六维赏析",
                "二创工坊",
                "英日翻译",
                "经典文库",
                "教学工坊",
                "题库与错题本",
                "用量统计",
                "备份中心",
                "命令面板",
            ],
        }

    @staticmethod
    def ensure_changelog():
        """兼容旧调用：不再向用户数据目录写 CHANGELOG。"""
        return False
