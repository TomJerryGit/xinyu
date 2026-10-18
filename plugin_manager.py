# -*- coding: utf-8 -*-
"""
心语 V6.5 — 插件管理器
自动扫描 plugins/ 目录，加载符合规范的 Python 插件

插件协议：
    每个插件文件必须实现 `get_plugin_info()` 函数，返回字典：
    {
        "name": 插件名称,
        "genre_name": 提供的新体裁名称,
        "generate": 生成函数（接收 engine, topic, style_info 参数，返回作品文本）
    }
"""
import os
import importlib.util
import logging

logger = logging.getLogger("xinyu")


class PluginManager:
    def __init__(self, plugin_dir="plugins"):
        """
        初始化插件管理器
        :param plugin_dir: 插件目录
        """
        self.plugin_dir = plugin_dir
        self.plugins = []
        self.load()

    def load(self):
        """扫描插件目录，加载所有符合规范的插件"""
        self.plugins = []
        if not os.path.exists(self.plugin_dir):
            logger.info(f"插件目录 {self.plugin_dir} 不存在")
            return

        # 遍历目录（仅直接子目录下的 .py 文件，支持嵌套目录）
        for root, _, files in os.walk(self.plugin_dir):
            for filename in files:
                if filename.endswith(".py") and not filename.startswith("_"):
                    filepath = os.path.join(root, filename)
                    self._load_plugin(filepath)

        logger.info(f"已加载 {len(self.plugins)} 个插件")

    def _load_plugin(self, filepath):
        """加载单个插件文件"""
        try:
            # 动态加载模块
            spec = importlib.util.spec_from_file_location(
                f"xinyu_plugin_{os.path.basename(filepath)[:-3]}", filepath
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            if hasattr(module, 'get_plugin_info'):
                info = module.get_plugin_info()
                if isinstance(info, dict) and info.get("genre_name") and info.get("generate"):
                    # 确保 generate 是可调用对象
                    if callable(info["generate"]):
                        self.plugins.append(info)
                        logger.info(f"插件加载成功: {info.get('name', info['genre_name'])}")
                    else:
                        logger.warning(f"插件 {filepath} 的 generate 不是可调用对象")
                else:
                    logger.warning(f"插件 {filepath} 缺少 genre_name 或 generate")
            else:
                logger.warning(f"插件 {filepath} 缺少 get_plugin_info 函数")
        except Exception as e:
            logger.error(f"加载插件失败 {filepath}: {e}")

    def get_genres(self):
        """返回所有插件提供的体裁名称列表"""
        return [p["genre_name"] for p in self.plugins]

    def generate(self, genre_name, engine, topic, style_info):
        """
        调用指定体裁的插件生成函数
        :param genre_name: 插件体裁名称
        :param engine: 引擎对象（用于调用其他 API）
        :param topic: 主题
        :param style_info: 风格信息
        :return: 生成的作品文本或 None
        """
        for p in self.plugins:
            if p["genre_name"] == genre_name:
                try:
                    return p["generate"](engine, topic, style_info)
                except Exception as e:
                    logger.error(f"插件生成失败 {p.get('name')}: {e}")
                    return None
        return None

    def is_installed(self, name):
        """检查指定名称的插件是否已安装"""
        return any(p.get("name") == name for p in self.plugins)

    def get_plugin_list(self):
        """返回插件信息列表（用于前端展示）"""
        return [
            {
                "name": p.get("name", p["genre_name"]),
                "genre_name": p["genre_name"],
                "description": p.get("description", ""),
            }
            for p in self.plugins
        ]