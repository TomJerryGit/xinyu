# -*- coding: utf-8 -*-
"""构建 Tauri/WebView2 使用的无界面 sidecar。

不包含 pywebview/pythonnet/PyQt，启动比完整桌面壳快。
"""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
SEP = ";" if os.name == "nt" else ":"


def main():
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--console", "--name", "XinyuSidecar", "--onedir",
        "--hidden-import", "cryptography.fernet",
        "--hidden-import", "cryptography.hazmat.primitives.asymmetric.ed25519",
        "--hidden-import", "exporter",
        "--hidden-import", "poetry_checker",
        "--hidden-import", "PIL.Image",
        "--hidden-import", "PIL.ImageDraw",
        "--hidden-import", "PIL.ImageFont",
        "--exclude-module", "webview",
        "--exclude-module", "clr",
        "--exclude-module", "clr_loader",
        "--exclude-module", "pythonnet",
        "--exclude-module", "PyQt5",
        "--exclude-module", "PyQt6",
        "--exclude-module", "PySide6",
        "--exclude-module", "pandas",
        "--exclude-module", "matplotlib",
        "--exclude-module", "scipy",
        "--exclude-module", "tkinter",
    ]
    for folder in ("templates", "static", "locales", "resources"):
        command += ["--add-data", f"{folder}{SEP}{folder}"]
    for filename in ("CHANGELOG.md", "README.md"):
        if os.path.exists(os.path.join(BASE, filename)):
            command += ["--add-data", f"{filename}{SEP}."]
    command.append("sidecar_server.py")
    print("构建 sidecar:", " ".join(command))
    result = subprocess.run(command, cwd=BASE)
    if result.returncode == 0:
        print("完成: dist\\XinyuSidecar\\XinyuSidecar.exe")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
