# -*- coding: utf-8 -*-
"""AI Gateway 预算与结构化输出测试。"""
import json

import pytest

import ai_gateway


class FakeCache:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, ttl=0):
        self.data[key] = value


class FakeEngine:
    provider = "deepseek"
    model = "deepseek-chat"

    def __init__(self, replies):
        self.replies = list(replies)

    def generate(self, prompt):
        return self.replies.pop(0) if self.replies else ""


class Owner:
    def __init__(self, engine):
        self.engine = engine
        self.cache_mgr = FakeCache()


def test_gateway_structured_repairs(monkeypatch, tmp_path):
    monkeypatch.setattr(ai_gateway, "app_path", lambda *parts: str(tmp_path.joinpath(*parts)))
    owner = Owner(FakeEngine(["not json", json.dumps({"background": "唐", "text_analysis": "好"})]))
    gateway = ai_gateway.AIGateway(owner)
    data = gateway.generate_structured("analysis", "prompt", required=["background", "text_analysis"])
    assert data["background"] == "唐"
    assert gateway.budget_status()["calls"] == 2


def test_gateway_budget_limit(monkeypatch, tmp_path):
    monkeypatch.setattr(ai_gateway, "app_path", lambda *parts: str(tmp_path.joinpath(*parts)))
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "settings.json").write_text(json.dumps({"ai": {"daily_budget": 0.000005}}), encoding="utf-8")
    owner = Owner(FakeEngine(["x"]))
    gateway = ai_gateway.AIGateway(owner)
    gateway.generate("analysis", "prompt")
    with pytest.raises(ai_gateway.ApiError) as exc:
        gateway.generate("analysis", "prompt")
    assert exc.value.code == "AI_ERROR"
