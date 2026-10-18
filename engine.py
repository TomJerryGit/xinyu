# -*- coding: utf-8 -*-
"""心语 AI 引擎模块。

支持云端 OpenAI 兼容接口与本地 llama.cpp 模型，并提供 API Key 的
Fernet 对称加密工具。

设计要点：
* 用量统计的刷盘在锁外执行，避免非重入锁自死锁；
* API Key 只以密文写入 ``data/settings.json``，密钥文件权限收紧；
* 所有路径基于项目根目录，避免工作目录变化导致读写错位。
"""
import json
import os
import threading
import time
from abc import ABC, abstractmethod

from utils import app_path, ensure_dir, secure_file_permissions

# ========== 加密解密工具（惰性加载 cryptography） ==========
_KEY_FILE = app_path("data", ".secret.key")
_fernet = None
_fernet_lock = threading.Lock()


def _get_or_create_key() -> bytes:
    """从安全文件读取或生成密钥（权限设置为仅当前用户可读写）。"""
    from cryptography.fernet import Fernet

    if os.path.exists(_KEY_FILE):
        with open(_KEY_FILE, "rb") as handle:
            key = handle.read().strip()
        if key:
            return key
    key = Fernet.generate_key()
    ensure_dir(_KEY_FILE)
    with open(_KEY_FILE, "wb") as handle:
        handle.write(key)
    secure_file_permissions(_KEY_FILE)
    return key


def _get_fernet():
    global _fernet
    if _fernet is None:
        from cryptography.fernet import Fernet

        with _fernet_lock:
            if _fernet is None:
                _fernet = Fernet(_get_or_create_key())
    return _fernet


def encrypt(text: str) -> str:
    """加密文本，返回可直接存入 JSON 的字符串。"""
    if not text:
        return ""
    return _get_fernet().encrypt(str(text).encode("utf-8")).decode("ascii")


def decrypt(encoded: str) -> str:
    """解密文本；密文损坏或密钥不匹配时返回空字符串。"""
    if not encoded:
        return ""
    try:
        return _get_fernet().decrypt(str(encoded).encode("ascii")).decode("utf-8")
    except Exception:
        return ""


