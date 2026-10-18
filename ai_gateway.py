# -*- coding: utf-8 -*-
"""AI Gateway：预算、路由、结构化输出、缓存与修复重试。

所有 AI 调用应尽量经由这里，而不是直接 ``engine.generate``：
* 每日预算与熔断；
* 按任务选择模型（需属于当前 provider）；
* JSON 结构化输出 + 一次修复；
* 结果缓存；
* 与本地指标、用量日志保持一致。
"""
import hashlib
import threading
from datetime import date

from errors import ApiError
from json_utils import parse_json_object
from utils import app_path, safe_json_load, safe_json_save

_DEFAULT_DAILY_BUDGET = 5.0


class AIGateway:
    def __init__(self, owner):
        self.owner = owner
        self._lock = threading.Lock()

    # ---------- 预算 ----------
    @property
    def _budget_path(self):
        return app_path("data", "ai_budget.json")

    def _daily_budget(self) -> float:
        settings = safe_json_load(app_path("data", "settings.json"), {})
        try:
            return max(0.0, float((settings.get("ai") or {}).get("daily_budget", _DEFAULT_DAILY_BUDGET)))
        except (TypeError, ValueError):
            return _DEFAULT_DAILY_BUDGET

    def _budget_state(self):
        today = date.today().isoformat()
        state = safe_json_load(self._budget_path, {}) or {}
        if state.get("date") != today:
            state = {"date": today, "spent": 0.0, "calls": 0}
        return state

    def _save_budget(self, state):
        safe_json_save(self._budget_path, state)

    def budget_status(self):
        state = self._budget_state()
        daily = self._daily_budget()
        return {
            "date": state.get("date"),
            "spent": round(float(state.get("spent", 0)), 4),
            "calls": int(state.get("calls", 0)),
            "daily_budget": daily,
            "remaining": round(max(0.0, daily - float(state.get("spent", 0))), 4) if daily else None,
        }

    def _charge(self, cost: float):
        with self._lock:
            state = self._budget_state()
            state["spent"] = round(float(state.get("spent", 0)) + max(0.0, float(cost)), 6)
            state["calls"] = int(state.get("calls", 0)) + 1
            self._save_budget(state)

    def _check_budget(self):
        daily = self._daily_budget()
        if not daily:
            return
        state = self._budget_state()
        if float(state.get("spent", 0)) >= daily:
            raise ApiError("AI_ERROR", "今日 AI 预算已用完，可在设置中调整 ai.daily_budget")

    # ---------- 路由 ----------
    def _routing(self):
        settings = safe_json_load(app_path("data", "settings.json"), {})
        routing = (settings.get("ai") or {}).get("routing") or {}
        return routing if isinstance(routing, dict) else {}

    def _routed_model(self, task, override=None):
        if override:
            return override
        model = self._routing().get(task)
        if not model:
            return None
        engine = self.owner.engine
        provider = getattr(engine, "provider", "")
        try:
            from engine import CloudEngine

            allowed = CloudEngine.PROVIDERS.get(provider, {}).get("models", [])
            return model if model in allowed else None
        except Exception:
            return None

    # ---------- 生成 ----------
    @staticmethod
    def _estimate_cost(prompt: str, result: str) -> float:
        tokens = max(1, len(prompt) // 2) + max(1, len(result) // 2)
        return tokens / 1000 * 0.002

    def generate(self, task: str, prompt: str, model=None, ttl=0):
        self._check_budget()
        engine = self.owner.engine
        routed = self._routed_model(task, model)
        old_model = engine.model
        cache_key = None
        if ttl and getattr(self.owner, "cache_mgr", None):
            digest = hashlib.sha256(f"{task}|{routed or old_model}|{prompt}".encode("utf-8")).hexdigest()
            cache_key = f"ai:{digest}"
            cached = self.owner.cache_mgr.get(cache_key)
            if cached is not None:
                return cached
        try:
            if routed:
                engine.model = routed
            result = engine.generate(prompt)
        finally:
            if routed:
                engine.model = old_model
        cost = self._estimate_cost(prompt, result or "")
        success = bool(result) and not str(result).startswith("AI请求失败") and "API Key无效" not in str(result)
        if success:
            self._charge(cost)
        if success and cache_key and getattr(self.owner, "cache_mgr", None):
            self.owner.cache_mgr.set(cache_key, result, ttl=ttl)
        return result

    def generate_structured(self, task, prompt, required=None, model=None, ttl=3600, retries=1):
        """返回 dict；JSON 解析失败或缺少字段时自动修复一次。"""
        required = list(required or [])
        cache_key = None
        if ttl and getattr(self.owner, "cache_mgr", None):
            digest = hashlib.sha256(f"json|{task}|{prompt}|{','.join(required)}".encode("utf-8")).hexdigest()
            cache_key = f"ai:json:{digest}"
            cached = self.owner.cache_mgr.get(cache_key)
            if isinstance(cached, dict):
                return cached

        text = self.generate(task, prompt, model=model, ttl=0)
        data = parse_json_object(text, {})
        if not self._valid(data, required):
            repair = (
                "你上一次的输出不是合法 JSON 或缺少字段。请只输出一个 JSON 对象，不要解释。"
                f"必须包含字段：{', '.join(required) if required else '任意'}。\n"
                f"原始任务：{prompt}"
            )
            text = self.generate(task, repair, model=model, ttl=0)
            data = parse_json_object(text, {})
        if not self._valid(data, required):
            raise ApiError("AI_ERROR", "模型返回格式不正确，请重试或更换模型")
        if cache_key and getattr(self.owner, "cache_mgr", None):
            self.owner.cache_mgr.set(cache_key, data, ttl=ttl)
        return data

    @staticmethod
    def _valid(data, required):
        if not isinstance(data, dict) or not data:
            return False
        for key in required:
            if key not in data or data[key] in (None, "", [], {}):
                return False
        return True
