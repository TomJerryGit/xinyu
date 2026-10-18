# -*- coding: utf-8 -*-
"""PyInstaller 打包脚本。

默认生成 **onedir** 发行目录（启动快、便于签名/更新）；传 ``--onefile``
生成单文件便携版。pywebview 的 Windows 后端依赖 pythonnet/CLR，
因此显式收集 webview、pythonnet 与 clr_loader。
"""
import os
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SEP = ";" if os.name == "nt" else ":"


def build(onefile: bool = False) -> int:
    name = "Xinyu"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        name,
        "--onefile" if onefile else "--onedir",
        "--collect-all",
        "webview",
        "--collect-all",
        "pythonnet",
        "--collect-all",
        "clr_loader",
        "--hidden-import",
        "clr",
        "--hidden-import",
        "webview.platforms.edgechromium",
        "--hidden-import",
        "cryptography.fernet",
        "--hidden-import",
        "cryptography.hazmat.primitives.asymmetric.ed25519",
        "--hidden-import",
        "exporter",
        "--hidden-import",
        "poetry_checker",
        "--hidden-import",
        "test_runner",
        "--hidden-import",
        "PIL.Image",
        "--hidden-import",
        "PIL.ImageDraw",
        "--hidden-import",
        "PIL.ImageFont",
        "--exclude-module",
        "PyQt5",
        "--exclude-module",
        "PyQt6",
        "--exclude-module",
        "PySide6",
        "--exclude-module",
        "pandas",
        "--exclude-module",
        "matplotlib",
        "--exclude-module",
        "scipy",
        "--exclude-module",
        "tkinter",
        "--exclude-module",
        "IPython",
    ]
    for folder in ("templates", "static", "locales", "resources"):
        command += ["--add-data", f"{folder}{SEP}{folder}"]
    for filename in ("CHANGELOG.md", "README.md"):
        if os.path.exists(os.path.join(BASE_DIR, filename)):
            command += ["--add-data", f"{filename}{SEP}."]
    command.append("app.py")

    print("打包:", name, "(onefile)" if onefile else "(onedir)")
    print(" ".join(command))
    result = subprocess.run(command, cwd=BASE_DIR)
    if result.returncode == 0:
        target = os.path.join("dist", f"{name}.exe" if onefile else os.path.join(name, f"{name}.exe"))
        print(f"完成: {target}")
    else:
        print(f"打包失败，退出码 {result.returncode}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(build("--onefile" in sys.argv))