class BaseEngine(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str:
        """根据提示词生成文本。"""


class CloudEngine(BaseEngine):
    """OpenAI 兼容的云端引擎（DeepSeek / 通义 / 智谱 / Moonshot / OpenAI）。"""

    PROVIDERS = {
        "deepseek": {
            "name": "DeepSeek",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "models": ["deepseek-chat", "deepseek-reasoner"],
        },
        "qwen": {
            "name": "通义千问",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "model": "qwen-plus",
            "models": ["qwen-plus", "qwen-turbo", "qwen-max"],
        },
        "zhipu": {
            "name": "智谱AI",
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "model": "glm-4-flash",
            "models": ["glm-4-flash", "glm-4-plus", "glm-4-air"],
        },
        "moonshot": {
            "name": "Moonshot",
            "base_url": "https://api.moonshot.cn/v1",
            "model": "moonshot-v1-8k",
            "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        },
        "openai": {
            "name": "OpenAI",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o-mini",
            "models": ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"],
        },
    }

    def __init__(self, provider=None, api_key=None, model=None):
        from openai import OpenAI

        self.settings = self._load_settings()
        api_cfg = self.settings.get("api", {}) or {}

        if provider is None:
            provider = api_cfg.get("provider", "deepseek")
        if provider not in self.PROVIDERS:
            provider = "deepseek"
        cfg = self.PROVIDERS[provider]

        self.provider = provider
        self.provider_name = cfg["name"]
        self.model = self._resolve_model(model or api_cfg.get("model"), cfg)
        self.temperature = float(api_cfg.get("temperature", 0.9))
        self.max_tokens = int(api_cfg.get("max_tokens", 512))
        self.timeout = max(5, int(api_cfg.get("timeout", 30)))
        self.retry = max(0, int(api_cfg.get("retry", 2)))

        if api_key:
            self.api_key = api_key
        else:
            encoded = api_cfg.get("api_key", "")
            self.api_key = decrypt(encoded) or os.getenv("DEEPSEEK_API_KEY", "")

        self.client = OpenAI(
            api_key=self.api_key or "invalid-key",
            base_url=cfg["base_url"],
            timeout=self.timeout,
            max_retries=0,  # 重试由本模块控制，便于统一退避
        )

        self.current_task = ""
        self.on_usage = None

        # 用量内存聚合：缓冲 + 锁，仅在锁内做内存操作
        self._usage_buffer = []
        self._usage_lock = threading.Lock()
        self._last_flush_time = time.time()
        self._flush_interval = 30
        self._flush_threshold = 100

    # ---------- 配置 ----------
    @staticmethod
    def _resolve_model(model, cfg) -> str:
        """确保模型名属于当前服务商，否则回退到该服务商默认模型。"""
        if model and model in cfg.get("models", []):
            return model
        return cfg["model"]

    @staticmethod
    def _load_settings() -> dict:
        path = app_path("data", "settings.json")
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def is_configured(self) -> bool:
        """是否已配置可用的 API Key。"""
        return bool(self.api_key)

    # ---------- 用量 ----------
    def _record_usage(self, tokens: int) -> None:
        """记录一次调用，必要时在锁外触发刷盘。"""
        should_flush = False
        with self._usage_lock:
            self._usage_buffer.append({"time": time.time(), "tokens": int(tokens)})
            should_flush = (
                len(self._usage_buffer) >= self._flush_threshold
                or time.time() - self._last_flush_time >= self._flush_interval
            )
        if should_flush:
            self._flush_usage()

    def _flush_usage(self) -> None:
        """把缓冲写入 settings.json 的 usage 字段。

        注意：写文件在锁外进行，失败时把记录放回缓冲，避免丢数据。
        """
        with self._usage_lock:
            if not self._usage_buffer:
                return
            pending = list(self._usage_buffer)
            self._usage_buffer.clear()
            self._last_flush_time = time.time()

        try:
            settings = self._load_settings()
            usage = settings.get("usage", {}) or {}
            now_str = time.strftime("%Y-%m")
            if usage.get("last_reset") != now_str:
                usage = {"monthly_calls": 0, "monthly_tokens": 0, "last_reset": now_str}

            usage["monthly_calls"] = int(usage.get("monthly_calls", 0)) + len(pending)
            usage["monthly_tokens"] = int(usage.get("monthly_tokens", 0)) + sum(
                int(item.get("tokens", 0)) for item in pending
            )
            settings["usage"] = usage

            path = app_path("data", "settings.json")
            ensure_dir(path)
            tmp_path = path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as handle:
                json.dump(settings, handle, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)
            secure_file_permissions(path)
        except Exception as exc:
            with self._usage_lock:
                self._usage_buffer[:0] = pending
            print(f"刷新用量失败: {exc}")

    def _report_usage(self, prompt: str, response: str) -> None:
        if not self.on_usage:
            return
        # 没有真实 usage 字段时按字符数估算，仅用于界面展示趋势
        prompt_tokens = max(1, len(prompt) // 2)
        completion_tokens = max(1, len(response) // 2)
        try:
            self.on_usage(
                task=self.current_task,
                model=self.model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        except Exception:
            pass

    # ---------- 错误处理 ----------
    @staticmethod
    def _handle_error(exc: Exception) -> str:
        err = str(exc).lower()
        if "api_key" in err or "auth" in err or "unauthorized" in err or "401" in err:
            return "API Key无效，请检查设置"
        if "connection" in err or "timeout" in err or "timed out" in err:
            return "网络连接失败或超时，请检查网络"
        if "quota" in err or "rate" in err or "429" in err:
            return "请求频率过高或额度不足，请稍后重试"
        if "content" in err or "filter" in err or "safety" in err:
            return "内容被安全策略拦截，请调整提示"
        if "model" in err and ("not found" in err or "does not exist" in err):
            return "模型不可用，请在设置中更换模型"
        return f"AI请求失败: {str(exc)[:200]}"

    # ---------- 生成 ----------
    def _metric(self, success, prompt, result, started):
        try:
            from metrics import record

            prompt_tokens = max(1, len(prompt) // 2)
            completion_tokens = max(1, len(result) // 2)
            record(
                "ai_call",
                task=self.current_task or "generate",
                model=self.model,
                success=bool(success),
                latency_ms=round((time.perf_counter() - started) * 1000, 1),
                tokens=prompt_tokens + completion_tokens,
                cost=round(prompt_tokens / 1000 * 0.001 + completion_tokens / 1000 * 0.002, 6),
                error="" if success else str(result)[:120],
            )
        except Exception:
            pass

    def generate(self, prompt: str) -> str:
        """带重试与指数退避的生成方法；失败时返回可读的中文错误信息。"""
        started = time.perf_counter()
        last_error = None
        for attempt in range(self.retry + 1):
            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )
                result = (resp.choices[0].message.content or "").strip()
                if result:
                    self._record_usage(len(prompt) // 2 + self.max_tokens // 2)
                    self._report_usage(prompt, result)
                    self._metric(True, prompt, result, started)
                    return result
                last_error = RuntimeError("模型返回空内容")
            except Exception as exc:  # noqa: BLE001 - 需要把 SDK 异常统一转成文案
                last_error = exc
            if attempt < self.retry:
                time.sleep(2 ** attempt)
        error = self._handle_error(last_error or RuntimeError("未知错误"))
        self._metric(False, prompt, error, started)
        return error

    def chat(self, messages) -> str:
        """多轮对话；失败时抛出异常，由调用方决定如何提示。"""
        started = time.perf_counter()
        prompt_str = "".join(str(m.get("content", "")) for m in messages)
        last_error = None
        for attempt in range(self.retry + 1):
            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.8,
                    max_tokens=800,
                )
                result = (resp.choices[0].message.content or "").strip()
                if not result:
                    raise RuntimeError("模型返回空内容")
                self._record_usage(800)
                self._report_usage(prompt_str, result)
                self._metric(True, prompt_str, result, started)
                return result
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt < self.retry:
                    time.sleep(2 ** attempt)
        error = self._handle_error(last_error or RuntimeError("未知错误"))
        self._metric(False, prompt_str, error, started)
        raise RuntimeError(error)

    def test_connection(self, key: str, provider: str = "deepseek"):
        """用给定 Key 做一次最小请求，返回 ``(ok, message)``。"""
        from openai import OpenAI

        cfg = self.PROVIDERS.get(provider, self.PROVIDERS["deepseek"])
        try:
            client = OpenAI(api_key=key, base_url=cfg["base_url"], timeout=10, max_retries=0)
            client.chat.completions.create(
                model=cfg["model"],
                messages=[{"role": "user", "content": "测试"}],
                max_tokens=5,
            )
            return True, "连接成功！Key有效"
        except Exception as exc:  # noqa: BLE001
            return False, self._handle_error(exc)[:120]


class LazyEngine(BaseEngine):
    """延迟创建 CloudEngine。

    ``import openai`` + 客户端初始化约 3.5 秒，放到首屏之后。
    首屏只读取设置（provider/model/has_key），第一次 AI 调用时才真正构造。
    """

    def __init__(self, provider=None, api_key=None, model=None):
        self._settings = CloudEngine._load_settings()
        api_cfg = self._settings.get("api", {}) or {}
        self._provider = provider or api_cfg.get("provider", "deepseek")
        if self._provider not in CloudEngine.PROVIDERS:
            self._provider = "deepseek"
        self._provider_name = CloudEngine.PROVIDERS[self._provider]["name"]
        self._api_key_override = api_key
        self._model_override = CloudEngine._resolve_model(
            model or api_cfg.get("model"), CloudEngine.PROVIDERS[self._provider]
        )
        self._delegate = None
        self._lock = threading.Lock()
        self._current_task = ""
        self._on_usage = None

    @property
    def provider(self):
        return self._provider

    @property
    def provider_name(self):
        return self._provider_name

    @property
    def model(self):
        if self._delegate is not None:
            return self._delegate.model
        return self._model_override

    @model.setter
    def model(self, value):
        self._model_override = value
        if self._delegate is not None:
            self._delegate.model = value

    @property
    def current_task(self):
        return self._current_task

    @current_task.setter
    def current_task(self, value):
        self._current_task = value or ""
        if self._delegate is not None:
            self._delegate.current_task = self._current_task

    @property
    def on_usage(self):
        return self._on_usage

    @on_usage.setter
    def on_usage(self, value):
        self._on_usage = value
        if self._delegate is not None:
            self._delegate.on_usage = value

    def _ensure(self):
        if self._delegate is not None:
            return self._delegate
        with self._lock:
            if self._delegate is None:
                delegate = CloudEngine(
                    provider=self._provider,
                    api_key=self._api_key_override,
                    model=self._model_override,
                )
                delegate.current_task = self._current_task
                delegate.on_usage = self._on_usage
                self._delegate = delegate
        return self._delegate

    @property
    def api_key(self):
        if self._api_key_override:
            return self._api_key_override
        api_cfg = self._settings.get("api", {}) or {}
        return decrypt(api_cfg.get("api_key", "")) or os.getenv("DEEPSEEK_API_KEY", "")

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def generate(self, prompt: str) -> str:
        delegate = self._ensure()
        delegate.current_task = self._current_task
        return delegate.generate(prompt)

    def chat(self, messages) -> str:
        delegate = self._ensure()
        delegate.current_task = self._current_task
        return delegate.chat(messages)

    def test_connection(self, key: str, provider: str = "deepseek"):
        return self._ensure().test_connection(key, provider)


class LocalEngine(BaseEngine):
    """本地 GGUF 模型引擎（需要 llama-cpp-python 与模型文件）。"""

    def __init__(self, model_path=None):
        from llama_cpp import Llama

        path = model_path or app_path("models", "poem.gguf")
        if not os.path.exists(path):
            raise FileNotFoundError(f"未找到本地模型: {path}")
        self.model = Llama(model_path=path, n_ctx=512, verbose=False)

    def generate(self, prompt: str) -> str:
        output = self.model(prompt, max_tokens=256, stop=["用户："])
        return (output["choices"][0].get("text") or "").strip()
