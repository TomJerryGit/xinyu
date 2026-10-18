"""
心语 V6.5 — 创作画像生成
统计用户作品数据，生成专属创作报告
"""
from collections import Counter

class PoetProfiler:
    def __init__(self, database):
        self.db = database

    def generate(self):
        works = self.db.search()
        if not works:
            return None
        total = len(works)
        total_chars = sum(len(w[4]) for w in works)
        imagery = self._count_imagery(works)
        topics = Counter(w[3] for w in works if w[3]).most_common(10)
        return {
            "total_works": total,
            "total_chars": total_chars,
            "imagery_top": imagery[:20],
            "favorite_topics": topics,
            "avg_length": round(total_chars / total, 1) if total else 0
        }

    def _count_imagery(self, works):
        words = ["月","花","风","云","山","水","秋","春","夜","日","江","湖","梦","酒","剑","雪","雨","柳","松","竹"]
        cnt = Counter()
        for w in works:
            for word in words:
                cnt[word] += w[4].count(word)
        return cnt.most_common()