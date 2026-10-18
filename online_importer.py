# -*- coding: utf-8 -*-
"""多源诗词数据下载与导入。

数据源为 chinese-poetry 仓库的原始 JSON；下载结果写入
``data/poetry_cache``，导入时复用外部数据库连接。
"""
import json
import os

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

from classics_database import ClassicsDatabase
from utils import app_path, atomic_write_text

SOURCES = {
    "唐诗": [
        "https://raw.githubusercontent.com/chinese-poetry/chinese-poetry/master/%E5%85%A8%E5%94%90%E8%AF%97/poet.tang.0.json",
        "https://raw.githubusercontent.com/chinese-poetry/chinese-poetry/master/%E5%85%A8%E5%94%90%E8%AF%97/poet.tang.1000.json",
    ],
    "宋词": [
        "https://raw.githubusercontent.com/chinese-poetry/chinese-poetry/master/%E5%AE%8B%E8%AF%8D/ci.song.0.json",
        "https://raw.githubusercontent.com/chinese-poetry/chinese-poetry/master/%E5%AE%8B%E8%AF%8D/ci.song.1000.json",
    ],
    "论语": [
        "https://raw.githubusercontent.com/chinese-poetry/chinese-poetry/master/%E8%AE%BA%E8%AF%AD/lunyu.json",
    ],
    "诗经": [
        "https://raw.githubusercontent.com/chinese-poetry/chinese-poetry/master/%E8%AF%97%E7%BB%8F/shijing.json",
    ],
    "楚辞": [
        "https://raw.githubusercontent.com/chinese-poetry/chinese-poetry/master/%E6%A5%9A%E8%BE%9E/chuci.json",
    ],
    "蒙学": [
        "https://raw.githubusercontent.com/chinese-poetry/chinese-poetry/master/%E8%92%99%E5%AD%A6/sanziJing.json",
        "https://raw.githubusercontent.com/chinese-poetry/chinese-poetry/master/%E8%92%99%E5%AD%A6/baiJiaXing.json",
        "https://raw.githubusercontent.com/chinese-poetry/chinese-poetry/master/%E8%92%99%E5%AD%A6/qianZiWen.json",
    ],
    "宋诗": [
        "https://raw.githubusercontent.com/chinese-poetry/chinese-poetry/master/%E5%AE%8B%E8%AF%97/poet.song.0.json",
    ],
    "元曲": [
        "https://raw.githubusercontent.com/chinese-poetry/chinese-poetry/master/%E5%85%83%E6%9B%B2/yuanqu.json",
    ],
}


class OnlineImporter:
    def __init__(self, db_path="data/classics.db", db=None, timeout=20):
        self.db = db or ClassicsDatabase(db_path)
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "XinYu/9.1"})
        self.sources = SOURCES

    def _try_fetch(self, urls):
        for url in urls:
            try:
                resp = self.session.get(url, timeout=self.timeout)
                if resp.status_code == 200:
                    return resp
                print(f"  源不可用({resp.status_code}): {url[:80]}...")
            except Exception as exc:  # noqa: BLE001 - 单个源失败继续尝试下一个
                print(f"  源超时或错误: {url[:80]}... {str(exc)[:50]}")
        return None

    @staticmethod
    def _parse(resp):
        if resp is None:
            return []
        text = resp.text
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
        except Exception:
            pass
        rows = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
        return rows

    @staticmethod
    def _make(cat, item):
        title = item.get("title") or item.get("chapter") or item.get("name") or ""
        poet = item.get("poet")
        author = item.get("author") or (poet.get("name") if isinstance(poet, dict) else "") or ""
        paragraphs = item.get("paragraphs", item.get("content", []))
        if isinstance(paragraphs, list):
            content = "\n".join(str(part) for part in paragraphs)
        else:
            content = str(paragraphs)
        tags = item.get("tags", [])
        if isinstance(tags, list):
            tags = ",".join(str(tag) for tag in tags)
        return {
            "title": title or "无题",
            "author": author or "佚名",
            "dynasty": item.get("dynasty", "") or "",
            "category": cat,
            "subcategory": "",
            "content": content,
            "tags": tags,
            "annotation": "",
            "is_famous": 0,
            "difficulty_level": 2,
        }

    def search_online(self, keyword="", category="", limit=30):
        """在线搜索（不写库）；网络失败时返回空列表。"""
        categories = [category] if category in self.sources else list(self.sources.keys())
        results = []
        for cat in categories:
            resp = self._try_fetch(self.sources.get(cat, []))
            if resp is None:
                continue
            for item in self._parse(resp):
                if not isinstance(item, dict):
                    continue
                record = self._make(cat, item)
                haystack = record["title"] + record["author"] + record["content"]
                if keyword and keyword not in haystack:
                    continue
                results.append(record)
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break

        seen = set()
        unique = []
        for record in results:
            key = (record["title"], record["author"])
            if key in seen:
                continue
            seen.add(key)
            unique.append(record)
        return unique[:limit]

    def download_and_import(self, items):
        if isinstance(items, dict):
            items = [items]
        count = 0
        for item in items:
            if isinstance(item, dict) and self.db.insert(item):
                count += 1
        return count

    def download_dataset(self, name):
        """并发下载指定分类的完整数据集到缓存文件。"""
        if name not in self.sources:
            return {"error": f"不支持: {name}"}

        cache_dir = app_path("data", "poetry_cache")
        os.makedirs(cache_dir, exist_ok=True)
        path = os.path.join(cache_dir, f"{name}.json")

        all_data = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(self._try_fetch, [url]): url for url in self.sources[name]}
            for future in as_completed(futures):
                resp = future.result()
                if not resp:
                    continue
                data = self._parse(resp)
                if data:
                    all_data.extend(data)

        if not all_data:
            return {"error": "所有源不可用或数据为空"}

        if not atomic_write_text(path, json.dumps(all_data, ensure_ascii=False)):
            return {"error": "缓存写入失败"}

        size_mb = os.path.getsize(path) / (1024 * 1024)
        return {
            "success": True,
            "dataset": name,
            "count": len(all_data),
            "file_size": f"{size_mb:.1f}MB",
            "cache_path": path,
        }

    def import_cache(self, name="", limit=None):
        cache_dir = app_path("data", "poetry_cache")
        if not os.path.exists(cache_dir):
            return {"error": "no cache"}
        files = [f"{name}.json"] if name else [f for f in os.listdir(cache_dir) if f.endswith(".json")]
        total = 0
        for filename in files:
            path = os.path.join(cache_dir, filename)
            if not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    items = json.load(handle)
                if limit:
                    items = items[: int(limit)]
                category = filename[:-5]
                for item in items:
                    if isinstance(item, dict) and self.db.insert(self._make(category, item)):
                        total += 1
            except Exception as exc:  # noqa: BLE001
                print(f"导入 {filename} 出错: {exc}")
        return {"success": True, "imported": total}

    def close(self):
        self.session.close()
