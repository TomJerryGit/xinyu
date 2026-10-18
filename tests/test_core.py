# -*- coding: utf-8 -*-
"""核心逻辑回归测试（pytest）。

运行：``pytest -q``
"""
import json
import threading
import time
import zipfile

import pytest


def test_normalize_path_blocks_prefix_escape():
    from utils import normalize_path

    escaped = normalize_path("..\\xinyu_evil\\a.txt")
    assert not escaped.endswith("a.txt"), escaped


def test_score_item_threshold():
    from api import score_item

    candidate = {
        "title": "静夜思",
        "author": "李白",
        "dynasty": "唐",
        "content": "床前明月光，疑是地上霜。" * 4,
        "tags": "唐诗,AI扩充",
    }
    assert score_item(candidate)["score"] >= 40
    assert score_item({})["score"] < 10


def test_html_web_mode_injects_shim():
    from html_ui import build_html

    html = build_html(web_mode=True, token="test-token-123")
    assert "__XINYU_WEB__" in html
    assert "test-token-123" in html
    assert "/api/" in html
    assert "<!-- INLINE_JS -->" not in html


def test_parse_json_object_variants():
    from json_utils import parse_json_object

    assert parse_json_object('{"a":1}')["a"] == 1
    assert parse_json_object('```json\n{"a":2}\n```')["a"] == 2
    assert parse_json_object('前缀 {"a":3} 后缀')["a"] == 3
    assert parse_json_object("坏数据", {"a": 4})["a"] == 4


def test_engine_usage_flush_does_not_deadlock(monkeypatch, tmp_path):
    import engine

    monkeypatch.setattr(engine, "app_path", lambda *parts: str(tmp_path.joinpath(*parts)))
    eng = engine.CloudEngine(api_key="unit-test-key")
    eng._last_flush_time = 0  # 强制触发刷盘

    worker = threading.Thread(target=eng._record_usage, args=(12,), daemon=True)
    worker.start()
    worker.join(timeout=5)
    assert not worker.is_alive(), "用量刷盘发生死锁"

    settings = json.loads((tmp_path / "data" / "settings.json").read_text(encoding="utf-8"))
    assert settings["usage"]["monthly_calls"] == 1


def test_api_usage_log_flush_does_not_deadlock(monkeypatch, tmp_path):
    import api

    monkeypatch.setattr(api, "app_path", lambda *parts: str(tmp_path.joinpath(*parts)))
    instance = object.__new__(api.API)
    instance._usage_log_buffer = [
        {"timestamp": "2026-01-01 00:00:00", "task": "t", "model": "m", "total_tokens": 1, "cost": 0.0}
        for _ in range(199)
    ]
    instance._usage_log_lock = threading.Lock()

    worker = threading.Thread(
        target=instance._log_usage, args=("t", "m", 1, 1), daemon=True
    )
    worker.start()
    worker.join(timeout=5)
    assert not worker.is_alive(), "用量日志刷盘发生死锁"

    logs = json.loads((tmp_path / "data" / "usage_log.json").read_text(encoding="utf-8"))
    assert len(logs) == 200


def test_cache_ttl_expires(monkeypatch, tmp_path):
    from cache_manager import FileCache

    cache = FileCache(str(tmp_path / "cache"))
    try:
        cache.set("key", {"v": 1}, ttl=1)
        assert cache.get("key") == {"v": 1}
        time.sleep(1.1)
        assert cache.get("key") is None
    finally:
        cache.close()


def test_backup_excludes_secrets_and_logs(monkeypatch, tmp_path):
    import backup_manager as bm

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "classics.db").write_bytes(b"db")
    (data_dir / ".secret.key").write_bytes(b"secret")
    (data_dir / "app.log").write_text("log", encoding="utf-8")
    (data_dir / "classics.db-wal").write_bytes(b"wal")

    monkeypatch.setattr(bm, "app_path", lambda *parts: str(tmp_path.joinpath(*parts)))
    monkeypatch.setattr(bm, "normalize_path", lambda path: str(path))

    manager = bm.BackupManager(str(tmp_path / "backups"))
    archive_path = manager.create()
    assert archive_path and zipfile.is_zipfile(archive_path)

    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
    assert "data/classics.db" in names
    assert "data/.secret.key" not in names
    assert "data/app.log" not in names
    assert "data/classics.db-wal" not in names
    assert "manifest.json" in names


def test_backup_restore_roundtrip(monkeypatch, tmp_path):
    import backup_manager as bm

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "works.db").write_bytes(b"original")
    (data_dir / "notes.json").write_text('{"a": 1}', encoding="utf-8")

    monkeypatch.setattr(bm, "app_path", lambda *parts: str(tmp_path.joinpath(*parts)))
    monkeypatch.setattr(bm, "normalize_path", lambda path: str(path))

    manager = bm.BackupManager(str(tmp_path / "backups"))
    archive_path = manager.create()

    (data_dir / "notes.json").write_text('{"a": 2}', encoding="utf-8")
    ok, message = manager.restore(archive_path)
    assert ok, message
    assert (data_dir / "notes.json").read_text(encoding="utf-8") == '{"a": 1}'


