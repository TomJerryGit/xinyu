# -*- coding: utf-8 -*-
"""生成/签名心语更新清单。

初始化密钥（只做一次，私钥不要提交到仓库）：

    python tools/sign_manifest.py init --key update_private.key

签名：

    python tools/sign_manifest.py sign --key update_private.key --manifest dist/update.json

公钥输出后填入 updater.BUILTIN_UPDATE_PUBLIC_KEY，或在构建环境设置
XINYU_UPDATE_PUBLIC_KEY。
"""
import argparse
import base64
import hashlib
import json
import os
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from updater import signing_payload  # noqa: E402


def _private_raw(private):
    return private.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _public_raw(private):
    return private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def init_key(path):
    private = Ed25519PrivateKey.generate()
    with open(path, "wb") as handle:
        handle.write(base64.b64encode(_private_raw(private)))
    print("private_key:", os.path.abspath(path))
    print("public_key:", base64.b64encode(_public_raw(private)).decode())
    print("请把 public_key 填入 updater.BUILTIN_UPDATE_PUBLIC_KEY 或 XINYU_UPDATE_PUBLIC_KEY")


def load_private(path):
    raw = base64.b64decode(open(path, "rb").read())
    return Ed25519PrivateKey.from_private_bytes(raw)


def sign_manifest(key_path, manifest_path):
    private = load_private(key_path)
    with open(manifest_path, "r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    version = str(data.get("version", ""))
    url = str(data.get("url", ""))
    sha256 = str(data.get("sha256", "")).lower()
    if not (version and url and sha256):
        raise SystemExit("manifest 需要 version / url / sha256")
    rollback = data.get("rollback") if isinstance(data.get("rollback"), dict) else {}
    signature = private.sign(
        signing_payload(
            version, url, sha256,
            str(rollback.get("url", "")), str(rollback.get("sha256", "")),
        )
    )
    data["signature"] = base64.b64encode(signature).decode()
    data["key_id"] = hashlib.sha256(_public_raw(private)).hexdigest()[:12]
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    print("signed:", manifest_path)
    print("public_key:", base64.b64encode(_public_raw(private)).decode())


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--key", default="update_private.key")
    sign = sub.add_parser("sign")
    sign.add_argument("--key", required=True)
    sign.add_argument("--manifest", required=True)
    args = parser.parse_args()
    if args.command == "init":
        init_key(args.key)
    else:
        sign_manifest(args.key, args.manifest)


if __name__ == "__main__":
    main()
