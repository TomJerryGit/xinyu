# -*- coding: utf-8 -*-
"""
心语 V6.5 — 多语言管理器
支持从 locales 目录加载 JSON 语言文件，提供 t() 翻译方法
"""
import json
import os

from utils import resource_path

class I18nManager:
    def __init__(self, locale_dir=None, default_lang="zh-CN"):
        """
        初始化多语言管理器
        :param locale_dir: 语言文件目录（默认资源目录下的 locales）
        :param default_lang: 默认语言代码（如 zh-CN, en-US）
        """
        self.locale_dir = locale_dir or resource_path("locales")
        self.default_lang = default_lang
        self.current_lang = default_lang
        self.strings = {}
        self.load(default_lang)

    def load(self, lang):
        """
        加载指定语言文件
        :param lang: 语言代码
        :return: bool 是否加载成功
        """
        path = os.path.join(self.locale_dir, f"{lang}.json")
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                self.strings = data
                self.current_lang = lang
                return True
            else:
                print(f"语言文件格式错误: {path}")
                return False
        except FileNotFoundError:
            # 回退到默认语言
            if lang != self.default_lang:
                print(f"语言文件缺失: {path}，回退到 {self.default_lang}")
                return self.load(self.default_lang)
            else:
                print(f"默认语言文件也缺失: {path}")
                self.strings = {}
                return False
        except Exception as e:
            print(f"加载语言文件失败: {e}")
            return False

    def t(self, key, **kwargs):
        """
        翻译字符串，支持占位符替换（如 {name}）
        :param key: 翻译键
        :param kwargs: 占位符变量
        :return: 翻译后的字符串
        """
        # 优先从当前语言获取，若无则回退到默认语言，再回退到 key 本身
        text = self.strings.get(key)
        if text is None:
            # 尝试从默认语言文件获取
            if self.current_lang != self.default_lang:
                default_path = os.path.join(self.locale_dir, f"{self.default_lang}.json")
                try:
                    with open(default_path, 'r', encoding='utf-8') as f:
                        default_data = json.load(f)
                    text = default_data.get(key, key)
                except Exception:
                    text = key
            else:
                text = key

        # 处理占位符
        if text and kwargs:
            try:
                text = text.format(**kwargs)
            except KeyError:
                pass  # 若缺少占位符，保持原文
        return text

    def get_supported_languages(self):
        """返回可用的语言列表"""
        if not os.path.exists(self.locale_dir):
            return []
        files = [f for f in os.listdir(self.locale_dir) if f.endswith('.json')]
        return [os.path.splitext(f)[0] for f in files]

    def set_language(self, lang):
        """切换语言"""
        return self.load(lang)

    def get_current_language(self):
        return self.current_lang