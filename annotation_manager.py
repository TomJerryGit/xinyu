# -*- coding: utf-8 -*-
"""
心语 V6.5 — 经典笔记批注管理
"""
import json, os
from datetime import datetime
from utils import safe_json_load, safe_json_save, ensure_dir

class AnnotationManager:
    def __init__(self, path="data/annotations.json"):
        self.path = path
        self.data = self._load()

    def _load(self):
        """安全加载 JSON 数据"""
        return safe_json_load(self.path, {})

    def _save(self):
        """安全保存 JSON 数据（自动创建目录）"""
        ensure_dir(os.path.dirname(self.path))
        safe_json_save(self.path, self.data)

    def add(self, classic_id, text, position=None):
        """添加一条批注"""
        if classic_id not in self.data:
            self.data[classic_id] = []
        self.data[classic_id].append({
            "text": text,
            "position": position,
            "time": datetime.now().isoformat()
        })
        self._save()

    def get(self, classic_id):
        """获取某篇经典的全部批注"""
        return self.data.get(classic_id, [])

    def remove(self, classic_id, index):
        """删除指定索引的批注"""
        if classic_id in self.data and 0 <= index < len(self.data[classic_id]):
            self.data[classic_id].pop(index)
            self._save()
            return True
        return False