"""
心语 V6.6 — 经典文库管理（JSON 文件版）
用于读取 resources/classics.json 中的经典数据
"""
import json
import os
import random


class ClassicLibrary:
    def __init__(self, data_path="resources/classics.json"):
        self.data = {}
        self.flat = []
        if os.path.exists(data_path):
            with open(data_path, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
            for cat, items in self.data.items():
                for item in items:
                    item["category"] = cat
                    self.flat.append(item)

    def search(self, keyword="", category="", dynasty=""):
        results = self.flat
        if category and category != "全部":
            results = [r for r in results if r.get("category") == category]
        if dynasty:
            results = [r for r in results if r.get("dynasty") == dynasty]
        if keyword:
            kw = keyword.lower()
            results = [r for r in results if kw in r.get("title","").lower() 
                       or kw in r.get("author","").lower() 
                       or kw in r.get("content","").lower()
                       or kw in " ".join(r.get("tags",[])).lower()]
        return results[:30]

    def get_random(self):
        return random.choice(self.flat) if self.flat else None

    def get_categories(self):
        return list(self.data.keys())

    def get_by_id(self, item_id):
        for item in self.flat:
            if item.get("id") == item_id:
                return item
        return None