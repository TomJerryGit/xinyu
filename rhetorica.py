"""
心语 V6.5 — 修辞分析器
检测对仗、典故、叠字
"""
import json, os, re

class Rhetorica:
    def __init__(self, allusion_db="resources/allusion_db.json"):
        self.allusions = []
        if os.path.exists(allusion_db):
            with open(allusion_db, 'r', encoding='utf-8') as f:
                self.allusions = json.load(f)

    def analyze(self, poem):
        lines = poem.strip().split('\n')
        return {
            "antithesis": self._check_antithesis(lines),
            "allusions": self._detect_allusions(poem),
            "reduplication": self._detect_reduplication(poem)
        }

    def _check_antithesis(self, lines):
        pairs = []
        for i in range(len(lines) - 1):
            if len(lines[i]) == len(lines[i+1]) and len(lines[i]) >= 10:
                pairs.append(f"第{i+1}句与第{i+2}句可能对仗")
        return pairs

    def _detect_allusions(self, text):
        found = []
        for al in self.allusions:
            for kw in al.get("keywords", []):
                if kw in text:
                    found.append(f"{al['name']}（{al.get('source','')}）")
                    break
        return found[:10]

    def _detect_reduplication(self, text):
        patterns = [r'(.)\1', r'(..)\1', r'(.)\1(.)\2']
        results = []
        for p in patterns:
            for m in re.findall(p, text):
                results.append(''.join(m) if isinstance(m, tuple) else m)
        return list(set(results))