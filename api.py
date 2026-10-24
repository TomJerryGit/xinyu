# -*- coding: utf-8 -*-
import os, warnings, json, random, time, threading, hashlib, re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import wraps
from typing import List, Dict, Optional

os.environ["MMKV_LOG_LEVEL"] = "off"
warnings.filterwarnings("ignore")

from engine import CloudEngine, LazyEngine, LocalEngine, encrypt, decrypt
from errors import install_api_guards
from ai_gateway import AIGateway
from jobs import JobManager
from perf import mark as perf_mark
from style_manager import StyleManager
from database import Database
from classics_database import ClassicsDatabase
from classics_importer import ClassicsImporter
from preference_learner import PreferenceLearner
from plugin_manager import PluginManager
from backup_manager import BackupManager
from cache_manager import CacheManager
from tts_manager import TTSManager
from updater import Updater, VersionManager
from logger import log
from version import VERSION
from utils import safe_json_load, safe_json_save, ensure_dir, normalize_path, get_timestamp_str, secure_file_permissions, app_path, atomic_write_text, resource_path

_UI_STATE_LOCK = threading.Lock()

def safe_api(func):
    """保留装饰器以兼容旧代码；异常交给全局 api_guard 统一处理。"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper


# 质量评分权重（满分 100）：只衡量"信息是否完整"，不代表内容准确
_SCORE_WEIGHTS = {
    "title": 5,
    "author": 8,
    "dynasty": 5,
    "content": 7,
    "verified": 15,
    "no_error": 10,
    "annotation": 8,
    "tags": 6,
    "emotion": 6,
    "translation": 8,
    "audio": 7,
    "related": 8,
    "allusions": 7,
}


def score_item(item: Dict) -> Dict:
    """对任意条目字典评分（不查数据库），供导入前质量闸门使用。"""
    item = item or {}
    score = 0
    detail = {}
    if item.get("title"):
        score += _SCORE_WEIGHTS["title"]
        detail["title"] = _SCORE_WEIGHTS["title"]
    if item.get("author"):
        score += _SCORE_WEIGHTS["author"]
        detail["author"] = _SCORE_WEIGHTS["author"]
    if item.get("dynasty"):
        score += _SCORE_WEIGHTS["dynasty"]
        detail["dynasty"] = _SCORE_WEIGHTS["dynasty"]
    if len(str(item.get("content", ""))) > 10:
        score += _SCORE_WEIGHTS["content"]
        detail["content"] = _SCORE_WEIGHTS["content"]
    if item.get("verified"):
        score += _SCORE_WEIGHTS["verified"]
        detail["verified"] = _SCORE_WEIGHTS["verified"]
    if item.get("title") and not item.get("has_error"):
        score += _SCORE_WEIGHTS["no_error"]
        detail["no_error"] = _SCORE_WEIGHTS["no_error"]
    for field in ("annotation", "tags", "emotion", "translation", "audio", "related_works", "allusions"):
        key = "related" if field == "related_works" else field
        if item.get(field):
            score += _SCORE_WEIGHTS[key]
            detail[key] = _SCORE_WEIGHTS[key]
    if score >= 95:
        grade = "S"
    elif score >= 85:
        grade = "A"
    elif score >= 70:
        grade = "B"
    elif score >= 50:
        grade = "C"
    else:
        grade = "D"
    stars = "⭐" * {"S": 5, "A": 4, "B": 3, "C": 2, "D": 1}[grade]
    return {"score": score, "grade": grade, "details": detail, "stars": stars}


def content_fingerprint(title: str, author: str, content: str) -> str:
    """用于去重的内容指纹：标题 + 作者 + 去掉空白标点的正文。"""
    normalized = re.sub(r"[\s\W_]+", "", str(content or ""))
    seed = f"{title or ''}|{author or ''}|{normalized}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()


def _export_path(filename: str) -> str:
    """把导出文件统一放到 ``exports/``，避免污染程序根目录。"""
    directory = app_path("exports")
    os.makedirs(directory, exist_ok=True)
    return os.path.join(directory, filename)


# ---------------------- 经典库操作 Mixin ----------------------
class ClassicsMixin:
    def search_classics_v2(self, kw: str = "", cat: str = "", dyn: str = "", au: str = "", limit: int = 500, offset: int = 0) -> List[Dict]:
        limit = min(2000, max(1, int(limit or 500)))
        offset = max(0, int(offset or 0))
        k = f"search:{kw}:{cat}:{dyn}:{au}:{limit}:{offset}"
        cached = self.cache_mgr.get(k)
        if cached:
            return cached
        r = self.classics_db.search(kw, cat, dyn, au, None, limit, offset)
        self.cache_mgr.set(k, r, ttl=600)
        return r

    def search_classics_page(self, kw: str = "", cat: str = "", dyn: str = "", au: str = "", page: int = 1, page_size: int = 20, verified_only: bool = False) -> Dict:
        """服务端分页检索，避免一次把整库数据传到前端。"""
        page = max(1, int(page or 1))
        page_size = min(100, max(5, int(page_size or 20)))
        verified_only = bool(verified_only)
        key = f"page:{kw}:{cat}:{dyn}:{au}:{page}:{page_size}:{int(verified_only)}"
        cached = self.cache_mgr.get(key)
        if cached:
            return cached
        total = self.classics_db.count_search(kw, cat, dyn, au, None, verified_only)
        items = self.classics_db.search(kw, cat, dyn, au, None, page_size, (page - 1) * page_size, verified_only)
        result = {
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, (total + page_size - 1) // page_size),
            "items": items,
            "verified_only": verified_only,
        }
        self.cache_mgr.set(key, result, ttl=300)
        return result

    def get_dashboard(self) -> Dict:
        """首页概览：一次请求返回统计、每日一诗、最近阅读与运行状态。"""
        cached = self.cache_mgr.get("dashboard:v92")
        if cached:
            return cached
        stats = self.classics_db.get_stats()
        quality_avg = 0
        cached_stats = self.cache_mgr.get("stats:classics")
        if isinstance(cached_stats, dict):
            quality_avg = cached_stats.get("quality_avg", 0)
        result = {
            "classics_total": stats["total"],
            "total_chars": stats["total_chars"],
            "category_count": len(stats["categories"]),
            "categories": stats["categories"][:8],
            "dynasties": stats["dynasties"][:8],
            "favorites": self.classics_db.get_favorites_count(),
            "notes": self.classics_db.get_notes_count(),
            "works": self.db.count(),
            "streak": self.classics_db.get_reading_streak(),
            "quality_avg": quality_avg,
            "daily": self.get_daily_task(),
            "recent_reads": self.classics_db.get_reading_history(6),
            "version": VERSION,
            "has_key": self.engine.is_configured(),
            "provider": self.engine.provider_name,
            "model": self.engine.model,
        }
        self.cache_mgr.set("dashboard:v92", result, ttl=60)
        return result

    def get_classic_stats(self) -> Dict:
        cached = self.cache_mgr.get("stats:classics")
        if cached:
            return cached
        base = self.classics_db.get_stats()
        quality = self.batch_quality_check(limit=200)
        logs = self.get_expand_log()
        result = {
            "total": base["total"],
            "total_chars": base["total_chars"],
            "categories": base["categories"],
            "dynasties": base["dynasties"],
            "quality_avg": quality["avg_score"],
            "quality_dist": quality["grades"],
            "recent_expand": len(logs) if logs else 0
        }
        self.cache_mgr.set("stats:classics", result, ttl=120)
        return result

    def get_classic_categories_v2(self) -> List[Dict]:
        cached = self.cache_mgr.get("categories:classics")
        if cached:
            return cached
        result = self.classics_db.get_categories()
        self.cache_mgr.set("categories:classics", result, ttl=300)
        return result

    def get_classic_dynasties_v2(self) -> List[Dict]:
        cached = self.cache_mgr.get("dynasties:classics")
        if cached:
            return cached
        result = self.classics_db.get_dynasties()
        self.cache_mgr.set("dynasties:classics", result, ttl=300)
        return result

    def get_classic_by_id_v2(self, cid: str) -> Optional[Dict]:
        return self.classics_db.get_by_id(cid)

    def get_reading_history(self, limit: int = 20) -> List[Dict]:
        return self.classics_db.get_reading_history(min(200, max(1, int(limit or 20))))

    def get_works(self, keyword: str = "", limit: int = 50) -> List[Dict]:
        return self.db.search_dicts(keyword, min(500, max(1, int(limit or 50))))

    def compare_classics(self, id1: str, id2: str) -> str:
        return self.compare_analysis(id1, id2)

    def record_classic_read(self, cid: str) -> None:
        self.classics_db.record_read(cid)

    def add_favorite(self, cid: str) -> None:
        self.classics_db.add_favorite(cid)
        self.cache_mgr.clear()

    def get_favorites(self) -> List[Dict]:
        return self.classics_db.get_favorites()

    def get_random_classic(self, category: str = "") -> Optional[Dict]:
        return self.classics_db.get_random(category)


    def search_online_classics(self, kw: str = "", cat: str = "", limit: int = 30) -> List[Dict]:
        return self.online_importer.search_online(kw, cat, limit)

    def download_and_import_items(self, ij: str) -> str:
        try:
            items = json.loads(ij) if isinstance(ij, str) else ij
        except (TypeError, ValueError):
            return "导入失败：数据格式错误"
        count = self.online_importer.download_and_import(items)
        self.cache_mgr.clear()
        return f"导入 {count} 篇"

    def download_dataset(self, name: str) -> Dict:
        return self.online_importer.download_dataset(name)

    def import_cache(self, name: str = "", limit: Optional[int] = None) -> Dict:
        safe_name = os.path.basename(normalize_path(name)) if name else ""
        result = self.online_importer.import_cache(safe_name, limit)
        self.cache_mgr.clear()
        return result

    def browse_by_filters(self, era: str = "", genre: str = "", school: str = "", category: str = "", limit: int = 200) -> List[Dict]:
        results = self.classics_db.search("", "", "", "", limit=limit)
        filtered = []
        for r in results:
            dynasty, cat, tags, sub = r.get("dynasty", ""), r.get("category", ""), r.get("tags", ""), r.get("subcategory", "")
            if era:
                era_map = {"先秦": ["先秦"], "两汉": ["西汉", "东汉", "汉"], "魏晋": ["魏", "晋", "东晋", "南北朝"], "唐": ["唐"], "宋": ["宋", "北宋", "南宋"], "元": ["元"], "明": ["明"], "清": ["清"], "民国": ["民国"]}
                if not any(e in dynasty for e in era_map.get(era, [era])):
                    continue
            if genre:
                genre_map = {"诗": ["诗", "唐诗", "宋诗", "绝句", "律诗"], "词": ["词", "宋词"], "曲": ["曲", "元曲"], "赋": ["赋", "辞赋"], "散文": ["散文", "经典散文"], "蒙学": ["蒙学"], "经部": ["经部"]}
                if not any(g in cat or g in sub or g in tags for g in genre_map.get(genre, [genre])):
                    continue
            if school:
                school_map = {"儒家": ["儒家"], "道家": ["道家"], "法家": ["法家"], "婉约": ["婉约"], "豪放": ["豪放"], "山水": ["山水"], "边塞": ["边塞"]}
                if not any(s in cat or s in sub or s in tags for s in school_map.get(school, [school])):
                    continue
            if category and cat != category:
                continue
            filtered.append(r)
        return filtered[:limit]

    def deep_analysis(self, classic_id: str) -> Dict:
        self.engine.current_task = "analysis"
        item = self.classics_db.get_by_id(classic_id)
        if not item:
            return {"error": "未找到该作品"}
        prompt = f"""请对《{item['title']}》{item['author']}进行六维深度赏析，以JSON格式返回：
{{"background":"创作背景（50字）","text_analysis":"文本解读（100字）","artistic":"意境分析（50字）","rhythm":"格律分析（50字）","culture":"文化拓展（50字）","teaching":"教学建议（50字）"}}
原文：{item['content']}"""
        try:
            result = self.ai.generate(self.engine.current_task or "generate", prompt)
            if result and ("错误" in result or "失败" in result or "网络" in result or "超时" in result):
                raise Exception("AI调用异常")
            try:
                data = json.loads(result)
                if not all(k in data for k in ["background","text_analysis","artistic","rhythm","culture","teaching"]):
                    raise ValueError("缺少字段")
                return data
            except Exception:
                retry_prompt = f"请只输出JSON，不要包含任何其他文字。格式：{{\"background\":\"...\",\"text_analysis\":\"...\",\"artistic\":\"...\",\"rhythm\":\"...\",\"culture\":\"...\",\"teaching\":\"...\"}}。作品：《{item['title']}》作者：{item['author']}，原文：{item['content'][:100]}"
                result = self.ai.generate(self.engine.current_task or "generate", retry_prompt)
                data = json.loads(result)
                if not all(k in data for k in ["background","text_analysis","artistic","rhythm","culture","teaching"]):
                    raise ValueError("仍缺少字段")
                return data
        except Exception:
            return {
                "background": item.get("annotation") or f"{item.get('dynasty','')} {item.get('author','佚名')}的作品，具有独特的艺术价值。",
                "text_analysis": item.get("translation") or f"本诗（文）以「{item.get('title','')}」为题，内容为：{item.get('content','')[:100]}...",
                "artistic": "（离线模式）结合原文意象，可体会其艺术风格，建议联网获取深度AI赏析。",
                "rhythm": "（离线模式）本文格律特征待补充，可联网获取专业分析。",
                "culture": "（离线模式）可结合历史背景进行延伸阅读，联网可获得更多文化拓展。",
                "teaching": "（离线模式）建议课堂中结合课文注释进行讲解，或联网获取AI教学建议。"
            }

    def in_depth_explanation(self, text: str) -> Dict:
        self.engine.current_task = "explain"
        prompt = f"""请对以下文本进行深入讲解，返回JSON：
{{"background":"创作背景推测","theme":"主题思想","imagery":"意象分析","rhetoric":"修辞手法","structure":"结构分析","language":"语言特色"}}
文本：{text}"""
        try:
            result = self.ai.generate(self.engine.current_task or "generate", prompt)
            if result and ("错误" in result or "失败" in result or "网络" in result or "超时" in result):
                raise Exception("AI调用异常")
            return json.loads(result)
        except Exception:
            return {"error": "讲解失败"}

    def simple_analysis(self, classic_id: str, level: str = "L2") -> str:
        self.engine.current_task = "analysis"
        item = self.classics_db.get_by_id(classic_id)
        if not item:
            return "未找到该作品"
        prompts = {"L1": f"用5岁儿童能听懂的语言解读《{item['title']}》。原文：{item['content']}",
                   "L2": f"为中学生解读《{item['title']}》。原文：{item['content']}",
                   "L3": f"从学术角度分析《{item['title']}》。原文：{item['content']}"}
        return self.ai.generate(self.engine.current_task or "generate", prompts.get(level, prompts["L2"]))

    def compare_analysis(self, id1: str, id2: str) -> str:
        self.engine.current_task = "analysis"
        item1, item2 = self.classics_db.get_by_id(id1), self.classics_db.get_by_id(id2)
        if not item1 or not item2:
            return "未找到作品"
        return self.ai.generate(self.engine.current_task or "generate", f"对比分析：\nA：《{item1['title']}》{item1['author']}\n{item1['content']}\nB：《{item2['title']}》{item2['author']}\n{item2['content']}")

    def mengxue_analysis(self, classic_id: str) -> Dict:
        self.engine.current_task = "analysis"
        item = self.classics_db.get_by_id(classic_id)
        if not item:
            return "未找到该作品"
        prompt = f"""对蒙学经典《{item['title']}》进行儿童友好型赏析，返回JSON：
{{"word_explain":"字词解释","rhythm_tip":"韵律特点","story_version":"故事化解读","moral":"道理","activity":"小活动建议"}}
原文：{item['content']}"""
        try:
            result = self.ai.generate(self.engine.current_task or "generate", prompt)
            if result and ("错误" in result or "失败" in result or "网络" in result or "超时" in result):
                raise Exception("AI调用异常")
            return json.loads(result)
        except Exception:
            return {"error": "赏析失败"}

    def quality_score(self, classic_id: str) -> Dict:
        item = self.classics_db.get_by_id(classic_id)
        if not item:
            return {"error": "未找到"}
        return score_item(item)

    def batch_quality_check(self, category: str = "", limit: int = 50) -> Dict:
        items = self.classics_db.search(category=category, limit=limit) if category else self.classics_db.search(limit=limit)
        results = []
        for item in items:
            r = score_item(item)
            results.append({"id": item["id"], "title": item["title"], "author": item["author"], "score": r["score"], "grade": r["grade"]})
        grades = {"S": 0, "A": 0, "B": 0, "C": 0, "D": 0}
        for r in results:
            grades[r["grade"]] += 1
        return {"total": len(results), "grades": grades, "items": results[:20], "avg_score": sum(r["score"] for r in results) // max(len(results), 1)}

    def quality_report(self) -> Dict:
        cats = self.classics_db.get_categories()
        report = []
        for cat in cats:
            r = self.batch_quality_check(cat["category"], limit=100)
            report.append({"category": cat["category"], "total": cat["count"], "avg_score": r["avg_score"], "grades": r["grades"]})
        return {"categories": report, "overall": self.batch_quality_check(limit=200)}

    def auto_proofread(self, classic_id: str) -> str:
        self.engine.current_task = "proofread"
        item = self.classics_db.get_by_id(classic_id)
        if not item:
            return "未找到"
        return self.ai.generate(self.engine.current_task or "generate", f"校对作品：《{item['title']}》{item['author']}\n{item['content']}\n指出错字、缺句、标点错误。")

    def auto_maintenance(self) -> Dict:
        results = {}
        dedup = self.dedup_check()
        results["dedup"] = f"发现 {dedup['duplicates']} 组疑似重复"
        quality = self.batch_quality_check(limit=100)
        results["quality"] = f"均分 {quality['avg_score']}"
        cats = self.classics_db.get_categories()
        target = ["唐诗", "宋词", "宋诗", "元曲", "经典散文", "蒙学", "经部", "子部", "史部", "集部"]
        missing = [c for c in target if c not in [x["category"] for x in cats]]
        results["missing"] = f"缺失：{', '.join(missing)}" if missing else "分类完整"
        backup_path = self.create_backup()
        results["backup"] = "备份完成" if isinstance(backup_path, str) and os.path.isfile(backup_path) else "备份失败"
        return results

    def health_dashboard(self) -> Dict:
        stats = self.classics_db.get_stats()
        quality = self.batch_quality_check(limit=200)
        return {"total": stats["total"], "total_chars": stats["total_chars"], "avg_score": quality["avg_score"], "grades": quality["grades"], "categories": stats["categories"][:10], "health_score": min(100, quality["avg_score"])}

    def dedup_check(self, category: str = "", threshold: float = 0.85) -> Dict:
        items = self.classics_db.search(category=category, limit=1000) if category else self.classics_db.search(limit=1000)
        duplicates = []
        seen = {}
        for item in items:
            fingerprint = content_fingerprint(item.get("title", ""), item.get("author", ""), item.get("content", ""))
            if fingerprint in seen:
                duplicates.append({"keep": seen[fingerprint], "dup": item["id"], "title": item["title"]})
            else:
                seen[fingerprint] = item["id"]
        return {"total": len(items), "duplicates": len(duplicates), "pairs": duplicates[:20]}

    def clean_low_quality(self, min_score: int = 30) -> str:
        quality = self.batch_quality_check(limit=500)
        to_delete = [item["id"] for item in quality.get("items", []) if item["score"] < min_score]
        removed = self.classics_db.delete_many(to_delete)
        self._clean_orphan_data()
        self.cache_mgr.clear()
        return f"已清理 {removed} 篇低质量数据"

    def clean_and_organize_database(self, min_score: int = 30, remove_dup: bool = True, convert_t2s: bool = True) -> Dict:
        converter = None
        if convert_t2s:
            try:
                import opencc
                converter = opencc.OpenCC("t2s")
            except Exception:
                converter = None
        self.create_backup()
        items = self.classics_db.search(limit=10000)
        seen = set()
        to_delete = set()
        duplicates_count = 0
        updated_count = 0
        for item in items:
            changed = False
            if converter:
                for field in ("title", "author", "content"):
                    value = str(item.get(field) or "")
                    converted = converter.convert(value)
                    if converted != value:
                        item[field] = converted
                        changed = True
            if changed:
                self.classics_db.conn.execute(
                    "UPDATE classics SET title=?, author=?, content=?, char_count=? WHERE id=?",
                    (item["title"], item["author"], item["content"], len(item["content"]), item["id"]),
                )
                updated_count += 1
            if remove_dup:
                fingerprint = content_fingerprint(item.get("title", ""), item.get("author", ""), item.get("content", ""))
                if fingerprint in seen:
                    to_delete.add(item["id"])
                    duplicates_count += 1
                    continue
                seen.add(fingerprint)
            if len(str(item.get("content", ""))) < 10 or not item.get("title"):
                to_delete.add(item["id"])
                continue
            if score_item(item)["score"] < min_score:
                to_delete.add(item["id"])
                continue
            if not item.get("category") or item["category"] == "未分类":
                new_cat = self.auto_classify(item["title"], item["content"])
                self.classics_db.conn.execute("UPDATE classics SET category=? WHERE id=?", (new_cat, item["id"]))
                updated_count += 1
        self.classics_db.conn.commit()
        removed = self.classics_db.delete_many(to_delete)
        self._clean_orphan_data()
        self.cache_mgr.clear()
        return {
            "removed": removed,
            "duplicates": duplicates_count,
            "updated": updated_count,
            "remaining": self.classics_db.get_total_count(),
        }

    def delete_classic(self, classic_id: str) -> str:
        try:
            with self.classics_db.conn:
                self.classics_db.conn.execute("DELETE FROM classics WHERE id=?", (classic_id,))
                self.classics_db.conn.execute("DELETE FROM user_notes WHERE classic_id=?", (classic_id,))
                self.classics_db.conn.execute("DELETE FROM favorites WHERE classic_id=?", (classic_id,))
                self.classics_db.conn.execute("DELETE FROM reading_history WHERE classic_id=?", (classic_id,))
            self.cache_mgr.clear()
            return "删除成功（含关联数据）"
        except Exception as e:
            return f"删除失败: {e}"

    def clean_database(self) -> Dict:
        items = self.classics_db.search(limit=10000)
        seen = set()
        to_delete = set()
        for item in items:
            title = str(item.get("title", ""))
            content = str(item.get("content", ""))
            if not title or len(content) < 10:
                to_delete.add(item["id"])
                continue
            fingerprint = content_fingerprint(title, item.get("author", ""), content)
            if fingerprint in seen:
                to_delete.add(item["id"])
            else:
                seen.add(fingerprint)
        deleted = self.classics_db.delete_many(to_delete)
        self._clean_orphan_data()
        self.cache_mgr.clear()
        return {"deleted": deleted, "remaining": self.classics_db.get_total_count()}

    def perfect_classify(self) -> Dict:
        items = self.classics_db.search(limit=5000)
        count = 0
        valid_cats = ["唐诗", "宋词", "宋诗", "元曲", "经典散文", "蒙学", "经部", "子部", "史部", "集部", "论语", "诗经", "楚辞"]
        with self.classics_db.conn:
            for item in items:
                if item.get("category") in valid_cats:
                    continue
                new_cat = self.auto_classify(item["title"], item["content"])
                self.classics_db.conn.execute("UPDATE classics SET category=? WHERE id=?", (new_cat, item["id"]))
                count += 1
        return {"message": f"已重新分类 {count} 篇作品"}

    def auto_optimize_database(self) -> Dict:
        result = self.auto_complete()
        dedup = self.dedup_check()
        return {"auto_complete": result, "dedup": dedup, "message": f"已补全{len(result['results'])}个分类，发现{dedup['duplicates']}组重复"}

    def auto_complete(self) -> Dict:
        cats = self.classics_db.get_categories()
        cat_names = [c["category"] for c in cats]
        target = ["唐诗", "宋词", "宋诗", "元曲", "经典散文", "蒙学", "经部", "子部", "史部", "集部"]
        missing = [c for c in target if c not in cat_names]
        results = []
        for cat in missing[:3]:
            r = self.smart_expand_advanced("", "", "", cat, 10)
            results.append({"category": cat, "imported": r["imported"]})
        return {"missing_categories": missing, "results": results}

    def validate_database(self) -> Dict:
        stats = self.classics_db.get_stats()
        quality = self.batch_quality_check(limit=100)
        cats = self.classics_db.get_categories()
        cat_names = [c["category"] for c in cats]
        expected = ["唐诗", "宋词", "宋诗", "元曲", "经典散文", "蒙学", "经部", "子部", "史部", "集部"]
        missing = [c for c in expected if c not in cat_names]
        prompt = f"""分析古典文学数据库健康状况：
