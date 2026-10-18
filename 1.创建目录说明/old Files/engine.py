"""
心语 V6.5 — 双引擎模块
在线：支持 DeepSeek / 通义千问 / 智谱AI / Moonshot / OpenAI
离线：llama.cpp GGUF 模型
"""
from abc import ABC, abstractmethod
import os


class BaseEngine(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str:
        pass


class CloudEngine(BaseEngine):
    PROVIDERS = {
        "deepseek": {
            "name": "DeepSeek",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "key_env": "DEEPSEEK_API_KEY",
        },
        "qwen": {
            "name": "通义千问",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "model": "qwen-plus",
            "key_env": "DASHSCOPE_API_KEY",
        },
        "zhipu": {
            "name": "智谱AI",
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "model": "glm-4-flash",
            "key_env": "ZHIPU_API_KEY",
        },
        "moonshot": {
            "name": "Moonshot",
            "base_url": "https://api.moonshot.cn/v1",
            "model": "moonshot-v1-8k",
            "key_env": "MOONSHOT_API_KEY",
        },
        "openai": {
            "name": "OpenAI",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-3.5-turbo",
            "key_env": "OPENAI_API_KEY",
        },
    }

    def __init__(self, provider="deepseek", api_key=None):
        from openai import OpenAI

        if provider not in self.PROVIDERS:
            raise ValueError(f"不支持的服务商: {provider}")

        cfg = self.PROVIDERS[provider]
        self.api_key = api_key or os.getenv(cfg["key_env"], "")

        if not self.api_key:
            print(f"⚠️ 未设置 {cfg['name']} API Key")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=cfg["base_url"]
        )
        self.model = cfg["model"]
        self.provider_name = cfg["name"]

    def generate(self, prompt: str) -> str:
        """生成文本，始终返回字符串"""
        if not self.api_key:
            return f"【错误】未设置 {self.provider_name} API Key"

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.9,
                max_tokens=512,
                stream=False,
            )
            return resp.choices[0].message.content
        except Exception as e:
            error_msg = str(e)
            if "api_key" in error_msg.lower() or "auth" in error_msg.lower():
                return f"【错误】API Key 无效"
            elif "connection" in error_msg.lower() or "timeout" in error_msg.lower():
                return "【错误】无法连接网络"
            elif "quota" in error_msg.lower() or "billing" in error_msg.lower():
                return "【错误】额度不足"
            else:
                return f"【生成错误】{error_msg}"


class LocalEngine(BaseEngine):
    def __init__(self, model_path="models/poem.gguf"):
        from llama_cpp import Llama
        self.model = Llama(model_path=model_path, n_ctx=512, verbose=False)

    def generate(self, prompt: str) -> str:
        output = self.model(prompt, max_tokens=256, stop=["用户："])
        return output["choices"][0]["text"]