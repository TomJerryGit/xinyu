#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
心语 V6.5 项目初始化脚本
自动生成完整目录结构并创建所有 Python 文件占位
运行方式: python setup.py
"""

import os

ROOT = os.path.dirname(os.path.abspath(__file__))

DIRS = [
    "resources/audio/classics",
    "resources/audio/bgm",
    "resources/fonts",
    "resources/extensions",
    "prompts",
    "plugins/xinyu-music",
    "plugins/xinyu-export-ext",
    "plugins/xinyu-audio-classics",
    "plugins/xinyu-game",
    "locales",
    "models",
    "data",
    "backups",
]

PYTHON_FILES = [
    "app.py",
    "engine.py",
    "style_manager.py",
    "poetry_checker.py",
    "lyric_checker.py",
    "database.py",
    "exporter.py",
    "classic_library.py",
    "preference_learner.py",
    "annotation_manager.py",
    "plugin_manager.py",
    "backup_manager.py",
    "extension_manager.py",
    "rhetorica.py",
    "poet_profiler.py",
    "poetry_tutor.py",
    "poetry_translator.py",
    "i18n_manager.py",
    "prompt_forge.py",
]

RESOURCE_FILES = [
    "resources/classics.json",
    "resources/word_relations.json",
    "resources/knowledge_cards.json",
    "resources/rhyme_dict.json",
    "resources/allusion_db.json",
    "requirements.txt",
    "README.md",
]

LOCALE_FILES = [
    "locales/zh-CN.json",
    "locales/en-US.json",
    "locales/ja-JP.json",
]


def create_dirs():
    for d in DIRS:
        os.makedirs(os.path.join(ROOT, d), exist_ok=True)
    print("✅ 目录结构已创建")


def create_python_files():
    for f in PYTHON_FILES:
        path = os.path.join(ROOT, f)
        if not os.path.exists(path):
            with open(path, 'w', encoding='utf-8') as fp:
                fp.write(f'# {f} - 心语 V6.5 模块\n')
                fp.write('# 请将完整代码填入此文件\n\n')
    print(f"✅ {len(PYTHON_FILES)} 个 Python 文件已就绪")


def create_resource_files():
    for f in RESOURCE_FILES + LOCALE_FILES:
        path = os.path.join(ROOT, f)
        if not os.path.exists(path):
            with open(path, 'w', encoding='utf-8') as fp:
                fp.write('{}\n' if f.endswith('.json') else '')
    print("✅ 资源文件已创建")


def main():
    print("心语 V6.5 项目初始化中...")
    create_dirs()
    create_python_files()
    create_resource_files()
    print("\n📁 项目结构已生成，请将完整代码填入对应文件")
    print("📦 运行 pip install -r requirements.txt 安装依赖")
    print("🚀 运行 python app.py 启动软件")


if __name__ == '__main__':
    main()