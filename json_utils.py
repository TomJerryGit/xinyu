# -*- coding: utf-8 -*-
"""JSON 兜底解析：容忍 ```json 围栏与前后说明文字。"""
import json
import re


def parse_json_object(text, default=None):
    default = {} if default is None else default
    if not isinstance(text, str) or not text.strip():
        return default
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else default
    except (ValueError, TypeError):
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(cleaned[start : end + 1])
            return data if isinstance(data, dict) else default
        except (ValueError, TypeError):
            return default
    return default
