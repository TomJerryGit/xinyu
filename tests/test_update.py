# -*- coding: utf-8 -*-
"""更新签名与灰度测试。"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import updater
from updater import signing_payload, verify_signature


def _keypair():
    private = Ed25519PrivateKey.generate()
    public_raw = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return private, base64.b64encode(public_raw).decode()


def test_signature_roundtrip():
    private, public_b64 = _keypair()
    version, url, sha = "9.3.0", "https://example.com/Xinyu.exe", "a" * 64
    signature = base64.b64encode(private.sign(signing_payload(version, url, sha))).decode()
    assert verify_signature(version, url, sha, signature, public_b64)
    assert not verify_signature(version, url, "b" * 64, signature, public_b64)
    assert not verify_signature(version, url, sha, signature, "")
    rollback_url, rollback_sha = "https://example.com/old.exe", "c" * 64
    rollback_sig = base64.b64encode(
        private.sign(signing_payload(version, url, sha, rollback_url, rollback_sha))
    ).decode()
    assert verify_signature(version, url, sha, rollback_sig, public_b64, rollback_url, rollback_sha)
    assert not verify_signature(version, url, sha, rollback_sig, public_b64, rollback_url, "d" * 64)


def test_check_update_verifies_signed_manifest(monkeypatch):
    private, public_b64 = _keypair()
    latest = "9.4.0"
    url = "https://example.com/Xinyu-Setup-9.4.0.exe"
    sha = "e" * 64
    signature = base64.b64encode(private.sign(signing_payload(latest, url, sha))).decode()
    manifest = {
        "version": latest, "url": url, "sha256": sha,
        "signature": signature, "rollout": 100,
    }

    class Response:
        status_code = 200

        def json(self):
            return manifest

    monkeypatch.setattr(updater, "BUILTIN_UPDATE_PUBLIC_KEY", public_b64)
    monkeypatch.setattr(updater.requests, "get", lambda *args, **kwargs: Response())
    manager = updater.Updater()
    manager.update_url = "https://example.com/update.json"
    result = manager.check_update()
    assert result["has_update"] is True
    assert result["signature_verified"] is True
    assert result["latest"] == latest


def test_check_update_rejects_bad_signature(monkeypatch):
    _, public_b64 = _keypair()
    manifest = {
        "version": "9.4.0",
        "url": "https://example.com/Xinyu-Setup-9.4.0.exe",
        "sha256": "e" * 64,
        "signature": "invalid",
        "rollout": 100,
    }

    class Response:
        status_code = 200

        def json(self):
            return manifest

    monkeypatch.setattr(updater, "BUILTIN_UPDATE_PUBLIC_KEY", public_b64)
    monkeypatch.setattr(updater.requests, "get", lambda *args, **kwargs: Response())
    manager = updater.Updater()
    manager.update_url = "https://example.com/update.json"
    result = manager.check_update()
    assert result["has_update"] is False
    assert "签名" in result["message"]


def test_rollout_is_stable(monkeypatch, tmp_path):
    monkeypatch.setattr(updater, "app_path", lambda *parts: str(tmp_path.joinpath(*parts)))
    manager = updater.Updater()
    monkeypatch.setattr(manager, "_install_id", lambda: "device-123")
    assert manager.in_rollout(100, "9.3.0") is True
    assert manager.in_rollout(0, "9.3.0") is False
    first = manager.in_rollout(50, "9.3.0")
    second = manager.in_rollout(50, "9.3.0")
    assert first == second