总篇数：{stats['total']}，总字数：{stats['total_chars']}，质量均分：{quality['avg_score']}
已有分类：{', '.join(cat_names)}，缺失分类：{', '.join(missing)}
返回JSON：{{"health_score":"0-100","issues":["问题"],"suggestions":["建议"],"priority_actions":["优先行动"]}}"""
        try:
            report = json.loads(self.ai.generate(self.engine.current_task or "generate", prompt))
        except Exception:
            report = {"health_score": quality["avg_score"], "issues": [], "suggestions": [], "priority_actions": []}
        return {"stats": stats, "quality": quality, "missing": missing, "report": report}

    def get_expand_log(self) -> List[Dict]:
        return safe_json_load(app_path("data", "expand_log.json"), [])

    def _save_expand_log(self, log_data: Dict) -> None:
        logs = safe_json_load(app_path("data", "expand_log.json"), [])
        if not isinstance(logs, list):
            logs = []
        logs.append(log_data)
        safe_json_save(app_path("data", "expand_log.json"), logs)

    def auto_classify(self, title: str, content: str) -> str:
        self.engine.current_task = "classify"
        prompt = f"""请分析以下作品的体裁和内容，将其归入最合适的分类。
分类选项：经部、史部、子部、集部、蒙学、唐诗、宋词、宋诗、元曲、经典散文、论语、诗经、楚辞
作品：《{title}》
内容：{content[:200]}
仅回复一个分类名称，不要解释。"""
        cat = (self.ai.generate("classify", prompt) or "").strip()
        if cat.startswith("AI请求失败") or "API Key无效" in cat:
            cat = ""
        valid = ["经部", "史部", "子部", "集部", "蒙学", "唐诗", "宋词", "宋诗", "元曲", "经典散文", "论语", "诗经", "楚辞"]
        if cat not in valid:
            if any(w in title + content for w in ["论语", "子曰"]):
                cat = "论语"
            elif any(w in title + content for w in ["诗", "风", "雅", "颂"]):
                cat = "诗经"
            elif any(w in title + content for w in ["楚辞", "离骚"]):
                cat = "楚辞"
            elif any(w in title + content for w in ["词", "宋"]):
                cat = "宋词"
            elif any(w in title + content for w in ["诗", "唐"]):
                cat = "唐诗"
            else:
                cat = "集部"
        return cat

    def smart_expand_advanced(self, era: str, genre: str, school: str, category: str, count: int, mode: str = "token", progress=None, should_cancel=None, checkpoint=None, resume=None) -> Dict:
        """智能扩充（使用线程池并行获取全文，提升效率；支持阶段快照）。"""
        self.engine.current_task = "expand"
        state = dict(resume or {})

        def tick(value, message=""):
            if should_cancel and should_cancel():
                raise RuntimeError("任务已取消")
            if progress:
                progress(value, message)

        def save(stage, **fields):
            state.update(fields)
            state["stage"] = stage
            if checkpoint:
                checkpoint(dict(state))

        tick(3, "生成篇目清单")
        items = state.get("items")
        if not isinstance(items, list):
            prompt = f"请列出{count}首符合以下条件的著名作品：\n"
            if era:
                prompt += f"时代：{era}\n"
            if genre:
                prompt += f"体裁：{genre}\n"
            if school:
                prompt += f"流派：{school}\n"
            if category:
                prompt += f"分类：{category}\n"
            prompt += "每行格式：篇名|作者|朝代。只列出篇目，不可杜撰。"
            result = self.ai.generate(self.engine.current_task or "generate", prompt)
            items = []
            for line in result.strip().split('\n'):
                parts = line.strip().split('|')
                if len(parts) >= 2:
                    title, author = parts[0].strip(), parts[1].strip()
                    dynasty = parts[2].strip() if len(parts) > 2 else ""
                    if title and author:
                        existing = self.classics_db.search(keyword=title, limit=1)
                        if existing:
                            continue
                        items.append({"title": title, "author": author, "dynasty": dynasty})
            save("items", items=items)
        tick(15, "解析篇目")

        # 并行获取全文
        def fetch_content(item):
            try:
                content = self.ai.generate(self.engine.current_task or "generate", f"请提供《{item['title']}》{item['author']}的全文，只输出原文。")
                return {**item, "content": content}
            except Exception:
                return None

        full_items = state.get("full_items")
        if not isinstance(full_items, list):
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = [executor.submit(fetch_content, item) for item in items]
                full_items = []
                for future in as_completed(futures):
                    if should_cancel and should_cancel():
                        raise RuntimeError("任务已取消")
                    res = future.result()
                    if res and len(res.get("content", "")) > 20:
                        full_items.append(res)
                    if items:
                        tick(min(65, 20 + 45 * len(full_items) / max(1, len(items))), "补全全文")
            save("full_items", full_items=full_items)
        tick(70, "分类与质量过滤")

        processed_items = state.get("processed")
        if not isinstance(processed_items, list):
            processed_items = []
            for item in full_items:
                content = item["content"]
                if content.startswith("AI请求失败") or "API Key无效" in content:
                    continue
                auto_cat = self.auto_classify(item["title"], content)
                processed_items.append({
                    "title": item["title"],
                    "author": item["author"],
                    "dynasty": item.get("dynasty", "") or "未知",
                    "category": auto_cat,
                    "content": content,
                    "translation": "",
                    "annotation": "",
                    "tags": f"{auto_cat},AI扩充",
                    "is_famous": 0,
                    "difficulty_level": 2
                })
            processed_items = self._filter_items_by_quality(processed_items, min_score=40)
            save("processed", processed=processed_items)

        imported = 0
        for item in processed_items:
            exists = self.classics_db.conn.execute(
                "SELECT 1 FROM classics WHERE title = ? AND author = ? LIMIT 1",
                (item["title"], item["author"]),
            ).fetchone()
            if exists:
                continue
            try:
                self.classics_db.insert(item)
                imported += 1
            except Exception:
                pass
            if processed_items:
                tick(min(98, 75 + 23 * imported / max(1, len(processed_items))), "入库")
        save("done", imported=imported)
        self.classics_db.improve_data_quality()
        self._save_expand_log({"time": str(datetime.now()), "category": category, "count": imported, "mode": mode})
        self.cache_mgr.clear()
        tick(100, "完成")
        return {"imported": imported, "total": len(processed_items), "resumed": bool(state.get("stage") and resume)}

    # 扩充预览（不写入数据库）
    def get_expand_candidates(self, era: str, genre: str, school: str, category: str, count: int) -> List[Dict]:
        """生成候选条目（不写入数据库），供前端预览"""
        self.engine.current_task = "expand"
        prompt = f"请列出{count}首符合以下条件的著名作品：\n"
        if era: prompt += f"时代：{era}\n"
        if genre: prompt += f"体裁：{genre}\n"
        if school: prompt += f"流派：{school}\n"
        if category: prompt += f"分类：{category}\n"
        prompt += "每行格式：篇名|作者|朝代。只列出篇目，不可杜撰。"
        result = self.ai.generate(self.engine.current_task or "generate", prompt)
        # 检查AI错误
        if result and ("错误" in result or "失败" in result or "网络" in result or "超时" in result or "Key" in result):
            return []
        candidates = []
        for line in result.strip().split('\n'):
            parts = line.strip().split('|')
            if len(parts) >= 2:
                candidates.append({
                    "title": parts[0].strip(),
                    "author": parts[1].strip(),
                    "dynasty": parts[2].strip() if len(parts) > 2 else ""
                })
        return candidates

    # 确认导入候选（并行获取全文）
    def confirm_import_candidates(self, candidates_json: str, progress=None, should_cancel=None) -> Dict:
        """确认导入候选条目（前端预览后调用）。"""
        def tick(value, message=""):
            if should_cancel and should_cancel():
                raise RuntimeError("任务已取消")
            if progress:
                progress(value, message)

        tick(3, "校验候选")
        try:
            candidates = json.loads(candidates_json) if isinstance(candidates_json, str) else candidates_json
        except (TypeError, ValueError):
            return {"imported": 0, "error": "候选数据格式错误"}
        if not isinstance(candidates, list):
            return {"imported": 0, "error": "候选数据格式错误"}
        candidates = [item for item in candidates if isinstance(item, dict)][:200]
        tick(8, "开始获取全文")

        def fetch_and_build(item):
            try:
                title = str(item.get("title", "")).strip()
                author = str(item.get("author", "")).strip() or "佚名"
                if not title:
                    return None
                content = self.ai.generate(self.engine.current_task or "generate", f"请提供《{title}》{author}的全文，只输出原文。")
                if not content or content.startswith("AI请求失败") or "API Key无效" in content:
                    return None
                auto_cat = item.get("category") or self.auto_classify(title, content)
                new_item = {
                    "title": title,
                    "author": author,
                    "dynasty": item.get("dynasty", "") or "未知",
                    "category": auto_cat,
                    "content": content,
                    "translation": "",
                    "annotation": "",
                    "tags": f"{auto_cat},AI扩充",
                    "is_famous": 0,
                    "difficulty_level": 2,
                }
                # 入库前按字典评分，不能按 id 查库（此时还没有 id）
                if score_item(new_item)["score"] >= 40:
                    return new_item
                return None
            except Exception as exc:  # noqa: BLE001
                log("warning", f"候选构建失败: {str(exc)[:100]}")
                return None

        built = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(fetch_and_build, item) for item in candidates]
            for future in as_completed(futures):
                if should_cancel and should_cancel():
                    raise RuntimeError("任务已取消")
                try:
                    result = future.result()
                except Exception:
                    result = None
                if result:
                    built.append(result)
                if candidates:
                    tick(min(70, 10 + 60 * len(built) / max(1, len(candidates))), "获取全文")

        tick(75, "写入数据库")
        imported = 0
        for item in built:
            exists = self.classics_db.conn.execute(
                "SELECT 1 FROM classics WHERE title = ? AND author = ? LIMIT 1",
                (item["title"], item["author"]),
            ).fetchone()
            if exists:
                continue
            if self.classics_db.insert(item):
                imported += 1
            if built:
                tick(min(98, 78 + 20 * imported / max(1, len(built))), "写入数据库")
        self.classics_db.improve_data_quality()
        self.cache_mgr.clear()
        tick(100, "完成")
        return {"imported": imported, "candidates": len(built)}

    def _filter_items_by_quality(self, items: List[Dict], min_score: int = 40) -> List[Dict]:
        """过滤低质量候选条目（不依赖数据库，纯字典评分）。"""
        filtered = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if score_item(item)["score"] >= min_score:
                filtered.append(item)
        return filtered

    def _clean_orphan_data(self) -> None:
        with self.classics_db.conn:
            self.classics_db.conn.execute("DELETE FROM favorites WHERE classic_id NOT IN (SELECT id FROM classics)")
            self.classics_db.conn.execute("DELETE FROM user_notes WHERE classic_id NOT IN (SELECT id FROM classics)")
            self.classics_db.conn.execute("DELETE FROM reading_history WHERE classic_id NOT IN (SELECT id FROM classics)")


# ---------------------- 创作类 Mixin ----------------------
class CreationMixin:
    @safe_api
    def generate(self, genre: str, topic: str, style_info: Dict) -> List[str]:
        self.engine.current_task = "generate"
        try:
            style_key = json.dumps(style_info or {}, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            style_key = str(style_info)
        cache_key = f"gen:{genre}:{topic}:{style_key}"
        cached = self.cache_mgr.get(cache_key)
        if cached:
            return cached

        prompt = self.style_mgr.build_prompt(genre, topic, style_info)
        results = []
        for _ in range(3):
            text = self.ai.generate("generate", prompt)
            text = (text or "").strip()
            if text:
                results.append(text)

        usable = [text for text in results if not text.startswith("AI请求失败") and "API Key无效" not in text]
        if usable:
            self.preferences.record(genre, style_info or {}, topic)
            self.cache_mgr.set(cache_key, results, ttl=1800)
        return results if results else ["生成失败，请检查网络或 API 设置"]

    def get_styles(self, g: str) -> List[Dict]:
        return self.style_mgr.get_styles_for_genre(g)

    def check_poem(self, poem: str, genre: str) -> str:
        from poetry_checker import check_poem as check_poem_text

        lines = [line.strip() for line in str(poem or "").split("\n") if line.strip()]
        return check_poem_text(genre, lines)

    def polish_line(self, poem: str) -> Dict:
        """炼字建议：返回 ``{"suggestions": [{original, replacements, reason}]}``。"""
        self.engine.current_task = "polish"
        prompt = (
            "请为下面的诗句提供炼字建议，指出 1-6 个可以替换的字词。\n"
            '只输出 JSON，格式：{"suggestions":[{"original":"原字词","replacements":["替换1","替换2"],"reason":"理由"}]}\n'
            f"诗句：{poem}"
        )
        try:
            data = self.ai.generate_structured("polish", prompt, required=["suggestions"], ttl=3600)
        except Exception as exc:  # noqa: BLE001
            return {"suggestions": [], "error": str(exc)}
        suggestions = []
        for item in data.get("suggestions", []) if isinstance(data.get("suggestions"), list) else []:
            if not isinstance(item, dict):
                continue
            original = str(item.get("original", "")).strip()
            replacements = item.get("replacements")
            if not original or not isinstance(replacements, list):
                continue
            suggestions.append(
                {
                    "original": original,
                    "replacements": [str(value) for value in replacements[:5]],
                    "reason": str(item.get("reason", ""))[:120],
                }
            )
        return {"suggestions": suggestions[:8]}

    def transform_style(self, poem: str, target: str) -> str:
        """把作品改写为目标体裁/风格，返回改写后的文本。"""
        self.engine.current_task = "transform"
        target = str(target or "现代诗").strip()
        prompt = (
            f"请把下面的作品改写成{target}，保留原意、意象与情感，只输出改写后的正文，不要解释：\n{poem}"
        )
        return self.ai.generate(self.engine.current_task or "generate", prompt)

    def critique(self, poem: str, genre: str) -> str:
        self.engine.current_task = "critique"
        return self.ai.generate(self.engine.current_task or "generate", f"品评这首{genre}：{poem}")

    def smart_continue(self, line: str) -> List[Dict]:
        self.engine.current_task = "continue"
        ds = [{"name": "意境延伸", "i": "保持意境"},
              {"name": "情感转折", "i": "情感转折"},
              {"name": "哲理升华", "i": "由景入理"}]
        return [{"direction": d["name"], "full_poem": self.ai.generate(self.engine.current_task or "generate", f"续写：{line} 方向：{d['i']}")} for d in ds]

    def create_cento(self, kw: str) -> str:
        self.engine.current_task = "cento"
        return self.ai.generate(self.engine.current_task or "generate", f"集句创作：{kw}")

    def generate_couplet(self, upper: str = "") -> str:
        self.engine.current_task = "couplet"
        return self.ai.generate(self.engine.current_task or "generate", f"对联：{upper}" if upper else "创作一副完整对联")

    def poem_response(self, org: str) -> str:
        self.engine.current_task = "response"
        return self.ai.generate(self.engine.current_task or "generate", f"唱和：{org}")

    def allusion_deep_dive(self, a: str) -> str:
        self.engine.current_task = "allusion"
        return self.ai.generate(self.engine.current_task or "generate", f"典故解析：{a}")

    def recreate_buyun(self, classic_id: str) -> str:
        self.engine.current_task = "recreate"
        item = self.classics_db.get_by_id(classic_id)
        if not item:
            return "未找到"
        return self.ai.generate(self.engine.current_task or "generate", f"步韵创作，原诗：《{item['title']}》\n{item['content']}\n用相同韵脚创作新诗。")

    def recreate_fangxie(self, classic_id: str, new_topic: str = "") -> str:
        self.engine.current_task = "recreate"
        item = self.classics_db.get_by_id(classic_id)
        if not item:
            return "未找到"
        return self.ai.generate(self.engine.current_task or "generate", f"模仿《{item['title']}》风格创作「{new_topic or item['title']}」。\n原诗：{item['content']}")

    def recreate_fanxie(self, classic_id: str) -> str:
        self.engine.current_task = "recreate"
        item = self.classics_db.get_by_id(classic_id)
        if not item:
            return "未找到"
        return self.ai.generate(self.engine.current_task or "generate", f"反其意创作：《{item['title']}》\n{item['content']}")

    def recreate_kuoxie(self, classic_id: str) -> str:
        self.engine.current_task = "recreate"
        item = self.classics_db.get_by_id(classic_id)
        if not item:
            return "未找到"
        return self.ai.generate(self.engine.current_task or "generate", f"扩写：《{item['title']}》\n{item['content']}")

    def recreate_suoxie(self, classic_id: str) -> str:
        self.engine.current_task = "recreate"
        item = self.classics_db.get_by_id(classic_id)
        if not item:
            return "未找到"
        return self.ai.generate(self.engine.current_task or "generate", f"缩写：《{item['title']}》\n{item['content']}")

    def recreate_modern(self, classic_id: str) -> str:
        self.engine.current_task = "recreate"
        item = self.classics_db.get_by_id(classic_id)
        if not item:
            return "未找到"
        return self.ai.generate(self.engine.current_task or "generate", f"现代文改写：《{item['title']}》\n{item['content']}")

    def recreate_translate(self, classic_id: str, lang: str = "en") -> str:
        self.engine.current_task = "translate"
        item = self.classics_db.get_by_id(classic_id)
        if not item:
            return "未找到"
        return self.ai.generate(self.engine.current_task or "generate", f"翻译成{lang}：《{item['title']}》\n{item['content']}")

    def recreate_calligraphy(self, classic_id: str, style: str = "颜体") -> str:
        item = self.classics_db.get_by_id(classic_id)
        if not item:
            return "未找到"
        return f"【{style}书法】\n{item['content']}"

    def recreate_classic(self, classic_id: str, mode: str = "buyun", extra: str = "") -> str:
        """统一二创入口。

        mode: buyun / fangxie / fanxie / kuoxie / suoxie / modern / translate / calligraphy
        extra: 仿写主题、翻译语言或书法字体
        """
        mode = str(mode or "buyun").lower()
        if mode == "fangxie":
            return self.recreate_fangxie(classic_id, extra)
        if mode == "translate":
            return self.recreate_translate(classic_id, extra or "en")
        if mode == "calligraphy":
            return self.recreate_calligraphy(classic_id, extra or "颜体")
        mapping = {
            "buyun": self.recreate_buyun,
            "fanxie": self.recreate_fanxie,
            "kuoxie": self.recreate_kuoxie,
            "suoxie": self.recreate_suoxie,
            "modern": self.recreate_modern,
        }
        function = mapping.get(mode)
        return function(classic_id) if function else "不支持的二创模式"



# ---------------------- 教学类 Mixin ----------------------
class TeachingMixin:
    @staticmethod
    def _profile_dict(profile: str) -> Dict:
        result = {}
        for part in str(profile or "").split("|"):
            if ":" in part:
                key, value = part.split(":", 1)
                result[key.strip()] = value.strip()
        return result

    @staticmethod
    def _profile_text(profile: str) -> str:
        data = TeachingMixin._profile_dict(profile)
        if not data:
            return "常规学情"
        labels = {"stage": "学段", "hours": "课时", "textbook": "教材", "student": "学生水平"}
        return "；".join(f"{labels.get(k, k)}：{v}" for k, v in data.items() if v)

    @staticmethod
    def _offline_teaching_plan(item: Dict, level: str = "standard", profile: str = "") -> Dict:
        """不调用 AI 也能立即出教案的离线骨架；只写可证明的内容。"""
        title = item.get("title", "")
        author = item.get("author", "佚名")
        dynasty = item.get("dynasty", "")
        category = item.get("category", "")
        content = item.get("content", "") or ""
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        annotation = (item.get("annotation") or "").strip()
        translation = (item.get("translation") or "").strip()
        objectives = {
            "beginner": ["读准字音，能正确、流利地朗读", "说出作品写了什么", "当堂背诵"],
            "standard": ["把握意象与情感", "分析关键句的作用", "完成课堂练习并订正"],
            "advanced": ["分析艺术手法与结构", "比较同题材作品", "写一段 200 字鉴赏"],
        }.get(level, ["把握意象与情感", "分析关键句的作用", "完成课堂练习并订正"])
        stage = TeachingMixin._profile_dict(profile).get("stage", "")
        hours = TeachingMixin._profile_dict(profile).get("hours", "1")
        if stage == "primary":
            objectives = ["借助拼音读通全文", "说出诗中的画面", "当堂背诵并积累一个好词"]
        elif stage == "senior":
            objectives = ["分析意象与结构的关系", "比较同题材作品", "形成有依据的鉴赏短评"]
        elif stage == "junior":
            objectives = ["读通文意，积累重点字词", "分析关键句的表达效果", "完成课堂练习并订正"]
        key_points = []
        if annotation:
            key_points.append(annotation[:120])
        if item.get("tags"):
            key_points.append("关键词：" + str(item["tags"])[:80])
        if not key_points:
            key_points.append(f"《{title}》的意象、情感与结构")
        analysis = {
            "background": annotation or f"{dynasty}{author}《{title}》，属{category}。",
            "text_analysis": translation or f"原文共 {len(content)} 字、{len(lines)} 句；逐句译文待补充。",
            "artistic": "结合原文意象与语言节奏品读；离线版不编造未核实的风格判断。",
            "rhythm": "格律/曲牌信息待补充；可结合原文句式和押韵观察。",
            "culture": "文化知识点待补充；可参考篇目注释与同作者作品。",
            "teaching": "先读通，再抓意象，最后落到背诵与练习。",
        }
        line_rows = [
            {"original": line, "translation": "", "keywords": "", "rhetoric": "", "structure": ""}
            for line in lines
        ]
        options = [category or "其他", "唐诗", "宋词", "元曲"]
        deduped = []
        for option in options:
            if option not in deduped:
                deduped.append(option)
        while len(deduped) < 2:
            deduped.append("其他")
        exercises = [
            {"type": "填空", "question": f"《{title}》的作者是____。", "options": [], "answer": author,
             "explanation": f"作者：{author}。"},
            {"type": "选择", "question": f"《{title}》属于哪一分类？", "options": deduped,
             "answer": deduped.index(category) if category in deduped else 0,
             "explanation": f"分类：{category}。"},
            {"type": "简答", "question": f"用自己的话概括《{title}》的主要内容。", "options": [],
             "answer": "言之有据，能引用原文关键词即可。", "explanation": "考查整体感知，不要求唯一答案。"},
        ]
        return {
            "title": title, "author": author, "dynasty": dynasty, "content": content,
            "category": category, "level": level, "analysis": analysis,
            "line_teaching": {"lines": line_rows}, "exercises": {"exercises": exercises},
            "related_works": [], "author_info": {"name": author, "dynasty": dynasty, "works_count": 0, "representative": []},
            "knowledge_points": [str(item.get("tags") or "")] if item.get("tags") else [],
            "objectives": objectives, "key_points": key_points,
            "homework": f"背诵并默写《{title}》；用 150 字写出一个画面或一处情感。" if str(hours) != "2" else f"背诵并默写《{title}》；完成一段 200 字鉴赏，并与同题材作品比较。",
            "board_design": f"《{title}》／{author}\n意象：____　情感：____　手法：____",
            "profile": profile or "",
            "source": "offline", "quality": "offline",
        }

    def _ai_teaching_plan(self, item: Dict, level: str = "standard", profile: str = ""):
        """一次结构化调用生成完整教案；失败返回 None，由离线骨架兜底。"""
        prompt = f"""你是中学语文备课专家。为《{item.get('title','')}》设计一份{level}教案。
