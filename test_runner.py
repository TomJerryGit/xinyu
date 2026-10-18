# -*- coding: utf-8 -*-
"""心语内置自检套件（不依赖网络，可在界面里直接运行）。

更完整的回归测试见 ``tests/``（pytest）。
"""
import os
import shutil
import sys
import tempfile

from utils import normalize_path, safe_json_load, safe_json_save


class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.messages = []

    def _assert(self, condition, name):
        if condition:
            self.passed += 1
            self.messages.append(f"  ✅ {name}")
        else:
            self.failed += 1
            self.messages.append(f"  ❌ {name}")

    def run(self):
        self.messages.append("=" * 52)
        self.messages.append("心语自检套件")
        self.messages.append("=" * 52)
        for test in (
            self._test_encryption,
            self._test_utils,
            self._test_database,
            self._test_poetry,
            self._test_cache,
            self._test_scoring,
            self._test_json_parsing,
        ):
            try:
                test()
            except Exception as exc:  # noqa: BLE001 - 自检需要汇总而非中断
                self._assert(False, f"{test.__name__} 异常: {str(exc)[:120]}")
        self.messages.append("=" * 52)
        self.messages.append(f"结果: {self.passed} 通过, {self.failed} 失败")
        print("\n".join(self.messages))
        return self.failed == 0

    # ---------- 加密 ----------
    def _test_encryption(self):
        self.messages.append("\n📦 加密解密")
        from engine import decrypt, encrypt

        original = "test-key-12345"
        encrypted = encrypt(original)
        self._assert(encrypted != original, "加密后不为明文")
        self._assert(decrypt(encrypted) == original, "解密还原正确")
        self._assert(decrypt("broken-cipher") == "", "损坏密文安全返回空串")

    # ---------- 工具 ----------
    def _test_utils(self):
        self.messages.append("\n📦 工具函数")
        tmp_dir = tempfile.mkdtemp()
        try:
            path = os.path.join(tmp_dir, "test.json")
            data = {"name": "心语", "version": "9.1"}
            self._assert(safe_json_save(path, data), "JSON 原子保存成功")
            self._assert(safe_json_load(path) == data, "JSON 读取正确")

            escaped = normalize_path(os.path.join("..", "xinyu_evil", "a.txt"))
            self._assert(not escaped.endswith("a.txt"), "路径穿越被拦截")
            self._assert(normalize_path("data") != "", "合法相对路径可解析")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # ---------- 数据库 ----------
    def _test_database(self):
        self.messages.append("\n📦 数据库")
        from classics_database import ClassicsDatabase

        tmp_dir = tempfile.mkdtemp()
        db = None
        try:
            db = ClassicsDatabase(os.path.join(tmp_dir, "classics_test.db"))
            sample = {
                "id": "test_001",
                "title": "静夜思",
                "author": "李白",
                "dynasty": "唐",
                "category": "唐诗",
                "content": "床前明月光，疑是地上霜。举头望明月，低头思故乡。",
            }
            self._assert(db.insert(sample), "插入成功")
            self._assert(len(db.search(keyword="静夜思")) == 1, "搜索命中")
            self._assert(db.get_by_id("test_001")["title"] == "静夜思", "按 ID 获取")
            self._assert(db.insert(sample) and db.get_total_count() == 1, "重复 ID 幂等")

            bad = {"title": "", "content": ""}
            self._assert(db.insert(bad) is True, "缺字段仍可入库（由上层校验）")
        finally:
            if db:
                db.close()
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # ---------- 格律 ----------
    def _test_poetry(self):
        self.messages.append("\n📦 格律检测")
        from poetry_checker import check_jueju, check_lvshi, check_poem

        jueju = ["床前明月光", "疑是地上霜", "举头望明月", "低头思故乡"]
        result = check_jueju(jueju)
        self._assert(isinstance(result, (str, list)), "绝句返回合法类型")
        self._assert(check_jueju(jueju[:3]) == "需要四句", "三句提示正确")
        self._assert(check_jueju(["床前明月光", "疑是地上霜", "举头望明月", "低头思故乡", "多一句"]) == "需要四句", "五句提示正确")

        lvshi = ["国破山河在", "城春草木深", "感时花溅泪", "恨别鸟惊心", "烽火连三月", "家书抵万金", "白头搔更短", "浑欲不胜簪"]
        lvshi_result = check_lvshi(lvshi)
        self._assert(lvshi_result != "需要四句", "律诗按八句检测")
        self._assert(check_poem("五言律诗", lvshi) == lvshi_result, "check_poem 正确分发律诗")
        self._assert("暂不支持" in check_poem("如梦令", ["x"]), "词牌明确标注不支持")

    # ---------- 缓存 ----------
    def _test_cache(self):
        self.messages.append("\n📦 缓存")
        import time

        from cache_manager import FileCache

        tmp_dir = tempfile.mkdtemp()
        cache = None
        try:
            cache = FileCache(tmp_dir)
            cache.set("k", {"value": 42}, ttl=1)
            self._assert(cache.get("k") == {"value": 42}, "缓存读写正确")
            time.sleep(1.1)
            self._assert(cache.get("k") is None, "TTL 到期后失效")
        finally:
            if cache:
                cache.close()
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # ---------- 评分 ----------
    def _test_scoring(self):
        self.messages.append("\n📦 质量评分")
        from api import content_fingerprint, score_item

        good = {
            "title": "静夜思",
            "author": "李白",
            "dynasty": "唐",
            "content": "床前明月光，疑是地上霜。" * 5,
            "annotation": "注",
            "tags": "月,思乡",
            "translation": "译",
        }
        self._assert(score_item(good)["score"] >= 50, "完整条目评分达标")
        self._assert(score_item({"title": "", "content": ""})["score"] < 10, "空条目低分")
        self._assert(
            content_fingerprint("静夜思", "李白", "床前明月光，疑是地上霜。")
            == content_fingerprint("静夜思", "李白", "床前明月光 疑是地上霜"),
            "指纹忽略标点空白",
        )

    # ---------- JSON 解析 ----------
    def _test_json_parsing(self):
        self.messages.append("\n📦 JSON 兜底解析")
        from json_utils import parse_json_object

        self._assert(parse_json_object('{"a": 1}')["a"] == 1, "纯 JSON")
        self._assert(parse_json_object('```json\n{"a": 2}\n```')["a"] == 2, "围栏 JSON")
        self._assert(parse_json_object('说明文字 {"a": 3} 结尾')["a"] == 3, "前后杂字")
        self._assert(parse_json_object("not json", {"a": 0})["a"] == 0, "失败回退默认值")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    raise SystemExit(0 if TestRunner().run() else 1)
