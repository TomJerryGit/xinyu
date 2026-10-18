# -*- coding: utf-8 -*-
"""前后端契约测试。

保证 ``main.js`` 调用的每个后端方法都真实存在，``index.html`` 里
每个内联事件都能在 JS 中找到实现——这两类问题此前都曾静默失效。
"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _api_methods():
    tree = ast.parse((ROOT / "api.py").read_text(encoding="utf-8"))
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    api_class = classes["API"]
    bases = [base.id for base in api_class.bases if isinstance(base, ast.Name)]
    methods = set()
    for name in bases + ["API"]:
        node = classes.get(name)
        if not node:
            continue
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.add(item.name)
    return {name for name in methods if not name.startswith("_")}


def _js_calls():
    source = (ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")
    called = set(re.findall(r"""callApi\(\s*['"]([A-Za-z_]\w*)['"]""", source))
    called |= set(re.findall(r"pywebview\.api\.([A-Za-z_]\w*)\s*\(", source))
    return called


def _js_functions():
    source = (ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")
    return set(re.findall(r"(?:^|\n)\s*(?:async\s+)?function\s+([A-Za-z_]\w*)\s*\(", source))


def test_every_frontend_call_exists_in_backend():
    missing = _js_calls() - _api_methods()
    assert not missing, f"前端调用了不存在的后端方法: {sorted(missing)}"


def test_every_inline_handler_exists_in_js():
    html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    handlers = re.findall(r'on(?:click|change|input|keydown)="([^"]+)"', html)
    called = set()
    for handler in handlers:
        called |= set(re.findall(r"([A-Za-z_]\w*)\s*\(", handler))
    builtins = {
        "if",
        "document",
        "event",
        "this",
        "return",
        "value",
        "trim",
        "contains",
        "alert",
        "getElementById",
        "parseInt",
        "parseFloat",
        "confirm",
        "prompt",
        "String",
        "Number",
        "open",
        "preventDefault",
        "stopPropagation",
    }
    missing = called - _js_functions() - builtins
    assert not missing, f"HTML 内联事件缺少 JS 实现: {sorted(missing)}"


def test_critical_p0_methods_present():
    methods = _api_methods()
    for name in ("polish_line", "transform_style", "confirm_import_candidates", "save_api_settings"):
        assert name in methods


def test_requirements_declare_runtime_dependencies():
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    for package in ("pywebview", "openai", "cryptography", "requests", "pypinyin", "pillow"):
        assert package in text, f"requirements.txt 缺少 {package}"
