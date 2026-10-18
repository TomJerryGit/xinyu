"""
心语 V6.5 — YAML 提示词模板引擎
支持条件判断和变量替换
"""
import yaml, random, re
from pathlib import Path

class PromptForge:
    def __init__(self, template_dir="prompts"):
        self.templates = {}
        self._load(Path(template_dir))

    def _load(self, dir_path):
        if not dir_path.exists():
            return
        for f in dir_path.glob("*.yaml"):
            with open(f, 'r', encoding='utf-8') as fp:
                t = yaml.safe_load(fp)
                self.templates[t['name']] = t

    def render(self, name, variables):
        t = self.templates.get(name)
        if not t:
            return None
        system = self._process_conditionals(t.get('system', ''), variables)
        examples = ""
        if 'few_shots' in t:
            shots = random.sample(t['few_shots'], min(2, len(t['few_shots'])))
            examples = "\n".join([f"用户：{s['input']}\n助手：{s['output']}" for s in shots])
        constraints = "\n".join([f"- {c}" for c in t.get('constraints', [])])
        return {
            "system": system,
            "examples": examples,
            "constraints": constraints,
            "full": f"{system}\n{examples}\n\n规则：\n{constraints}\n\n用户：{variables.get('topic','')}"
        }

    def _process_conditionals(self, text, variables):
        def replace(match):
            cond = match.group(1).strip()
            content = match.group(2)
            for k, v in variables.items():
                if f"{k} ==" in cond:
                    expected = cond.split('==')[1].strip().strip('"').strip("'")
                    if str(v) == expected:
                        return content.split('{% elif ')[0].split('%}')[1]
            return content.split('{% elif ')[-1].split('%}')[1] if '{% elif' in content else content
        return re.sub(r'{%\s*if\s+(.*?)\s*%}(.*?){%\s*endif\s*%}', replace, text, flags=re.DOTALL)