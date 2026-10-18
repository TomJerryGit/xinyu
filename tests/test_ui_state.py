# -*- coding: utf-8 -*-
"""UI 状态持久化（pywebview localStorage 不可用时的后端兜底）。"""
import json

import api


def test_ui_state_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "app_path", lambda *parts: str(tmp_path.joinpath(*parts)))
    obj = api.API.__new__(api.API)
    assert obj.get_ui_state() == {}
    assert obj.save_ui_state(json.dumps({"theme": "dark", "last_nav": "data"})) is True
    assert obj.get_ui_state()["theme"] == "dark"
    assert obj.get_ui_state()["last_nav"] == "data"
    assert obj.save_ui_state("not-json") is False
    assert obj.save_ui_state(json.dumps(["bad"])) is False


def test_ui_state_only_allowed_keys(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "app_path", lambda *parts: str(tmp_path.joinpath(*parts)))
    obj = api.API.__new__(api.API)
    assert obj.save_ui_state(json.dumps({"theme": "paper", "evil": "x"})) is True
    data = obj.get_ui_state()
    assert data["theme"] == "paper"
    assert "evil" not in data