学情参数：{TeachingMixin._profile_text(profile)}
只输出 JSON 对象，字段：
{{"objectives":["教学目标"],"key_points":["重点"],"background":"创作背景","text_analysis":"文本解读",
"line_teaching":[{{"original":"原句","translation":"翻译","keywords":"关键词","rhetoric":"修辞","structure":"结构作用"}}],
"artistic":"意境","rhythm":"格律","culture":"文化拓展","teaching":"教学建议",
"exercises":[{{"type":"选择/填空/简答","question":"题目","options":[],"answer":0,"explanation":"解析"}}],
"homework":"作业","board_design":"板书设计"}}
要求：忠实原文，不编造不确定的典故；翻译用现代汉语；题目必须有答案。
原文：{item.get('content','')[:1200]}"""
        try:
            try:
                self.engine._ensure().max_tokens = max(1800, getattr(self.engine._ensure(), "max_tokens", 512))
            except Exception:
                pass
            data = self.ai.generate_structured("teaching", prompt, required=["objectives", "line_teaching", "exercises", "background", "text_analysis"])
            if not isinstance(data, dict) or not data.get("line_teaching"):
                return None
            data["source"] = "ai"
            data["quality"] = "ai"
            try:
                self.classics_db.enqueue_ai_review("teaching_plan", item.get("id", ""), {
                    "title": item.get("title", ""), "author": item.get("author", ""),
                    "level": level, "profile": profile,
                    "objectives": data.get("objectives", []), "summary": str(data.get("teaching", ""))[:200],
                })
            except Exception:
                pass
            return data
        except Exception:
            return None

    def get_ai_review_queue(self, status: str = "pending") -> List[Dict]:
        return self.classics_db.list_ai_review(status)

    def get_ai_review_stats(self) -> Dict:
        return self.classics_db.get_review_stats()

    def review_ai_queue(self, review_id: str, decision: str, reviewer: str = "", notes: str = "", edits_json: str = "", review_minutes: float = 0, edited: bool = False) -> Dict:
        item = self.classics_db.get_ai_review(review_id)
        if not item:
            return {"success": False, "message": "审核项不存在"}
        payload = item.get("payload", {}) or {}
        if edits_json:
            try:
                changes = json.loads(edits_json) if isinstance(edits_json, str) else dict(edits_json or {})
                if isinstance(changes, dict):
                    payload.update(changes)
                    edited = True
            except (TypeError, ValueError):
                pass
        ok = self.classics_db.review_ai_item(review_id, decision, reviewer, notes, review_minutes, 1 if edited else 0)
        if not ok:
            return {"success": False, "message": "审核参数错误"}
        if decision == "approved":
            kind = item.get("kind")
            try:
                if kind == "translation_draft":
                    cid = payload.get("classic_id") or item.get("classic_id")
                    self.classics_db.conn.execute(
                        """UPDATE classics SET translation=?, annotation=CASE WHEN ?<>'' THEN ? ELSE annotation END,
                           translation_status='approved',
                           annotation_status=CASE WHEN ?<>'' THEN 'approved' ELSE annotation_status END,
                           reviewed_by=?, reviewed_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
                           WHERE id=?""",
                        (payload.get("translation", ""), payload.get("annotation", ""), payload.get("annotation", ""),
                         payload.get("annotation", ""), reviewer or "reviewer", cid),
                    )
                    self.classics_db.conn.commit()
                elif kind in ("reading_question", "quiz_question"):
                    cid = payload.get("classic_id") or item.get("classic_id")
                    work = self.classics_db.get_by_id(cid) or {}
                    self.classics_db.conn.execute(
                        """INSERT OR REPLACE INTO question_bank
                           (id,classic_id,category,dynasty,difficulty,type,question,options,answer,explanation,
                            cognitive,rubric,source,verified)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'reviewed',1)""",
                        (f"review_{review_id}", cid, work.get("category", ""), work.get("dynasty", ""),
                         2, payload.get("type", "简答"), payload.get("question", ""), "[]",
                         payload.get("answer", ""), payload.get("explanation", ""),
                         payload.get("cognitive", "分析"), json.dumps(payload.get("rubric", []), ensure_ascii=False)),
                    )
                    self.classics_db.conn.commit()
            except Exception as exc:
                return {"success": True, "message": f"审核已记录，写入失败：{str(exc)[:80]}"}
        return {"success": True, "message": "已通过" if decision == "approved" else "已拒绝"}

    def get_intertext(self, classic_id: str) -> List[Dict]:
        try:
            payload = safe_json_load(resource_path("resources", "intertext.json"), {})
            links = payload.get("links", {}) if isinstance(payload, dict) else {}
            rows = links.get(classic_id, []) if isinstance(links, dict) else []
            return [row for row in rows if row.get("review_status") != "rejected"]
        except Exception:
            return []

    def get_word_notes(self, classic_id: str = "") -> Dict:
        """常用词/典故点注；不依赖作品，可离线。"""
        words = safe_json_load(resource_path("resources", "word_notes.json"), [])
        allusions = safe_json_load(resource_path("resources", "allusion_db.json"), [])
        return {"words": words if isinstance(words, list) else [],
                "allusions": allusions if isinstance(allusions, list) else []}

    def get_teaching_plan(self, classic_id: str, level: str = "standard", profile: str = "") -> Dict:
        """返回预置/缓存教案；没有则按需生成离线骨架。"""
        cache_level = level if not profile else f"{level}|{profile}"
        cached = self.classics_db.get_teaching_plan(classic_id, cache_level)
        if cached:
            return {"available": True, "plan": cached, "source": cached.get("_source", "cache")}
        if not profile:
            try:
                path = resource_path("resources", "teaching_plans.json")
                if os.path.exists(path):
                    payload = json.load(open(path, encoding="utf-8"))
                    plan = (payload.get("plans", {}) or {}).get(f"{classic_id}|{level}")
                    if plan:
                        self.classics_db.save_teaching_plan(classic_id, cache_level, plan, "prebuilt")
                        plan["_source"] = "prebuilt"
                        return {"available": True, "plan": plan, "source": "prebuilt"}
            except Exception:
                pass
        item = self.classics_db.get_by_id(classic_id)
        if not item:
            return {"available": False, "error": "未找到该作品"}
        # 全量按需预置：任意一篇第一次打开都立即得到离线教案，并写入缓存
        plan = self._offline_teaching_plan(item, level, profile)
        plan["_source"] = "offline"
        self.classics_db.save_teaching_plan(classic_id, cache_level, plan, "offline")
        return {"available": True, "plan": plan, "source": "offline"}

    def save_teaching_plan_custom(self, classic_id: str, level: str, profile: str, fields_json: str) -> Dict:
        try:
            fields = json.loads(fields_json) if isinstance(fields_json, str) else dict(fields_json or {})
        except (TypeError, ValueError):
            return {"error": "教案字段格式错误"}
        current = self.get_teaching_plan(classic_id, level, profile)
        if not current.get("available"):
            return {"error": "未找到教案"}
        plan = current["plan"]
        allowed = {"objectives", "key_points", "background", "text_analysis", "artistic", "rhythm",
                   "culture", "teaching", "homework", "board_design"}
        for key, value in fields.items():
            if key in allowed:
                plan[key] = value
        if "background" in fields or "text_analysis" in fields:
            analysis = plan.get("analysis") if isinstance(plan.get("analysis"), dict) else {}
            for key in ("background", "text_analysis", "artistic", "rhythm", "culture", "teaching"):
                if key in fields:
                    analysis[key] = fields[key]
            plan["analysis"] = analysis
        plan["source"] = "teacher"
        plan["_source"] = "teacher"
        cache_level = level if not profile else f"{level}|{profile}"
        self.classics_db.save_teaching_plan(classic_id, cache_level, plan, "teacher")
        self.classics_db.save_teaching_version(classic_id, level, profile, plan, "teacher")
        return {"available": True, "plan": plan, "source": "teacher"}

    def get_teaching_versions(self, classic_id: str, level: str, profile: str = "") -> List[Dict]:
        return self.classics_db.list_teaching_versions(classic_id, level, profile)

    def restore_teaching_plan(self, classic_id: str, level: str, profile: str = "") -> Dict:
        cache_level = level if not profile else f"{level}|{profile}"
        self.classics_db.conn.execute(
            "DELETE FROM teaching_plans WHERE classic_id=? AND level=?", (classic_id, cache_level)
        )
        self.classics_db.conn.commit()
        return self.get_teaching_plan(classic_id, level, profile)

    def _assemble_teaching_plan(self, item: Dict, level: str, force: bool = False, profile: str = "") -> Dict:
        if not force:
            cached = self.get_teaching_plan(item["id"], level, profile)
            if cached.get("available"):
                return cached["plan"]
        plan = self._ai_teaching_plan(item, level, profile) if force and self.engine.is_configured() else None
        if not plan:
            plan = self._offline_teaching_plan(item, level, profile)
        # 补齐离线分析字段，保证旧 UI 兼容
        offline = self._offline_teaching_plan(item, level, profile)
        for key, value in offline.items():
            plan.setdefault(key, value)
        related = self.classics_db.search(keyword=item["author"], category=item["category"], limit=5)
        plan["related_works"] = [{"id": r["id"], "title": r["title"], "author": r["author"]} for r in related if r["id"] != item["id"]]
        author_works = self.classics_db.search(keyword=item["author"], limit=10)
        plan["author_info"] = {"name": item["author"], "dynasty": item["dynasty"], "works_count": len(author_works),
                               "representative": [{"title": w["title"], "id": w["id"]} for w in author_works[:3]]}
        plan["title"], plan["author"], plan["dynasty"] = item["title"], item["author"], item["dynasty"]
        plan["content"], plan["level"], plan["category"] = item["content"], level, item.get("category", "")
        plan["profile"] = profile or ""
        plan["id"] = item["id"]
        cache_level = level if not profile else f"{level}|{profile}"
        self.classics_db.save_teaching_plan(item["id"], cache_level, plan, plan.get("source", "ai"))
        return plan

    def teaching_workflow(self, classic_id: str, level: str = "standard", progress=None, should_cancel=None, checkpoint=None, resume=None, force: bool = False, profile: str = "") -> Dict:
        self.engine.current_task = "teaching"

        def tick(value, message=""):
            if should_cancel and should_cancel():
                raise RuntimeError("任务已取消")
            if progress:
                progress(value, message)

        item = self.classics_db.get_by_id(classic_id)
        if not item:
            return {"error": "未找到该作品"}
        tick(10, "读取作品")
        cache_key = f"{classic_id}_{level}_{profile}"
        if not force and cache_key in self.teaching_cache:
            tick(100, "使用内存缓存")
            return self.teaching_cache[cache_key]
        tick(30, "检查预置教案")
        plan = self._assemble_teaching_plan(item, level, force=force, profile=profile)
        self.teaching_cache[cache_key] = plan
        try:
            self.classics_db.conn.execute("UPDATE classics SET teaching_data=? WHERE id=?", (json.dumps(plan, ensure_ascii=False), classic_id))
            self.classics_db.conn.commit()
        except Exception:
            pass
        if checkpoint:
            checkpoint({"stage": "done", "plan": plan})
        tick(100, "教案完成")
        return plan

    def _open_quiz_questions(self, category: str, count: int) -> List[Dict]:
        """从教案/原文生成带量规的开放题；不自动判分。"""
        if count <= 0:
            return []
        rows = self.classics_db.conn.execute(
            """SELECT c.id,c.title,c.author,c.category,t.data
               FROM classics c LEFT JOIN teaching_plans t
               ON t.classic_id=c.id AND t.level='standard'
               WHERE c.category=? AND c.verified=1
               ORDER BY RANDOM() LIMIT ?""",
            (category, max(1, count * 3)),
        ).fetchall()
        questions = []
        seen = set()
        approved = self.classics_db.conn.execute(
            """SELECT classic_id,question,answer,explanation,cognitive,rubric
               FROM question_bank
               WHERE category=? AND type='简答' AND verified=1 AND cognitive IN ('理解','分析')
               ORDER BY RANDOM() LIMIT ?""",
            (category, max(1, count)),
        ).fetchall()
        for row in approved:
            try:
                rubric = json.loads(row["rubric"] or "[]")
            except (TypeError, ValueError):
                rubric = []
            questions.append({
                "type": "简答", "question": row["question"], "options": [],
                "answer": row["answer"], "explanation": row["explanation"] or "开放题，按量规人工评分。",
                "rubric": rubric, "auto_gradable": False,
                "cognitive": row["cognitive"] or "分析", "classic_id": row["classic_id"],
            })
            seen.add(row["question"])
        for row in rows:
            if len(questions) >= count:
                break
            data = {}
            try:
                data = json.loads(row["data"]) if row["data"] else {}
            except (TypeError, ValueError):
                data = {}
            exercise = None
            exercise_data = data.get("exercises") if isinstance(data.get("exercises"), dict) else {}
            for item in (exercise_data or {}).get("exercises", []):
                if isinstance(item, dict) and item.get("type") == "简答":
                    exercise = item
                    break
            if exercise:
                question = exercise.get("question", "")
                answer = exercise.get("answer", "")
            else:
                question = f"结合《{row['title']}》原文，分析一个关键意象及其作用。"
                answer = "参考：指出意象，引用原文，说明情感或结构作用。"
            if not question or question in seen:
                continue
            seen.add(question)
            questions.append({
                "type": "简答",
                "question": question,
                "options": [],
                "answer": answer,
                "explanation": "开放题，按量规人工评分。",
                "rubric": [
                    {"dimension": "内容理解", "points": 40, "criteria": "准确引用原文，理解无误"},
                    {"dimension": "分析深度", "points": 40, "criteria": "指出手法/结构/情感并说明关系"},
                    {"dimension": "语言表达", "points": 20, "criteria": "条理清楚，术语准确"},
                ],
                "auto_gradable": False,
                "cognitive": "分析",
                "classic_id": row["id"],
            })
        return questions

    def generate_quiz(self, category: str = "唐诗", difficulty: int = 1, count: int = 5, types: str = "选择", blueprint: str = "basic") -> Dict:
        self.engine.current_task = "quiz"
        cache_key = f"quiz_{category}_{difficulty}_{count}_{types}_{blueprint}"
        if cache_key in self.teaching_cache:
            return self.teaching_cache[cache_key]
        blueprint = blueprint if blueprint in ("basic", "ability", "comprehensive") else "basic"
        objective_count = count if blueprint == "basic" else max(1, count // 2)
        open_count = 0 if blueprint == "basic" else max(0, count - objective_count)
        # 基础卷优先走本地题库；只有“新题/鉴赏”等显式需求才交给 AI
        type_set = {part.strip() for part in str(types or "选择").split(",") if part.strip()}
        if type_set == {"选择"} and int(difficulty or 1) <= 1:
            try:
                from question_bank import build_bank, load_prebuilt, sample_bank

                prebuilt = load_prebuilt(category)
                if blueprint == "basic" and len(prebuilt) >= int(count):
                    bank = random.sample(prebuilt, int(count))
                    result = {"questions": bank, "source": "bank", "bank_total": len(prebuilt), "blueprint": blueprint}
                    self.teaching_cache[cache_key] = result
                    return result
                if len(prebuilt) >= objective_count:
                    bank = random.sample(prebuilt, objective_count)
                else:
                    build_bank(self.classics_db.conn, category=category)
                    bank = sample_bank(self.classics_db.conn, category, objective_count)
                opened = self._open_quiz_questions(category, open_count) if open_count else []
                if len(bank) + len(opened) >= int(count):
                    result = {"questions": bank + opened, "source": "bank+rubric" if opened else "bank",
                              "blueprint": blueprint, "bank_total": len(bank)}
                    self.teaching_cache[cache_key] = result
                    return result
            except Exception:
                pass
        items = self.classics_db.search(category=category, limit=200)
        if not items:
            return {"questions": []}
        questions = []
        random.shuffle(items)
        if "选择" in types:
            all_authors = list({a["author"] for a in self.classics_db.get_authors() if a["author"] != "佚名"})
            for item in items:
                if len(questions) >= count:
                    break
                correct_author = item["author"]
                if correct_author == "佚名":
                    continue
                wrong_authors = [a for a in all_authors if a != correct_author]
                if len(wrong_authors) < 3:
                    continue
                wrong = random.sample(wrong_authors, 3)
                options = wrong + [correct_author]
                random.shuffle(options)
                answer_idx = options.index(correct_author)
                questions.append({"type": "选择", "question": f"《{item['title']}》的作者是谁？", "options": options, "answer": answer_idx, "explanation": f"《{item['title']}》的作者是{correct_author}。"})
        if "选择" in types and len(questions) < count:
            dynasties = list({item["dynasty"] for item in items if item["dynasty"] and item["dynasty"] != "未知"})
            for item in items:
                if len(questions) >= count:
                    break
                correct_dynasty = item["dynasty"]
                if not correct_dynasty or correct_dynasty == "未知":
                    continue
                wrong = random.sample([d for d in dynasties if d != correct_dynasty], 3) if len(dynasties) >= 4 else []
                if len(wrong) < 3:
                    continue
                options = wrong + [correct_dynasty]
                random.shuffle(options)
                answer_idx = options.index(correct_dynasty)
                questions.append({"type": "选择", "question": f"《{item['title']}》属于哪个朝代？", "options": options, "answer": answer_idx, "explanation": f"《{item['title']}》属于{correct_dynasty}。"})
        if "默写" in types and len(questions) < count:
            poems_with_comma = []
            for item in items:
                for line in item["content"].split("\n"):
                    if "，" in line and line.count("，") == 1 and len(line) >= 8:
                        poems_with_comma.append((line, item["title"]))
            if poems_with_comma:
                selected = random.sample(poems_with_comma, min(count - len(questions), len(poems_with_comma)))
                for line, title in selected:
                    parts = line.split("，")
                    question = f"{parts[0].strip()}，____"
                    answer = parts[1].strip()
                    questions.append({"type": "默写", "question": question, "answer": answer, "explanation": f"《{title}》中的句子。"})
        if "出处" in types and len(questions) < count:
            all_items = self.classics_db.search(limit=500)
            candidates = []
            for item in all_items:
                if item.get('content') and len(item['content']) > 10:
                    lines = [l.strip() for l in item['content'].split('\n') if l.strip()]
                    if len(lines) >= 2:
                        candidates.append((item, lines))
            if len(candidates) >= count:
                all_titles = [x['title'] for x in all_items if x.get('title')]
                selected = random.sample(candidates, min(count - len(questions), len(candidates)))
                for item, lines in selected:
                    correct_title = item['title']
                    wrong_titles = [t for t in all_titles if t != correct_title]
                    if len(wrong_titles) < 3:
                        continue
                    wrong = random.sample(wrong_titles, 3)
                    options = wrong + [correct_title]
                    random.shuffle(options)
                    answer_idx = options.index(correct_title)
                    random_line = random.choice(lines)
                    questions.append({"type": "选择", "question": f"诗句“{random_line}”出自哪首作品？", "options": options, "answer": answer_idx, "explanation": f"诗句出自《{correct_title}》。"})
        if len(questions) >= count:
            result = {"questions": questions[:count]}
            self.teaching_cache[cache_key] = result
            return result
        prompt = f"""请使用简体中文生成以下题目。
