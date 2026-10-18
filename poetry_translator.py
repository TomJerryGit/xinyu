"""
心语 V6.5 — 诗词翻译引擎
"""
class PoetryTranslator:
    def __init__(self, engine):
        self.engine = engine

    def translate(self, poem, target="en"):
        if target == "en":
            prompt = f"请将以下中文诗词翻译成英文，保留意境，尽量押韵：\n{poem}"
        elif target == "ja":
            prompt = f"请将以下中文诗词翻译成日文，保留意境：\n{poem}"
        else:
            prompt = f"请将以下中文诗词翻译成{target}：\n{poem}"
        return self.engine.generate(prompt)