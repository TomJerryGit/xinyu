# -*- coding: utf-8 -*-
"""版本信息唯一来源。"""

VERSION = "9.3.0"
CODENAME = "文脉相承"
APP_NAME = "心语"
AUTHOR = "hedongwei"


def version_tuple(value: str = VERSION):
    """把 ``9.1.0`` 之类的版本号转换成可比较的整数元组。"""
    parts = []
    for piece in str(value).strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)
