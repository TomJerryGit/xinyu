# -*- coding: utf-8 -*-
"""统一错误契约。

所有通过 js_api 暴露的方法都会被 :func:`install_api_guards` 包装：
未捕获异常统一返回 ``{"__error__": {"code", "message"}}``，
前端 ``callApi`` 会把它转成带 code 的 Error，便于给出恢复建议。
"""
import inspect
import sqlite3
from functools import wraps

from logger import log

ERROR_CODES = {
    "INVALID_INPUT": "参数不合法",
    "INVALID_JSON": "数据格式错误",
    "FILE_NOT_FOUND": "文件不存在",
    "FILE_PERMISSION": "文件权限不足",
    "DB_BUSY": "数据库正忙，请稍后重试",
    "DB_ERROR": "数据库操作失败",
    "TIMEOUT": "操作超时",
    "NETWORK": "网络连接失败",
    "AI_ERROR": "AI 服务暂时不可用",
    "INTERNAL": "内部错误",
}


class ApiError(Exception):
    def __init__(self, code: str, message: str = ""):
        self.code = code if code in ERROR_CODES else "INTERNAL"
        super().__init__(message or ERROR_CODES[self.code])


def classify(exc: Exception) -> str:
    if isinstance(exc, ApiError):
        return exc.code
    if isinstance(exc, (ValueError, TypeError, KeyError, IndexError)):
        return "INVALID_INPUT"
    if isinstance(exc, FileNotFoundError):
        return "FILE_NOT_FOUND"
    if isinstance(exc, PermissionError):
        return "FILE_PERMISSION"
    if isinstance(exc, TimeoutError):
        return "TIMEOUT"
    if isinstance(exc, sqlite3.OperationalError):
        text = str(exc).lower()
        if "locked" in text or "busy" in text:
            return "DB_BUSY"
        return "DB_ERROR"
    if isinstance(exc, sqlite3.Error):
        return "DB_ERROR"
    text = str(exc).lower()
    if "timeout" in text or "timed out" in text:
        return "TIMEOUT"
    if "connection" in text or "network" in text:
        return "NETWORK"
    if "api key" in text or "401" in text or "rate" in text:
        return "AI_ERROR"
    return "INTERNAL"


def error_envelope(code: str, message: str = "", detail: str = ""):
    return {
        "__error__": {
            "code": code,
            "message": message or ERROR_CODES.get(code, ERROR_CODES["INTERNAL"]),
            "detail": str(detail)[:300],
        }
    }


def api_guard(func):
    if getattr(func, "__api_guarded__", False):
        return func

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - 边界处统一转错误契约
            code = classify(exc)
            log("error", f"{func.__name__} 失败[{code}]: {str(exc)[:240]}")
            return error_envelope(code, ERROR_CODES.get(code, ""), exc)

    wrapper.__api_guarded__ = True  # type: ignore[attr-defined]
    return wrapper


def install_api_guards(cls):
    """把类上所有公开方法包一层错误契约（幂等）。"""
    for name in dir(cls):
        if name.startswith("_"):
            continue
        attribute = getattr(cls, name, None)
        if inspect.isfunction(attribute) and not getattr(attribute, "__api_guarded__", False):
            setattr(cls, name, api_guard(attribute))
    return cls
