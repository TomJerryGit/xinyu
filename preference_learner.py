# -*- coding: utf-8 -*-
"""
心语 V6.5 — 用户偏好学习器
记录用户的风格选择、主题偏好，辅助个性化推荐
"""
import os
from utils import safe_json_load, safe_json_save, ensure_dir

class PreferenceLearner:
    def __init__(self, path="data/preferences.json"):
        self.path = path
        self.data = self._load()

    def _load(self):
        """安全加载 JSON 数据"""
        return safe_json_load(self.path, {"styles": {}, "topics": [], "actions": {}})

    def _save(self):
        """安全保存 JSON 数据（自动创建目录）"""
        ensure_dir(os.path.dirname(self.path))
        safe_json_save(self.path, self.data)

    def record(self, genre, style, topic, action="generate"):
        """
        记录用户一次创作行为
        :param genre: 体裁
        :param style: 风格（字典或字符串）
        :param topic: 主题
        :param action: 动作类型（默认 generate）
        """
        # 提取风格标签（兼容字典或字符串）
        key = style.get("label", "默认") if isinstance(style, dict) else str(style)
        self.data["styles"][key] = self.data["styles"].get(key, 0) + 1
        # 记录主题（最多30个）
        if topic and topic not in self.data["topics"]:
            self.data["topics"].append(topic)
            if len(self.data["topics"]) > 30:
                self.data["topics"].pop(0)
        # 记录动作
        self.data["actions"][action] = self.data["actions"].get(action, 0) + 1
        self._save()

    def get_top_style(self):
        """返回最常使用的风格标签"""
        if not self.data["styles"]:
            return None
        return max(self.data["styles"], key=self.data["styles"].get)

    def get_recent_topics(self, n=5):
        """返回最近使用的主题列表（最多 n 个）"""
        return self.data["topics"][-n:]