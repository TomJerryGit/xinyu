"""
心语 V6.5 — 歌词韵脚与结构检测
"""
from pypinyin import pinyin, Style
from collections import defaultdict

def get_rhyme_groups(lines):
    rhyme_map = defaultdict(list)
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        last_char = line.strip()[-1]
        if '\u4e00' <= last_char <= '\u9fff':
            final = pinyin(last_char, style=Style.FINALS)[0][0]
            rhyme_map[final].append(i)
    return None, rhyme_map

def check_structure(text):
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    if len(paragraphs) < 2:
        return []
    issues = []
    if len(paragraphs[0].split('\n')) != len(paragraphs[1].split('\n')):
        issues.append("主歌段落行数不一致")
    if len(paragraphs) >= 4:
        if len(paragraphs[2].split('\n')) != len(paragraphs[3].split('\n')):
            issues.append("副歌段落行数不一致")
    return issues