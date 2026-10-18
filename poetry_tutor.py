"""
心语 V6.5 — AI 诗词导师
回答用户关于诗词知识的提问
"""
class PoetryTutor:
    def __init__(self, engine):
        self.engine = engine

    def ask(self, question):
        prompt = f"你是诗词老师，请用通俗语言回答学生问题。\n问题：{question}\n要求：准确，举例，200字以内。"
        return self.engine.generate(prompt)