def test_backup_names_are_unique(monkeypatch, tmp_path):
    import backup_manager as bm

    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "works.db").write_bytes(b"db")

    monkeypatch.setattr(bm, "app_path", lambda *parts: str(tmp_path.joinpath(*parts)))
    monkeypatch.setattr(bm, "normalize_path", lambda path: str(path))

    manager = bm.BackupManager(str(tmp_path / "backups"))
    first = manager.create()
    second = manager.create()
    assert first and second
    assert first != second, "同一秒内的两次备份不能互相覆盖"


def test_restore_ignores_wal_members(monkeypatch, tmp_path):
    import backup_manager as bm

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "works.db").write_bytes(b"db")

    monkeypatch.setattr(bm, "app_path", lambda *parts: str(tmp_path.joinpath(*parts)))
    monkeypatch.setattr(bm, "normalize_path", lambda path: str(path))

    manager = bm.BackupManager(str(tmp_path / "backups"))
    archive_path = manager.create()

    # 手工往 zip 里塞一个旧 WAL，恢复时必须跳过它
    import zipfile

    with zipfile.ZipFile(archive_path, "a") as archive:
        archive.writestr("data/works.db-wal", b"stale")

    ok, message = manager.restore(archive_path)
    assert ok, message
    assert not (data_dir / "works.db-wal").exists()


def test_lvshi_and_cipai_messages():
    from poetry_checker import check_lvshi, check_poem

    lines = [
        "国破山河在",
        "城春草木深",
        "感时花溅泪",
        "恨别鸟惊心",
        "烽火连三月",
        "家书抵万金",
        "白头搔更短",
        "浑欲不胜簪",
    ]
    assert check_lvshi(lines) != "需要四句"
    assert check_lvshi(lines[:4]) == "律诗需要八句"
    assert "暂不支持" in check_poem("如梦令", lines)


def test_count_search_and_pagination(tmp_path):
    from classics_database import ClassicsDatabase

    db = ClassicsDatabase(str(tmp_path / "search.db"))
    try:
        for index in range(7):
            db.insert({
                "id": f"t{index}",
                "title": f"明月{index}",
                "author": "李白",
                "dynasty": "唐",
                "category": "唐诗",
                "content": "床前明月光，疑是地上霜。",
            })
        db.insert({
            "id": "song1",
            "title": "水调歌头",
            "author": "苏轼",
            "dynasty": "宋",
            "category": "宋词",
            "content": "明月几时有，把酒问青天。",
        })
        assert db.count_search("明月") == 8
        assert db.count_search(category="唐诗") == 7
        assert db.count_search("明月", "宋词") == 1
        page = db.search("明月", limit=3, offset=0)
        assert len(page) == 3
    finally:
        db.close()


def test_migration_creates_version_and_backup(tmp_path):
    import sqlite3

    from classics_database import ClassicsDatabase

    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE classics (id TEXT PRIMARY KEY, title TEXT, author TEXT, dynasty TEXT, "
        "category TEXT, subcategory TEXT, content TEXT, translation TEXT, annotation TEXT, "
        "tags TEXT, char_count INTEGER, is_famous INTEGER, difficulty_level INTEGER)"
    )
    conn.execute(
        "INSERT INTO classics (id, title, content) VALUES ('old1', '旧数据', '床前明月光')"
    )
    conn.commit()
    conn.close()

    db = ClassicsDatabase(str(db_path))
    try:
        assert db.schema_version() == 1
        columns = {row[1] for row in db.conn.execute("PRAGMA table_info(classics)")}
        assert {"verified", "teaching_data", "created_at"} <= columns
        assert db.get_by_id("old1")["title"] == "旧数据"
    finally:
        db.close()
    backups = list(tmp_path.glob("old.db.pre_*"))
    assert backups, "迁移前应生成备份"


def test_data_root_override(monkeypatch, tmp_path):
    from utils import _resolve_data_root

    monkeypatch.setenv("XINYU_DATA_DIR", str(tmp_path / "custom"))
    assert _resolve_data_root() == str(tmp_path / "custom")


def test_api_guard_wraps_exceptions():
    from errors import api_guard

    @api_guard
    def broken():
        raise FileNotFoundError("missing")

    result = broken()
    assert result["__error__"]["code"] == "FILE_NOT_FOUND"
    assert result["__error__"]["message"]


def test_diagnostics_zip(monkeypatch, tmp_path):
    import zipfile

    import crash_reporter

    monkeypatch.setattr(crash_reporter, "app_path", lambda *parts: str(tmp_path.joinpath(*parts)))
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "app.log").write_text("hello", encoding="utf-8")
    path = crash_reporter.build_diagnostics()
    assert path and zipfile.is_zipfile(path)
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
    assert "system.txt" in names
    assert "settings.redacted.json" in names


@pytest.mark.parametrize(
    "text,expected",
    [
        ("9.1.0", (9, 1, 0)),
        ("v9.2", (9, 2)),
    ],
)
def test_version_tuple(text, expected):
    from version import version_tuple

    assert version_tuple(text) == expected
