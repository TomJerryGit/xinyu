# -*- coding: utf-8 -*-
"""灰度比例：修改 update.json 的 rollout（5 → 25 → 100）。

    python tools/set_rollout.py --file dist/update.json --rollout 5

修改 rollout 不需要重新签名（签名覆盖 version/url/sha/rollback，不覆盖灰度比例）。
"""
import argparse
import json
import os
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=os.path.join("dist", "update.json"))
    parser.add_argument("--rollout", type=int, required=True, choices=range(0, 101))
    args = parser.parse_args()
    with open(args.file, "r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    data["rollout"] = args.rollout
    temp = args.file + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(temp, args.file)
    print(f"{args.file}: rollout={args.rollout}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