从{category}中生成{count}道题目，难度{difficulty}级，题型包括{types}。
返回JSON：{{"questions":[{{"type":"题型","question":"题目","options":["A","B","C","D"],"answer":0,"explanation":"解析"}}]}}
注意：填空题 options 为空，answer 为正确答案字符串；判断题 options 为["正确","错误"]。"""
        try:
            result = json.loads(self.ai.generate(self.engine.current_task or "generate", prompt))
        except Exception:
            result = {"questions": []}
        if isinstance(result, dict) and "questions" in result:
            for q in result["questions"]:
                q["question"] = self._convert_to_simplified(q.get("question", ""))
                q["explanation"] = self._convert_to_simplified(q.get("explanation", ""))
                if q.get("options"):
                    q["options"] = [self._convert_to_simplified(o) for o in q["options"]]
        self.teaching_cache[cache_key] = result
        return result

    def check_quiz_answer(self, questions_json: str, answers_json: str) -> Dict:
        questions = json.loads(questions_json)
        answers = json.loads(answers_json)
        correct = 0
        wrong = []
        pending = []
        auto_total = 0
        for i, q in enumerate(questions.get("questions", [])):
            if q.get("auto_gradable") is False or q.get("type") in ("简答", "鉴赏"):
                pending.append({"index": i, "question": q.get("question", ""), "rubric": q.get("rubric", []),
                                "answer_hint": q.get("answer", "")})
                continue
            auto_total += 1
            if q["type"] in ["填空", "默写"]:
                if i < len(answers) and str(answers[i]) == str(q["answer"]):
                    correct += 1
                else:
                    wrong.append({"index": i, "correct": q["answer"], "explanation": q.get("explanation", "")})
            else:
                if i < len(answers) and answers[i] == q["answer"]:
                    correct += 1
                else:
                    wrong.append({"index": i, "correct": q["answer"], "explanation": q.get("explanation", "")})
        return {"total": len(questions.get("questions", [])), "auto_total": auto_total,
                "correct": correct, "wrong": wrong, "pending": pending,
                "score": round(correct / max(auto_total, 1) * 100)}

    def get_daily_task(self) -> Dict:
        item = self.classics_db.get_random()
        if not item:
            return {"type": "暂无推荐"}
        return {
            "type": "每日学习",
            "id": item.get("id", ""),
            "title": item.get("title", ""),
            "author": item.get("author", ""),
            "dynasty": item.get("dynasty", ""),
            "category": item.get("category", ""),
            "content": item.get("content", ""),
            "translation": item.get("translation", ""),
            "annotation": item.get("annotation", ""),
        }

    def save_learning_progress(self, data_json: str) -> str:
        path = app_path("data", "learning_progress.json")
        ensure_dir(path)
        return "进度已保存" if atomic_write_text(path, data_json) else "保存失败"

    def load_learning_progress(self) -> str:
        p = app_path("data", "learning_progress.json")
        return open(p, "r", encoding="utf-8").read() if os.path.exists(p) else "{}"

    def add_wrong_question(self, question_data: Dict) -> str:
        self.classics_db.conn.execute(
            "INSERT INTO quiz_wrong (question, your_answer, correct_answer, explanation) VALUES (?,?,?,?)",
            (question_data.get("question", ""), question_data.get("yourAnswer", ""),
             question_data.get("correctAnswer", ""), question_data.get("explanation", ""))
        )
        self.classics_db.conn.commit()
        return "已添加"

    def get_wrong_questions(self, limit: int = 100) -> List[Dict]:
        rows = self.classics_db.conn.execute(
            "SELECT * FROM quiz_wrong ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]

    def create_study_plan(self, name: str, description: str, classic_ids: List[str]) -> str:
        self.classics_db.create_study_plan(name, description, classic_ids)
        return "计划已创建"

    def get_study_plans(self) -> List[Dict]:
        return self.classics_db.get_study_plans()


# ---------------------- 设置与配置 Mixin ----------------------
class SettingsMixin:
    def set_engine(self, mode: str) -> str:
        if mode == "online":
            self.engine = LazyEngine()
            self.engine.on_usage = self._log_usage
            self.engine.current_task = ""
            return "引擎: online"
        try:
            self.engine = LocalEngine(app_path("models", "poem.gguf"))
            self.engine.on_usage = self._log_usage
            self.engine.current_task = ""
            return "引擎: offline"
        except Exception as e:
            log("warning", f"本地模型加载失败，回退到云端: {str(e)[:100]}")
            self.engine = LazyEngine()
            self.engine.on_usage = self._log_usage
            return "本地模型不可用，已切换为云端引擎"

    def switch_model(self, provider: str) -> str:
        if provider not in CloudEngine.PROVIDERS:
            return f"不支持的模型: {provider}"
        self.engine = LazyEngine(provider=provider)
        self.engine.on_usage = self._log_usage
        self.engine.current_task = ""
        settings = safe_json_load(app_path("data", "settings.json"), {})
        settings.setdefault("api", {})
        settings["api"]["provider"] = provider
        settings["api"]["model"] = self.engine.model
        safe_json_save(app_path("data", "settings.json"), settings)
        return f"已切换到 {CloudEngine.PROVIDERS[provider]['name']}（{self.engine.model}）"

    def get_settings(self) -> Dict:
        settings = safe_json_load(app_path("data", "settings.json"), {})
        api_cfg = settings.get("api", {}) or {}
        usage = settings.get("usage", {"monthly_calls": 0, "monthly_tokens": 0, "last_reset": ""})
        return {
            "provider": api_cfg.get("provider", "deepseek"),
            "has_key": bool(api_cfg.get("api_key", "")),
            "model": api_cfg.get("model", "deepseek-chat"),
            "temperature": api_cfg.get("temperature", 0.9),
            "max_tokens": api_cfg.get("max_tokens", 512),
            "timeout": api_cfg.get("timeout", 30),
            "retry": api_cfg.get("retry", 2),
            "is_default": api_cfg.get("is_default", False),
            "usage": usage,
            "version": VERSION,
            "providers": [
                {
                    "id": key,
                    "name": cfg["name"],
                    "desc": {
                        "deepseek": "国产大模型，性价比高",
                        "qwen": "阿里云大模型",
                        "zhipu": "清华系大模型",
                        "moonshot": "月之暗面",
                        "openai": "OpenAI 官方接口",
                    }.get(key, ""),
                    "models": cfg["models"],
                }
                for key, cfg in CloudEngine.PROVIDERS.items()
            ],
        }

    def save_api_settings(self, p: str, k: str, m: str, t: float, mt: int, timeout: Optional[int] = None, retry: Optional[int] = None, is_default: Optional[bool] = None) -> str:
        ensure_dir(app_path("data", "settings.json"))
        settings = safe_json_load(app_path("data", "settings.json"), {})
        previous = settings.get("api", {}) or {}
        key_text = str(k or "").strip()
        new_key = key_text if key_text and key_text != "KEPT" else None

        settings["api"] = {
            "provider": p,
            "api_key": encrypt(new_key) if new_key else previous.get("api_key", ""),
            "model": m,
            "temperature": float(t),
            "max_tokens": int(mt),
            "timeout": int(timeout) if timeout else previous.get("timeout", 30),
            "retry": int(retry) if retry is not None else previous.get("retry", 2),
            "is_default": bool(is_default) if is_default is not None else previous.get("is_default", False),
        }
        if not safe_json_save(app_path("data", "settings.json"), settings):
            return "设置保存失败，请检查文件权限"
        secure_file_permissions(app_path("data", "settings.json"))

        # 传入 None 时让引擎重新读取已保存的密文，绝不能把 "KEPT" 当 Key
        self.engine = LazyEngine(provider=p, api_key=new_key, model=m)
        self.engine.on_usage = self._log_usage
        self.engine.current_task = ""
        return "设置已保存到本地"

    def test_api_key(self, key: str, provider: str) -> Dict:
        ok, msg = self.engine.test_connection(key, provider)
        return {"success": ok, "message": msg}

    def check_api_status(self) -> Dict:
        """检查当前 API 配置是否可用。"""
        settings = safe_json_load(app_path("data", "settings.json"), {})
        api_cfg = settings.get("api", {}) or {}
        provider = api_cfg.get("provider", "deepseek")
        encoded_key = api_cfg.get("api_key", "")
        key = decrypt(encoded_key) if encoded_key else os.getenv("DEEPSEEK_API_KEY", "")
        if not key:
            return {"success": False, "message": "未配置API Key"}
        ok, msg = self.engine.test_connection(key, provider)
        return {"success": ok, "message": msg}

    def get_translations(self, lang: str = "zh-CN") -> Dict:
        from i18n_manager import I18nManager
        i18n = I18nManager()
        i18n.set_language(lang)
        return i18n.strings

    def check_update(self) -> Dict:
        return self.updater.check_update()

    def download_update(self, url: str = "", sha256: str = "") -> Dict:
        return self.updater.download_update(url, sha256)

    def install_update(self, path: str) -> Dict:
        return self.updater.install_update(path)

    def rollback_update(self, url: str = "", sha256: str = "") -> Dict:
        return self.updater.rollback_update(url, sha256)

    def get_update_url(self) -> str:
        return self.updater.update_url

    def save_update_url(self, url: str) -> str:
        settings = safe_json_load(app_path("data", "settings.json"), {})
        settings.setdefault("update", {})
        settings["update"]["url"] = str(url or "").strip()
        if not safe_json_save(app_path("data", "settings.json"), settings):
            return "更新源保存失败"
        self.updater = Updater()
        return "更新源已保存" if self.updater.update_url else "更新源已清空"

    def get_ui_state(self) -> Dict:
        """读取界面偏好：主题、上次标签、错题本、学习记录、答题历史。

        pywebview 的 ``html=`` 页面是 opaque origin，localStorage 会被拒绝；
        因此 UI 状态必须落到本地文件。
        """
        data = safe_json_load(app_path("data", "ui_state.json"), {})
        return data if isinstance(data, dict) else {}

    def save_ui_state(self, patch_json: str) -> bool:
        if not isinstance(patch_json, str) or len(patch_json) > 1024 * 1024:
            return False
        try:
            patch = json.loads(patch_json)
        except (TypeError, ValueError):
            return False
        if not isinstance(patch, dict):
            return False
        allowed = {"theme", "last_nav", "wrong_book", "learned", "quiz_history"}
        with _UI_STATE_LOCK:
            data = self.get_ui_state()
            for key in allowed:
                if key in patch:
                    data[key] = patch[key]
            return bool(safe_json_save(app_path("data", "ui_state.json"), data))

    def clear_cache(self) -> str:
        self.cache_mgr.clear()
        self.teaching_cache = {}
        return "本地缓存已清理"

    def get_ai_budget(self) -> Dict:
        return self.ai.budget_status()

    def get_version_info(self) -> Dict:
        return VersionManager.get_full_info()

    def get_changelog(self) -> str:
        return self.updater.get_changelog()


# ---------------------- 备份与导出 Mixin ----------------------
class BackupExportMixin:
    def create_backup(self) -> str:
        # 先把 WAL 合并回主库，保证 zip 拿到一致快照
        try:
            self.db.checkpoint()
            self.classics_db.checkpoint()
        except Exception:
            log("warning", "备份前 checkpoint 失败，继续执行")
        path = self.backup_mgr.create()
        return path or "备份失败，请检查磁盘空间或文件权限"

    def list_backups(self) -> Dict:
        info = self.backup_mgr.get_backup_info()
        result = []
        for name in info.get("backups", []):
            full_path = os.path.join(self.backup_mgr.backup_dir, name)
            try:
                size = os.path.getsize(full_path)
                mtime = os.path.getmtime(full_path)
            except OSError:
                continue
            result.append(
                {
                    "filename": name,
                    "size": size,
                    "time": datetime.fromtimestamp(mtime).isoformat(),
                }
            )
        return {
            "backup_dir": info["backup_dir"],
            "keep_last": info["keep_last"],
            "backups": result,
        }

    def _remove_db_sidecars(self):
        """删除 SQLite 的 -wal/-shm 侧车文件，返回删除失败的文件名。"""
        failed = []
        for name in ("works.db", "classics.db"):
            for suffix in ("-wal", "-shm"):
                path = app_path("data", name + suffix)
                for attempt in range(6):
                    try:
                        os.remove(path)
                        break
                    except FileNotFoundError:
                        break
                    except OSError:
                        time.sleep(0.1 * (attempt + 1))
                else:
                    failed.append(os.path.basename(path))
        return failed

    def restore_backup(self, filename: str) -> Dict:
        full_path = self.backup_mgr.resolve_backup(filename)
        if not full_path:
            return {"success": False, "message": "备份文件不存在"}
        safety_backup = self.create_backup()

        # Windows 下数据库文件被占用时无法覆盖，先关闭连接
        self._close_data_layer()
        sidecar_failed = []
        try:
            sidecar_failed = self._remove_db_sidecars()
            ok, message = self.backup_mgr.restore(full_path)
        finally:
            sidecar_failed += self._remove_db_sidecars()
            self._reopen_data_layer()
        self.cache_mgr.clear()

        if sidecar_failed:
            return {
                "success": False,
                "message": f"数据已恢复，但 WAL 文件被占用（{', '.join(sidecar_failed)}），"
                           "请关闭其他实例后重试，否则可能读到旧数据",
                "safety_backup": safety_backup,
            }
        return {"success": ok, "message": message, "safety_backup": safety_backup}

    def delete_backup(self, filename: str) -> Dict:
        ok, msg = self.backup_mgr.delete(filename)
        return {"success": ok, "message": msg}

    def get_backup_config(self) -> Dict:
        return self.backup_mgr.get_config()

    def get_backup_overview(self) -> Dict:
        config = self.get_backup_config()
        info = self.list_backups()
        config["backups"] = info.get("backups", [])
        config["count"] = len(config["backups"])
        config["latest"] = config["backups"][0] if config["backups"] else None
        return config

    def save_backup_config(self, keep_last: Optional[int] = None, interval_hours: Optional[float] = None) -> Dict:
        ok, msg = self.backup_mgr.set_config(keep_last, interval_hours)
        return {"success": ok, "message": msg}

    def export_txt(self, text: str) -> str:
        path = _export_path(f"xinyu_{get_timestamp_str()}.txt")
        atomic_write_text(path, str(text or ""))
        return path

    def export_image_api(self, t: str, fs: int, bg: tuple, a: str) -> str:
        from exporter import export_image

        path = _export_path(f"xinyu_{get_timestamp_str()}.png")
        return export_image(t, output=path, font_size=int(fs or 24), bg_color=tuple(bg or (255, 250, 240)), author=a)

    def export_letter(self, t: str, a: str, s: str) -> str:
        from exporter import export_letter_style

        path = _export_path(f"xinyu_letter_{get_timestamp_str()}.png")
        return export_letter_style(t, output=path, author=a, seal_text=s)

    def export_fan(self, t: str, a: str) -> str:
        from exporter import export_fan_style

        path = _export_path(f"xinyu_fan_{get_timestamp_str()}.png")
        return export_fan_style(t, output=path, author=a)

    def export_couplet_img(self, u: str, l: str, h: str) -> str:
        from exporter import export_couplet_style

        path = _export_path(f"xinyu_couplet_{get_timestamp_str()}.png")
        return export_couplet_style(u, l, h, output=path)

    def export_spring(self, u: str, l: str, h: str) -> str:
        from exporter import export_spring_couplet

        path = _export_path(f"xinyu_spring_{get_timestamp_str()}.png")
        return export_spring_couplet(u, l, h, output=path)

    def export_card(self, p: str, t: str, a: str) -> str:
        from exporter import export_social_card

        path = _export_path(f"xinyu_card_{get_timestamp_str()}.png")
        return export_social_card(p, title=t, author=a, output=path)


# ---------------------- 工具与杂项 Mixin ----------------------
class UtilityMixin:
    def analyze_any_text(self, text: str) -> Dict:
        self.engine.current_task = "analyze"
        prompt = f"请赏析以下诗句/作品：{text}，返回JSON格式六维赏析（背景、解读、意境、格律、文化、教学）。"
        try:
            result = self.ai.generate(self.engine.current_task or "generate", prompt)
            if result and ("错误" in result or "失败" in result or "网络" in result or "超时" in result):
                raise Exception("AI调用异常")
            try:
                data = json.loads(result)
                if not all(k in data for k in ["background","text_analysis","artistic","rhythm","culture","teaching"]):
                    raise ValueError("缺少字段")
                return data
            except Exception:
                retry_prompt = f"请只输出JSON，不要包含任何其他文字。格式：{{\"background\":\"...\",\"text_analysis\":\"...\",\"artistic\":\"...\",\"rhythm\":\"...\",\"culture\":\"...\",\"teaching\":\"...\"}}。待赏析文本：{text[:100]}"
                result = self.ai.generate(self.engine.current_task or "generate", retry_prompt)
                data = json.loads(result)
                if not all(k in data for k in ["background","text_analysis","artistic","rhythm","culture","teaching"]):
                    raise ValueError("仍缺少字段")
                return data
        except Exception as e:
            return {"error": f"AI赏析失败：{str(e)[:100]}，请检查API设置或网络。"}

    def get_usage_stats(self) -> Dict:
        self._flush_usage_log()
        log_path = app_path("data", "usage_log.json")
        if not os.path.exists(log_path):
            return {"daily": [], "total_calls": 0, "total_tokens": 0, "total_cost": 0}
        with open(log_path, "r", encoding="utf-8") as f:
            logs = json.load(f)
        if not isinstance(logs, list):
            logs = []
        daily = {}
        task_counts = {}
        total_calls = len(logs)
        total_tokens = 0
        total_cost = 0
        for item in logs:
            if not isinstance(item, dict):
                continue
            timestamp = str(item.get("timestamp") or "")
            date = timestamp[:10] or "未知"
            tokens = int(item.get("total_tokens") or 0)
            cost = float(item.get("cost") or 0)
            daily.setdefault(date, {"calls": 0, "tokens": 0, "cost": 0})
            daily[date]["calls"] += 1
            daily[date]["tokens"] += tokens
            daily[date]["cost"] += cost
            task = item.get("task", "其他")
            task_counts[task] = task_counts.get(task, 0) + 1
            total_tokens += tokens
            total_cost += cost
        daily_list = [{"date": k, "calls": v["calls"], "tokens": v["tokens"], "cost": round(v["cost"], 4)} for k, v in daily.items()]
        daily_list.sort(key=lambda x: x["date"], reverse=True)
        return {
            "daily": daily_list[:30],
            "task_counts": task_counts,
            "total_calls": total_calls,
            "total_tokens": total_tokens,
            "total_cost": round(total_cost, 4)
        }

    def get_usage_dashboard(self) -> Dict:
        """用量仪表盘：月度 + 明细 + 各任务占比。"""
        cached = self.cache_mgr.get("usage:dashboard")
        if cached:
            return cached
        stats = self.get_usage_stats()
        settings = self.get_settings()
        usage = settings.get("usage", {}) or {}
        result = {
            "monthly_calls": int(usage.get("monthly_calls") or 0),
            "monthly_tokens": int(usage.get("monthly_tokens") or 0),
            "total_calls": int(stats.get("total_calls") or 0),
            "total_tokens": int(stats.get("total_tokens") or 0),
            "total_cost": float(stats.get("total_cost") or 0),
            "daily": stats.get("daily", []),
            "task_counts": stats.get("task_counts", {}),
            "provider": settings.get("provider", ""),
            "model": settings.get("model", ""),
            "has_key": settings.get("has_key", False),
        }
        self.cache_mgr.set("usage:dashboard", result, ttl=30)
        return result

    def export_diagnostics(self) -> str:
        """导出不含 Key 与作品正文的诊断包。"""
        from crash_reporter import build_diagnostics

        return build_diagnostics()

    def get_legal_document(self, name: str) -> str:
        from legal import get_document

        return get_document(name)

    def export_user_data(self) -> str:
        """把用户自己的作品、笔记、收藏、历史与设置导出为 zip。"""
        import zipfile

        directory = app_path("exports")
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, f"xinyu_userdata_{get_timestamp_str()}.zip")
        conn = self.classics_db.conn
        tables = {
            "notes.json": "SELECT * FROM user_notes",
            "favorites.json": "SELECT * FROM favorites",
            "reading_history.json": "SELECT * FROM reading_history",
            "study_plans.json": "SELECT * FROM study_plans",
            "quiz_wrong.json": "SELECT * FROM quiz_wrong",
        }
        settings = safe_json_load(app_path("data", "settings.json"), {})
        if isinstance(settings, dict):
            settings.setdefault("api", {})["api_key"] = "***"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "works.json",
                json.dumps(self.db.search_dicts("", limit=100000), ensure_ascii=False, indent=2),
            )
            for filename, sql in tables.items():
                rows = [dict(row) for row in conn.execute(sql).fetchall()]
                archive.writestr(filename, json.dumps(rows, ensure_ascii=False, indent=2))
            archive.writestr(
                "settings.redacted.json", json.dumps(settings, ensure_ascii=False, indent=2)
            )
            for name in (
                "chat_history.json",
                "preferences.json",
                "learning_progress.json",
                "user_styles.json",
                "annotations.json",
            ):
                source = app_path("data", name)
                if os.path.exists(source):
                    try:
                        archive.writestr(name, open(source, encoding="utf-8").read())
                    except OSError:
                        continue
            archive.writestr(
                "README.txt",
                "这是心语导出的个人数据。API Key 已用 *** 脱敏；"
                "经典库原文不在此包内，可在软件内继续使用。\n",
            )
        return path

    def reset_user_data(self, confirm: str = "") -> Dict:
        """清空用户数据（保留经典库、设置与 Key），执行前自动备份。"""
        if str(confirm or "").strip().upper() != "DELETE":
            return {"success": False, "message": "请输入 DELETE 确认后再执行"}
        backup = self.create_backup()
        counts = {}
        with self.classics_db.conn:
            for table in ("user_notes", "favorites", "reading_history", "study_plans", "quiz_wrong"):
                cursor = self.classics_db.conn.execute(f"DELETE FROM {table}")
                counts[table] = cursor.rowcount
        with self.db.conn:
            counts["works"] = self.db.conn.execute("DELETE FROM works").rowcount
            counts["journals"] = self.db.conn.execute("DELETE FROM journals").rowcount
        for name in (
            "chat_history.json",
            "preferences.json",
            "learning_progress.json",
            "user_styles.json",
            "annotations.json",
        ):
            path = app_path("data", name)
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass
        self.preferences = PreferenceLearner(app_path("data", "preferences.json"))
        self.teaching_cache = {}
        self.cache_mgr.clear()
        return {"success": True, "message": "个人数据已清空", "backup": backup, "counts": counts}

    def log_user_action(self, action: str, details: str = "") -> str:
        log("info", f"[操作] {action} {details}")
        return "已记录"

    def translate_poem(self, poem: str, lang: str) -> str:
        self.engine.current_task = "translate"
        if self._poetry_translator is None:
            from poetry_translator import PoetryTranslator
            self._poetry_translator = PoetryTranslator(self.engine)
        return self._poetry_translator.translate(poem, lang)

    def get_profile(self) -> Dict:
        if self._poet_profiler is None:
            from poet_profiler import PoetProfiler
            self._poet_profiler = PoetProfiler(self.db)
        return self._poet_profiler.generate()

    def get_random_topic(self) -> str:
        return random.choice(["雨后空山", "江南春晓", "边塞风雪", "秋夜寄北", "月下独酌", "桃花源", "登高怀古", "竹林听雨", "大漠孤烟", "海上明月"])

    def chat(self, message: str, history_json: str = "[]", role: str = "") -> str:
        self.engine.current_task = "chat"
        try:
            history = json.loads(history_json) if history_json else []
            normalized = []
            for item in history[-20:]:
                role_val = item.get("role", "").lower()
                if role_val == "ai":
                    role_val = "assistant"
                elif role_val == "human":
                    role_val = "user"
                elif role_val not in ("system", "user", "assistant"):
                    role_val = "user"
                normalized.append({"role": role_val, "content": item.get("content", "")})
            if role:
                system_prompt = f"你是{role}，请以{role}的风格回答。"
            else:
                system_prompt = "你是心语AI诗词助手，精通中国古典文学。"
            messages = [{"role": "system", "content": system_prompt}] + normalized + [{"role": "user", "content": message}]
            return self.engine.chat(messages)
        except Exception as e:
            return f"错误: {str(e)[:100]}"

    def chat_with_model(self, message: str, history_json: str = "[]", model: str = "deepseek-chat") -> str:
        self.engine.current_task = "chat"
        try:
            history = json.loads(history_json) if history_json else []
            normalized = []
            for item in history[-20:]:
                role_val = item.get("role", "").lower()
                if role_val == "ai":
                    role_val = "assistant"
                elif role_val == "human":
                    role_val = "user"
                elif role_val not in ("system", "user", "assistant"):
                    role_val = "user"
                normalized.append({"role": role_val, "content": item.get("content", "")})
            messages = [{"role": "system", "content": "你是DeepSeek专业助手。"}] + normalized + [{"role": "user", "content": message}]
            old_model = self.engine.model
            self.engine.model = model
            try:
                result = self.engine.chat(messages)
            finally:
                self.engine.model = old_model
            return result
        except Exception as e:
            return f"错误: {str(e)[:100]}"

    def save_chat_history(self, h: str) -> None:
        path = app_path("data", "chat_history.json")
        ensure_dir(path)
        atomic_write_text(path, h)

    def load_chat_history(self) -> str:
        p = app_path("data", "chat_history.json")
        return open(p, "r", encoding="utf-8").read() if os.path.exists(p) else "[]"

    def list_plugins(self) -> List[Dict]:
        return self.plugin_mgr.get_plugin_list()

    def analyze_rhetoric(self, poem: str) -> Dict:
        from rhetorica import Rhetorica
        rhet = Rhetorica()
        return rhet.analyze(poem)

    def get_tts_options(self) -> Dict:
        return {"voices": TTSManager.get_voices(), "styles": TTSManager.get_styles(), "bgm": TTSManager.get_bgm()}

    def speak_text(self, text: str, voice: str = "female", style: str = "normal", speed: float = 1.0) -> Dict:
        vc = TTSManager.VOICES.get(voice, TTSManager.VOICES["female"])
        sc = TTSManager.STYLES.get(style, TTSManager.STYLES["normal"])
        return {"text": text, "rate": round(vc["rate"] * sc.get("rate", 0.8) * speed, 2), "pitch": round(vc.get("pitch", 1.0) * sc.get("pitch", 1.0), 2)}

    def evaluate_pronunciation(self, original: str, user_text: str) -> Dict:
        if not user_text:
            return {"score": 0, "message": "未检测到朗读"}
        import difflib

        clean = lambda value: re.sub(r"[\s\W_]+", "", str(value or ""))
        expected = clean(original)
        actual = clean(user_text)
        if not expected:
            return {"score": 0}
        score = difflib.SequenceMatcher(None, expected, actual).ratio() * 100
        grade = "S" if score >= 95 else "A" if score >= 85 else "B" if score >= 70 else "C"
        return {"score": round(score, 1), "grade": grade}

    def run_tests(self) -> Dict:
        from test_runner import TestRunner
        r = TestRunner()
        s = r.run()
        return {"success": s, "passed": r.passed, "failed": r.failed}

    def get_help_info(self) -> Dict:
        return {
            "commands": ["/deep 作品名 - 六维赏析", "/write 体裁 风格 主题 - 创作", "/expand 分类 数量 - 扩充", "/stats - 统计", "/health - 健康", "/teach 作品名 - 教学", "/quiz 分类 难度 数量 - 出题"],
            "tips": ["经典菜单可浏览经史子集蒙、唐诗宋词等", "数据验证可一键清理重复和残缺条目", "教学工坊支持背景、逐句、赏析、练习", "Token面板可切换免费/Token模式"]
        }


# ---------------------- API 主类（整合所有 Mixin） ----------------------
class API(ClassicsMixin, CreationMixin, TeachingMixin, SettingsMixin, BackupExportMixin, UtilityMixin):
    def __init__(self):
        perf_mark("api.start")
        VersionManager.ensure_changelog()
        self.engine = LazyEngine()
        self.ai = AIGateway(self)
        perf_mark("api.engine")
        self.style_mgr = StyleManager()
        self._init_data_layer()
        perf_mark("api.data")
        self.preferences = PreferenceLearner(app_path("data", "preferences.json"))
        self.plugin_mgr = PluginManager(app_path("plugins"))
        self.backup_mgr = BackupManager(app_path("backups"))
        self.cache_mgr = CacheManager()
        perf_mark("api.cache")
        self.updater = Updater()
        self.teaching_cache = {}
        self._poet_profiler = None
        self._poetry_translator = None
        self.cache_mgr.file.clear_expired()

        self.jobs = JobManager(
            app_path("data", "jobs.db"),
            {
                "teaching": self._job_teaching,
                "expand": self._job_expand,
                "import": self._job_import,
            },
            max_workers=2,
        )
        perf_mark("api.jobs")

        # 用量日志缓冲（锁只保护内存，写盘在锁外）
        self._usage_log_buffer = []
        self._usage_log_lock = threading.Lock()
        self._usage_log_flush_thread = None
        self._usage_log_stop = threading.Event()
        self._start_usage_log_flusher()

        try:
            self.classics_db.conn.execute("SELECT 1")
            log("info", "数据库连接正常")
        except Exception as e:
            log("error", f"数据库连接异常: {str(e)[:100]}")

        log("info", f"心语 V{VERSION} 启动完成")
        total = self.classics_db.get_total_count()
        seed_marker = app_path("data", "classics_seed_version")
        seed_version = "2"
        marker_is_current = False
        try:
            if os.path.exists(seed_marker):
                with open(seed_marker, "r", encoding="utf-8") as handle:
                    marker_is_current = handle.read().strip() == seed_version
        except OSError:
            marker_is_current = False
        if total < 3500 and not marker_is_current:
            try:
                seeded = self.classics_importer.import_bundled_seed()
                atomic_write_text(seed_marker, seed_version)
                if seeded:
                    log("info", f"已合并内置经典种子 {seeded} 篇")
            except Exception as exc:  # noqa: BLE001
                log("warning", f"内置经典种子导入失败: {str(exc)[:120]}")
            total = self.classics_db.get_total_count()
        if total == 0:
            count = self.classics_importer.import_sample_data()
            log("info", f"已自动导入 {count} 篇经典范文")
        self.engine.on_usage = self._log_usage
        self.engine.current_task = ""

    # ---------- 数据层生命周期 ----------
    @property
    def online_importer(self):
        """在线数据源按需导入 requests，避免拖慢首屏。"""
        if getattr(self, "_online_importer", None) is None:
            from online_importer import OnlineImporter

            self._online_importer = OnlineImporter(db=self.classics_db)
        return self._online_importer

    def _init_data_layer(self):
        self.db = Database(app_path("data", "works.db"))
        self.classics_db = ClassicsDatabase(app_path("data", "classics.db"))
        self.classics_importer = ClassicsImporter(db=self.classics_db)
        self._online_importer = None
        try:
            self.classics_db.optimize()
        except Exception:
            pass

    def _close_data_layer(self):
        for name in ("classics_importer",):
            obj = getattr(self, name, None)
            if obj is not None and hasattr(obj, "close"):
                try:
                    obj.close()
                except Exception:
                    pass
        obj = getattr(self, "_online_importer", None)
        if obj is not None and hasattr(obj, "close"):
            try:
                obj.close()
            except Exception:
                pass
        for name in ("db", "classics_db"):
            obj = getattr(self, name, None)
            if obj is not None and hasattr(obj, "close"):
                try:
                    obj.close()
                except Exception:
                    pass

    def _reopen_data_layer(self):
        self._init_data_layer()
        self.teaching_cache = {}

    # ---------- 作业系统 ----------
    def _job_teaching(self, payload, progress, cancelled):
        # 直接调用 Mixin 实现，绕过 js_api 错误包装，让取消异常能传到作业层
        return TeachingMixin.teaching_workflow(
            self,
            str(payload.get("classic_id", "")),
            str(payload.get("level", "standard")),
            progress=progress,
            should_cancel=cancelled,
            checkpoint=getattr(progress, "checkpoint", None),
            resume=getattr(progress, "get_checkpoint", lambda: {})(),
            force=bool(payload.get("force", False)),
            profile=str(payload.get("profile", "")),
        )

    def _job_expand(self, payload, progress, cancelled):
        return ClassicsMixin.smart_expand_advanced(
            self,
            str(payload.get("era", "")),
            str(payload.get("genre", "")),
            str(payload.get("school", "")),
            str(payload.get("category", "唐诗")),
            int(payload.get("count", 10) or 10),
            progress=progress,
            should_cancel=cancelled,
            checkpoint=getattr(progress, "checkpoint", None),
            resume=getattr(progress, "get_checkpoint", lambda: {})(),
        )

    def _job_import(self, payload, progress, cancelled):
        return ClassicsMixin.confirm_import_candidates(
            self,
            json.dumps(payload.get("candidates", []), ensure_ascii=False),
            progress=progress,
            should_cancel=cancelled,
        )

    def submit_job(self, kind: str, payload_json: str = "{}") -> Dict:
        try:
            payload = json.loads(payload_json) if isinstance(payload_json, str) else payload_json
        except (TypeError, ValueError):
            return {"error": "任务参数格式错误"}
        if not isinstance(payload, dict):
            return {"error": "任务参数格式错误"}
        try:
            return {"job_id": self.jobs.submit(kind, payload)}
        except ValueError as exc:
            return {"error": str(exc)}

    def get_job(self, job_id: str) -> Dict:
        job = self.jobs.get(job_id)
        return job or {"error": "任务不存在"}

    def cancel_job(self, job_id: str) -> bool:
        return self.jobs.cancel(job_id)

    def retry_job(self, job_id: str) -> bool:
        return self.jobs.retry(job_id)

    def list_jobs(self, limit: int = 20) -> List[Dict]:
        return self.jobs.list(limit)

    def get_startup_report(self) -> Dict:
        from perf import read_latest

        return read_latest()

    def get_metrics_dashboard(self) -> Dict:
        from metrics import startup_history, summary

        return {"summary": summary(7), "startups": startup_history(10)}

    def _start_usage_log_flusher(self):
        def _flusher():
            while not self._usage_log_stop.is_set():
                self._flush_usage_log()
                self._usage_log_stop.wait(timeout=30)
        self._usage_log_flush_thread = threading.Thread(target=_flusher, daemon=True)
        self._usage_log_flush_thread.start()

    def _flush_usage_log(self):
        # 锁内只做内存快照与清空，写盘在锁外，避免与 _log_usage 互相等待
        with self._usage_log_lock:
            if not self._usage_log_buffer:
                return
            pending = list(self._usage_log_buffer)
            self._usage_log_buffer.clear()
        try:
            log_path = app_path("data", "usage_log.json")
            logs = safe_json_load(log_path, [])
            if not isinstance(logs, list):
                logs = []
            logs.extend(pending)
            safe_json_save(log_path, logs[-1000:])
        except Exception as e:
            with self._usage_log_lock:
                self._usage_log_buffer[:0] = pending
            log("error", f"记录用量失败: {str(e)[:100]}")

    def _convert_to_simplified(self, text: str) -> str:
        if not text:
            return text
        try:
            import opencc
            converter = opencc.OpenCC('t2s')
            return converter.convert(text)
        except Exception:
            return text

    def _log_usage(self, task: str, model: str, prompt_tokens: int, completion_tokens: int) -> None:
        cost = (prompt_tokens / 1000 * 0.001) + (completion_tokens / 1000 * 0.002)
        record = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "task": task,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "cost": round(cost, 6)
        }
        should_flush = False
        with self._usage_log_lock:
            self._usage_log_buffer.append(record)
            should_flush = len(self._usage_log_buffer) >= 200
        if should_flush:
            self._flush_usage_log()

    # 作品管理
    def save_work(self, g: str, s: str, t: str, c: str) -> None:
        self.db.save(g, json.dumps(s) if isinstance(s, dict) else s, t, c)
        self.cache_mgr.clear()

    def search_works(self, kw: str = "") -> List:
        return self.db.search(kw)

    def delete_work(self, wid: int) -> None:
        self.db.delete(int(wid))
        self.cache_mgr.clear()

    def get_journals(self, limit: int = 30) -> List:
        return self.db.get_journals(limit)

    def save_note(self, classic_id: str, note_text: str) -> str:
        self.classics_db.add_note(classic_id, note_text)
        self.cache_mgr.clear()
        return "笔记已保存"

    def get_notes(self, classic_id: str) -> List[Dict]:
        return self.classics_db.get_notes(classic_id)

    def delete_note(self, note_id: int) -> str:
        try:
            self.classics_db.delete_note(int(note_id))
            self.cache_mgr.clear()
            return "已删除"
        except Exception as e:
            return f"删除失败: {e}"

    def close(self):
        if getattr(self, "_closed", False):
            return
        self._closed = True
        self._usage_log_stop.set()
        thread = self._usage_log_flush_thread
        if thread and thread.is_alive():
            thread.join(timeout=3)
        self._flush_usage_log()

        try:
            self.backup_mgr.stop_auto_backup()
        except Exception:
            pass
        try:
            self.jobs.shutdown()
        except Exception:
            pass
        try:
            self.cache_mgr.close()
        except Exception:
            pass
        self._close_data_layer()


# 所有公开方法统一套上错误契约（未捕获异常 → {"__error__": {...}}）
install_api_guards(API)