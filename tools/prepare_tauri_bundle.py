# -*- coding: utf-8 -*-
"""把 onedir sidecar 复制到 Tauri 资源目录，供 NSIS 安装包打包。"""
import os
import shutil

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "dist", "XinyuSidecar")
DST = os.path.join(BASE, "spike", "tauri", "src-tauri", "sidecar", "XinyuSidecar")

if not os.path.exists(os.path.join(SRC, "XinyuSidecar.exe")):
    raise SystemExit(f"missing sidecar: {SRC}")
if os.path.exists(DST):
    shutil.rmtree(DST)
shutil.copytree(SRC, DST)
print("prepared:", DST)
