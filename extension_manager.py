"""
心语 V6.5 — 扩展包管理
下载、安装、卸载经典文库扩展包
"""
import os, json, zipfile
from datetime import datetime

class ExtensionManager:
    def __init__(self, base_dir="resources/extensions"):
        self.base_dir = base_dir
        self.reg_path = os.path.join(base_dir, "registry.json")
        os.makedirs(base_dir, exist_ok=True)
        self.reg = self._load_reg()

    def _load_reg(self):
        if os.path.exists(self.reg_path):
            with open(self.reg_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        default = {
            "installed": {},
            "available": {
                "tang_ext": {"name": "唐诗扩展包", "size": "1.5MB", "url": ""},
                "song_ext": {"name": "宋词扩展包", "size": "0.8MB", "url": ""},
                "guwen_ext": {"name": "古文扩展包", "size": "1.2MB", "url": ""}
            }
        }
        self._save_reg(default)
        return default

    def _save_reg(self, data=None):
        if data:
            self.reg = data
        with open(self.reg_path, 'w', encoding='utf-8') as f:
            json.dump(self.reg, f, ensure_ascii=False, indent=2)

    def install(self, ext_id, zip_path):
        if ext_id not in self.reg["available"]:
            return False
        ext_dir = os.path.join(self.base_dir, ext_id)
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(ext_dir)
        self.reg["installed"][ext_id] = {
            "version": self.reg["available"][ext_id].get("version", "1.0"),
            "installed_at": datetime.now().isoformat()
        }
        self._save_reg()
        return True

    def uninstall(self, ext_id):
        if ext_id in self.reg["installed"]:
            ext_dir = os.path.join(self.base_dir, ext_id)
            if os.path.exists(ext_dir):
                import shutil
                shutil.rmtree(ext_dir)
            del self.reg["installed"][ext_id]
            self._save_reg()

    def is_installed(self, ext_id):
        return ext_id in self.reg["installed"]

    def get_available(self):
        return self.reg.get("available", {})

    def get_installed(self):
        return self.reg.get("installed", {})