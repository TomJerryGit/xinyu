# -*- coding: utf-8 -*-
import os, warnings, webview, json, random, time
os.environ["MMKV_LOG_LEVEL"] = "off"
warnings.filterwarnings("ignore")

from engine import CloudEngine, LocalEngine
from style_manager import StyleManager
from poetry_checker import check_jueju, check_cipai
from lyric_checker import get_rhyme_groups, check_structure
from database import Database
from exporter import export_image, export_letter_style, export_fan_style, export_couplet_style, export_spring_couplet, export_social_card
from classic_library import ClassicLibrary
from classics_database import ClassicsDatabase
from classics_importer import ClassicsImporter
from online_importer import OnlineImporter
from preference_learner import PreferenceLearner
from annotation_manager import AnnotationManager
from plugin_manager import PluginManager
from backup_manager import BackupManager
from cache_manager import CacheManager
from async_queue import AsyncQueue
from tts_manager import TTSManager
from updater import Updater, VersionManager
from logger import log

def safe_api(func):
    def wrapper(*args, **kwargs):
        try: return func(*args, **kwargs)
        except Exception as e:
            log("error", f"{func.__name__}: {str(e)[:200]}")
            return f"操作失败，请重试"
    return wrapper

class API:
    def __init__(self):
        self.engine = CloudEngine()
        self.style_mgr = StyleManager()
        self.db = Database("data/works.db")
        self.library = ClassicLibrary("resources/classics.json")
        self.classics_db = ClassicsDatabase("data/classics.db")
        self.classics_importer = ClassicsImporter("data/classics.db")
        self.online_importer = OnlineImporter("data/classics.db")
        self.preferences = PreferenceLearner("data/preferences.json")
        self.annotations = AnnotationManager("data/annotations.json")
        self.plugin_mgr = PluginManager("plugins")
        self.backup_mgr = BackupManager("backups")
        self.cache_mgr = CacheManager()
        self.async_queue = AsyncQueue(max_workers=3)
        self.updater = Updater()
        VersionManager.save_changelog()
        self.cache = {}
        self._poet_profiler = None
        self._poetry_translator = None
        self.cache_mgr.file.clear_expired(86400)
        log("info", "心语 V8.2 启动完成")
        if self.classics_db.get_total_count() == 0:
            count = self.classics_importer.import_sample_data()
            print(f"已自动导入 {count} 篇经典范文")

    def set_engine(self, mode):
        if mode == "online": self.engine = CloudEngine()
        else: self.engine = LocalEngine("models/poem.gguf")
        return f"引擎: {mode}"

    @safe_api
    def generate(self, genre, topic, style_info):
        k = f"gen:{genre}:{topic}:{json.dumps(style_info or {})}"
        cached = self.cache_mgr.get(k, 1800)
        if cached: return cached
        p = self.style_mgr.build_prompt(genre, topic, style_info)
        r = []
        for _ in range(3):
            try: r.append(self.engine.generate(p).strip())
            except: r.append("生成失败")
        if r: self.preferences.record(genre, style_info or {}, topic); self.cache_mgr.set(k, r)
        return r

    def get_styles(self, g): return self.style_mgr.get_styles_for_genre(g)
    def check_poem(self, poem, genre):
        lines = [l.strip() for l in poem.split('\n') if l.strip()]
        if "绝句" in genre or "律诗" in genre: return check_jueju(lines)
        if genre in ["如梦令","蝶恋花"]: return check_cipai(genre, lines)
        return "无需检测"
    def critique(self, poem, genre): return self.engine.generate(f"品评这首{genre}：{poem}")
    def smart_continue(self, line):
        ds = [{"name":"意境延伸","i":"保持意境"},{"name":"情感转折","i":"情感转折"},{"name":"哲理升华","i":"由景入理"}]
        return [{"direction":d["name"],"full_poem":self.engine.generate(f"续写：{line} 方向：{d['i']}")} for d in ds]
    def create_cento(self, kw): return self.engine.generate(f"集句创作：{kw}")
    def generate_couplet(self, upper=""): return self.engine.generate(f"对联：{upper}" if upper else "创作一副完整对联")
    def poem_response(self, org): return self.engine.generate(f"唱和：{org}")
    def allusion_deep_dive(self, a): return self.engine.generate(f"典故解析：{a}")

    def search_classics_v2(self, kw="", cat="", dyn="", au="", limit=500):
        k = f"search:{kw}:{cat}:{dyn}:{au}:{limit}"
        cached = self.cache_mgr.get(k, 600)
        if cached: return cached
        r = self.classics_db.search(kw, cat, dyn, au, None, limit)
        self.cache_mgr.set(k, r)
        return r

    def get_classic_stats(self): return self.classics_db.get_stats()
    def get_classic_categories_v2(self): return self.classics_db.get_categories()
    def get_classic_dynasties_v2(self): return self.classics_db.get_dynasties()
    def get_classic_by_id_v2(self, cid): return self.classics_db.get_by_id(cid)
    def record_classic_read(self, cid): self.classics_db.record_read(cid)
    def add_favorite(self, cid): self.classics_db.add_favorite(cid)
    def get_favorites(self): return self.classics_db.get_favorites()
    def get_random_classic(self): return self.classics_db.get_random()

    def search_online_classics(self, kw="", cat="", limit=30): return self.online_importer.search_online(kw, cat, limit)
    def download_and_import_items(self, ij): return f"导入 {self.online_importer.download_and_import(json.loads(ij))} 篇"
    def download_dataset(self, name): return self.online_importer.download_dataset(name)
    def import_cache(self, name="", limit=None): return self.online_importer.import_cache(name, limit)

    def save_work(self, g, s, t, c): self.db.save(g, json.dumps(s) if isinstance(s, dict) else s, t, c)
    def search_works(self, kw=""): return self.db.search(kw)
    def delete_work(self, wid): self.db.delete(int(wid))
    def get_journals(self, limit=30): return self.db.get_journals(limit)

    def export_txt(self, text):
        with open("output.txt","w",encoding="utf-8") as f: f.write(text)
        return os.path.abspath("output.txt")
    def export_image_api(self, t, fs, bg, a): return export_image(t, output="output.png", font_size=fs, bg_color=tuple(bg), author=a)
    def export_letter(self, t, a, s): return export_letter_style(t, output="letter.png", author=a, seal_text=s)
    def export_fan(self, t, a): return export_fan_style(t, output="fan.png", author=a)
    def export_couplet_img(self, u, l, h): return export_couplet_style(u, l, h, output="couplet.png")
    def export_spring(self, u, l, h): return export_spring_couplet(u, l, h, output="spring.png")
    def export_card(self, p, t, a): return export_social_card(p, title=t, author=a, output="social.png")
    def create_backup(self): return self.backup_mgr.create()

    def translate_poem(self, poem, lang):
        if self._poetry_translator is None:
            from poetry_translator import PoetryTranslator
            self._poetry_translator = PoetryTranslator(self.engine)
        return self._poetry_translator.translate(poem, lang)

    def get_profile(self):
        if self._poet_profiler is None:
            from poet_profiler import PoetProfiler
            self._poet_profiler = PoetProfiler(self.db)
        return self._poet_profiler.generate()

    def get_random_topic(self):
        return random.choice(["雨后空山","江南春晓","边塞风雪","秋夜寄北","月下独酌","桃花源","登高怀古","竹林听雨","大漠孤烟","海上明月"])

    def chat(self, message, history_json="[]"):
        history = json.loads(history_json) if history_json else []
        messages = [{"role":"system","content":"你是心语AI诗词助手，精通中国古典文学。"}] + history[-20:] + [{"role":"user","content":message}]
        return self.engine.chat(messages)

    def save_chat_history(self, h):
        os.makedirs("data", exist_ok=True)
        with open("data/chat_history.json","w",encoding="utf-8") as f: f.write(h)

    def load_chat_history(self):
        p = "data/chat_history.json"
        return open(p,"r",encoding="utf-8").read() if os.path.exists(p) else "[]"

    def switch_model(self, provider):
        if provider in CloudEngine.PROVIDERS:
            self.engine = CloudEngine(provider=provider)
            return f"已切换到 {CloudEngine.PROVIDERS[provider]['name']}"
        return f"不支持的模型: {provider}"

    def smart_expand_advanced(self, era, genre, school, category, count):
        prompt = f"请列出{count}首符合以下条件的作品：\n"
        if era: prompt += f"时代：{era}\n"
        if genre: prompt += f"体裁：{genre}\n"
        if school: prompt += f"流派：{school}\n"
        if category: prompt += f"分类：{category}\n"
        prompt += "每行格式：篇名|作者|朝代|体裁。只列出篇目。"
        result = self.engine.generate(prompt)
        items = []
        for line in result.strip().split('\n'):
            parts = line.strip().split('|')
            if len(parts) >= 2:
                title, author = parts[0].strip(), parts[1].strip()
                dynasty = parts[2].strip() if len(parts) > 2 else ""
                item_genre = parts[3].strip() if len(parts) > 3 else ""
                if title and author:
                    existing = self.classics_db.search(keyword=title, limit=1)
                    if existing: continue
                    content = self.engine.generate(f"请提供《{title}》{author}的全文，只输出原文。")
                    items.append({"id":f"adv_{abs(hash(title+author))%100000}","title":title,"author":author,"dynasty":dynasty,"category":item_genre,"subcategory":"","content":content,"tags":f"{item_genre},AI扩充","annotation":"AI智能扩充","is_famous":0,"difficulty_level":2})
        imported = 0
        for item in items:
            try: self.classics_db.insert(item); imported += 1
            except: pass
        self._save_expand_log({"time":str(__import__('datetime').datetime.now()),"category":category,"count":imported})
        return {"imported":imported,"total":len(items)}

    def _save_expand_log(self, log_data):
        self._save_expand_log({"time":str(__import__("datetime").datetime.now()),"category":category,"count":imported})
        logs = json.load(open("data/expand_log.json","r",encoding="utf-8")) if os.path.exists("data/expand_log.json") else []
        logs.append(log_data)
        with open("data/expand_log.json","w",encoding="utf-8") as f: json.dump(logs,f,ensure_ascii=False,indent=2)

    def get_expand_log(self):
        return json.load(open("data/expand_log.json","r",encoding="utf-8")) if os.path.exists("data/expand_log.json") else []

    def auto_complete(self):
        cats = self.classics_db.get_categories()
        cat_names = [c["category"] for c in cats]
        target = ["唐诗","宋词","元曲","经典散文","蒙学","经部","子部","史部","集部"]
        missing = [c for c in target if c not in cat_names]
        results = []
        for cat in missing[:3]:
            r = self.smart_expand_advanced("","","",cat,10)
            results.append({"category":cat,"imported":r["imported"]})
        return {"missing_categories":missing,"results":results}

    def browse_by_filters(self, era="", genre="", school="", category="", limit=200):
        results = self.classics_db.search("","","","",limit=limit)
        filtered = []
        for r in results:
            dynasty, cat, tags, sub = r.get("dynasty",""), r.get("category",""), r.get("tags",""), r.get("subcategory","")
            if era:
                era_map = {"先秦":["先秦"],"两汉":["西汉","东汉","汉"],"魏晋":["魏","晋","东晋","南北朝"],"唐":["唐"],"宋":["宋","北宋","南宋"],"元":["元"],"明":["明"],"清":["清"],"民国":["民国"]}
                if not any(e in dynasty for e in era_map.get(era,[era])): continue
            if genre:
                genre_map = {"诗":["诗","唐诗","宋诗","绝句","律诗"],"词":["词","宋词"],"曲":["曲","元曲"],"赋":["赋","辞赋"],"散文":["散文","经典散文"],"蒙学":["蒙学"],"经部":["经部"]}
                if not any(g in cat or g in sub or g in tags for g in genre_map.get(genre,[genre])): continue
            if school:
                school_map = {"儒家":["儒家"],"道家":["道家"],"法家":["法家"],"婉约":["婉约"],"豪放":["豪放"],"山水":["山水"],"边塞":["边塞"]}
                if not any(s in cat or s in sub or s in tags for s in school_map.get(school,[school])): continue
            if category and cat != category: continue
            filtered.append(r)
        return filtered[:limit]

    def deep_analysis(self, classic_id):
        item = self.classics_db.get_by_id(classic_id)
        if not item: return {"error":"未找到该作品"}
        prompt = f"""请对《{item['title']}》{item['author']}进行六维深度赏析，以JSON格式返回：
{{"background":"创作背景（50字）","text_analysis":"文本解读（100字）","artistic":"意境分析（50字）","rhythm":"格律分析（50字）","culture":"文化拓展（50字）","teaching":"教学建议（50字）"}}
原文：{item['content']}"""
        try: return json.loads(self.engine.generate(prompt))
        except: return {"error":"赏析生成失败"}

    def simple_analysis(self, classic_id, level="L2"):
        item = self.classics_db.get_by_id(classic_id)
        if not item: return "未找到该作品"
        prompts = {"L1":f"用5岁儿童能听懂的语言解读《{item['title']}》。原文：{item['content']}","L2":f"为中学生解读《{item['title']}》。原文：{item['content']}","L3":f"从学术角度分析《{item['title']}》。原文：{item['content']}"}
        return self.engine.generate(prompts.get(level, prompts["L2"]))

    def compare_analysis(self, id1, id2):
        item1, item2 = self.classics_db.get_by_id(id1), self.classics_db.get_by_id(id2)
        if not item1 or not item2: return "未找到作品"
        return self.engine.generate(f"对比分析：\nA：《{item1['title']}》{item1['author']}\n{item1['content']}\nB：《{item2['title']}》{item2['author']}\n{item2['content']}")

    def mengxue_analysis(self, classic_id):
        item = self.classics_db.get_by_id(classic_id)
        if not item: return "未找到该作品"
        prompt = f"""对蒙学经典《{item['title']}》进行儿童友好型赏析，返回JSON：
{{"word_explain":"字词解释","rhythm_tip":"韵律特点","story_version":"故事化解读","moral":"道理","activity":"小活动建议"}}
原文：{item['content']}"""
        try: return json.loads(self.engine.generate(prompt))
        except: return {"error":"赏析失败"}

    def quality_score(self, classic_id):
        item = self.classics_db.get_by_id(classic_id)
        if not item: return {"error":"未找到"}
        score = 0; d = {}
        if item.get("title"): score += 5; d["title"] = 5
        if item.get("author") and item["author"] != "佚名": score += 8; d["author"] = 8
        else: d["author"] = 0
        if item.get("dynasty"): score += 5; d["dynasty"] = 5
        else: d["dynasty"] = 0
        if len(item.get("content","")) > 50: score += 7; d["content"] = 7
        else: d["content"] = 0
        d["verified"] = 15 if item.get("verified") else 0; score += d["verified"]
        d["no_error"] = 10 if not item.get("has_error") else 0; score += d["no_error"]
        d["annotation"] = 8 if item.get("annotation") else 0; score += d["annotation"]
        d["tags"] = 6 if item.get("tags") else 0; score += d["tags"]
        d["emotion"] = 6 if item.get("emotion") else 0; score += d["emotion"]
        d["translation"] = 8 if item.get("translation") else 0; score += d["translation"]
        d["audio"] = 7 if item.get("audio") else 0; score += d["audio"]
        d["related"] = 8 if item.get("related_works") else 0; score += d["related"]
        d["allusions"] = 7 if item.get("allusions") else 0; score += d["allusions"]
        if score >= 95: grade = "S"
        elif score >= 85: grade = "A"
        elif score >= 70: grade = "B"
        elif score >= 50: grade = "C"
        else: grade = "D"
        return {"score":score,"grade":grade,"details":d,"stars":"⭐"*(5 if grade=="S" else 4 if grade=="A" else 3 if grade=="B" else 2 if grade=="C" else 1)}

    def batch_quality_check(self, category="", limit=50):
        items = self.classics_db.search(category=category, limit=limit) if category else self.classics_db.search(limit=limit)
        results = []
        for item in items:
            r = self.quality_score(item["id"])
            results.append({"id":item["id"],"title":item["title"],"author":item["author"],"score":r["score"],"grade":r["grade"]})
        grades = {"S":0,"A":0,"B":0,"C":0,"D":0}
        for r in results: grades[r["grade"]] += 1
        return {"total":len(results),"grades":grades,"items":results[:20],"avg_score":sum(r["score"] for r in results)//max(len(results),1)}

    def quality_report(self):
        cats = self.classics_db.get_categories()
        report = []
        for cat in cats:
            r = self.batch_quality_check(cat["category"], limit=100)
            report.append({"category":cat["category"],"total":cat["count"],"avg_score":r["avg_score"],"grades":r["grades"]})
        return {"categories":report,"overall":self.batch_quality_check(limit=200)}

    def auto_proofread(self, classic_id):
        item = self.classics_db.get_by_id(classic_id)
        if not item: return "未找到"
        return self.engine.generate(f"校对作品：《{item['title']}》{item['author']}\n{item['content']}\n指出错字、缺句、标点错误。")

    def auto_maintenance(self):
        results = {}
        dedup = self.dedup_check()
        results["dedup"] = f"发现 {dedup['duplicates']} 组疑似重复"
        quality = self.batch_quality_check(limit=100)
        results["quality"] = f"均分 {quality['avg_score']}，S:{quality['grades']['S']} A:{quality['grades']['A']}"
        cats = self.classics_db.get_categories()
        target = ["唐诗","宋词","元曲","经典散文","蒙学","经部","子部","史部","集部"]
        missing = [c for c in target if c not in [x["category"] for x in cats]]
        results["missing"] = f"缺失分类：{', '.join(missing)}" if missing else "分类完整"
        results["backup"] = f"备份完成：{self.create_backup()}"
        return results

    def health_dashboard(self):
        stats = self.classics_db.get_stats()
        quality = self.batch_quality_check(limit=200)
        return {"total":stats["total"],"total_chars":stats["total_chars"],"avg_score":quality["avg_score"],"grades":quality["grades"],"categories":stats["categories"][:10],"health_score":min(100, quality["avg_score"])}

    def dedup_check(self, category="", threshold=0.85):
        items = self.classics_db.search(category=category, limit=1000) if category else self.classics_db.search(limit=1000)
        duplicates = []; seen = {}
        for item in items:
            key = item["title"][:4] + item.get("author","")[:2]
            if key in seen: duplicates.append({"keep":seen[key],"dup":item["id"],"title":item["title"]})
            else: seen[key] = item["id"]
        return {"total":len(items),"duplicates":len(duplicates),"pairs":duplicates[:20]}

    def clean_low_quality(self, min_score=30):
        quality = self.batch_quality_check(limit=500)
        removed = 0
        for item in quality.get("items",[]):
            if item["score"] < min_score:
                try: self.classics_db.conn.execute("DELETE FROM classics WHERE id=?",(item["id"],)); removed += 1
                except: pass
        self.classics_db.conn.commit()
        return f"已清理 {removed} 篇低质量数据"

    def recreate_buyun(self, classic_id):
        item = self.classics_db.get_by_id(classic_id)
        if not item: return "未找到"
        return self.engine.generate(f"步韵创作，原诗：《{item['title']}》\n{item['content']}\n用相同韵脚创作新诗。")

    def recreate_fangxie(self, classic_id, new_topic=""):
        item = self.classics_db.get_by_id(classic_id)
        if not item: return "未找到"
        return self.engine.generate(f"模仿《{item['title']}》风格，以「{new_topic or item['title']}」为题创作。\n原诗：{item['content']}")

    def recreate_fanxie(self, classic_id):
        item = self.classics_db.get_by_id(classic_id)
        if not item: return "未找到"
        return self.engine.generate(f"反其意创作：《{item['title']}》\n{item['content']}")

    def recreate_kuoxie(self, classic_id):
        item = self.classics_db.get_by_id(classic_id)
        if not item: return "未找到"
        return self.engine.generate(f"扩写：《{item['title']}》\n{item['content']}")

    def recreate_suoxie(self, classic_id):
        item = self.classics_db.get_by_id(classic_id)
        if not item: return "未找到"
        return self.engine.generate(f"缩写：《{item['title']}》\n{item['content']}")

    def recreate_modern(self, classic_id):
        item = self.classics_db.get_by_id(classic_id)
        if not item: return "未找到"
        return self.engine.generate(f"现代文改写：《{item['title']}》\n{item['content']}")

    def recreate_translate(self, classic_id, lang="en"):
        item = self.classics_db.get_by_id(classic_id)
        if not item: return "未找到"
        return self.engine.generate(f"翻译成{lang}：《{item['title']}》\n{item['content']}")

    def recreate_calligraphy(self, classic_id, style="颜体"):
        item = self.classics_db.get_by_id(classic_id)
        if not item: return "未找到"
        return f"【{style}书法】\n{item['content']}"

    def get_tts_options(self):
        return {"voices":TTSManager.get_voices(),"styles":TTSManager.get_styles(),"bgm":TTSManager.get_bgm()}

    def speak_text(self, text, voice="female", style="normal", speed=1.0):
        vc = TTSManager.VOICES.get(voice, TTSManager.VOICES["female"])
        sc = TTSManager.STYLES.get(style, TTSManager.STYLES["normal"])
        return {"text":text,"rate":round(vc["rate"]*sc.get("rate",0.8)*speed,2),"pitch":round(vc.get("pitch",1.0)*sc.get("pitch",1.0),2)}

    def evaluate_pronunciation(self, original, user_text):
        if not user_text: return {"score":0,"message":"未检测到朗读"}
        o = set(original.replace("\n","").replace(" ",""))
        u = set(user_text.replace("\n","").replace(" ",""))
        if not o: return {"score":0}
        s = len(o & u) / len(o) * 100
        g = "S" if s>=95 else "A" if s>=85 else "B" if s>=70 else "C"
        return {"score":round(s,1),"grade":g}

    def get_settings(self):
        settings = json.load(open("data/settings.json","r",encoding="utf-8")) if os.path.exists("data/settings.json") else {}
        api_cfg = settings.get("api",{})
        return {"provider":api_cfg.get("provider","deepseek"),"has_key":bool(api_cfg.get("api_key","")),"model":api_cfg.get("model","deepseek-chat"),"temperature":api_cfg.get("temperature",0.9),"max_tokens":api_cfg.get("max_tokens",512),"usage":settings.get("usage",{"monthly_calls":0,"monthly_tokens":0})}

    def save_api_settings(self, p, k, m, t, mt):
        from engine import encrypt
        os.makedirs("data", exist_ok=True)
        settings = json.load(open("data/settings.json","r",encoding="utf-8")) if os.path.exists("data/settings.json") else {}
        settings["api"] = {"provider":p,"api_key":encrypt(k) if k and k!="KEPT" else settings.get("api",{}).get("api_key",""),"model":m,"temperature":float(t),"max_tokens":int(mt)}
        with open("data/settings.json","w",encoding="utf-8") as f: json.dump(settings,f,ensure_ascii=False,indent=2)
        self.engine = CloudEngine(api_key=k)
        return "设置已保存"

    def test_api_key(self, key, provider):
        ok, msg = self.engine.test_connection(key, provider)
        return {"success":ok,"message":msg}

    def check_update(self):
        has = self.updater.check_update()
        if has: return {"has_update":True,"current":self.updater.current,"latest":self.updater.update_info["version"],"url":self.updater.update_info["url"]}
        return {"has_update":False,"current":self.updater.current}

    def get_version_info(self): return VersionManager.get_full_info()
    def get_changelog(self): return self.updater.get_changelog()

    def run_tests(self):
        from test_runner import TestRunner
        r = TestRunner()
        s = r.run()
        return {"success":s,"passed":r.passed,"failed":r.failed}

    def close(self): self.db.close(); self.classics_db.close(); self.online_importer.close(); self.async_queue.shutdown()


HTML = r"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><title>心语 V8.2</title><style>
:root{--bg:#f5f0e6;--text:#4e342e;--card:#fff;--menu-bg:#5d4037;--menu-text:#ffecb3;--border:#d7ccc8;--accent:#8d6e63}
.theme-dark{--bg:#1e1e1e;--text:#d4c5a9;--card:#2c2c2c;--menu-bg:#111;--menu-text:#d4c5a9;--border:#444;--accent:#a08060}
.theme-paper{--bg:#f5f0e6;--text:#3e2e1e;--card:#fffbf0;--menu-bg:#4a3628;--menu-text:#e8d5b0;--border:#c8b8a0;--accent:#7a5e4e}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Microsoft YaHei",sans-serif;background:var(--bg);color:var(--text);font-size:14px}
.menubar{display:flex;background:var(--menu-bg);padding:0 8px}
.menu{position:relative}
.menu-btn{background:none;border:none;color:var(--menu-text);padding:8px 14px;cursor:pointer}
.menu-btn:hover{background:rgba(255,255,255,0.15)}
.dropdown{display:none;position:absolute;background:var(--card);min-width:200px;box-shadow:0 4px 12px rgba(0,0,0,0.2);z-index:100;border-radius:0 0 6px 6px;max-height:500px;overflow-y:auto}
.dropdown a{display:block;padding:8px 16px;color:var(--text);text-decoration:none;cursor:pointer}
.dropdown a:hover{background:var(--border)}
.menu:hover .dropdown{display:block}
.toolbar{display:flex;gap:8px;padding:10px;flex-wrap:wrap;align-items:center}
select,input,button{padding:6px 12px;border:1px solid var(--border);border-radius:4px;background:var(--card);color:var(--text)}
button{background:var(--accent);color:#fff;cursor:pointer;border:none}button:hover{opacity:0.85}
input{flex:1;min-width:150px}
.result-card{background:var(--card);border:1px solid var(--border);padding:15px;white-space:pre-wrap;line-height:1.8;min-height:120px;margin:10px}
.tabs{display:flex;gap:4px;margin:0 10px}
.tab-btn{background:var(--border);padding:6px 16px;border-radius:4px 4px 0 0;cursor:pointer}
.tab-btn.active{background:var(--accent);color:#fff}
.check-result{margin:8px 10px;padding:8px 12px;background:#fff8e1;border-left:4px solid #ff8f00;color:#bf360c}
.action-btns{display:flex;gap:6px;padding:10px;flex-wrap:wrap}
.hidden{display:none!important}
.status-bar{position:fixed;bottom:0;left:0;right:0;background:var(--menu-bg);color:var(--menu-text);text-align:center;padding:4px;font-size:12px;z-index:200}
.draggable-panel{position:fixed;z-index:260;background:var(--card);border-radius:8px;box-shadow:0 8px 32px rgba(0,0,0,0.3);display:flex;flex-direction:column;min-width:300px;min-height:200px;resize:both;overflow:auto}
.draggable-panel .panel-header{cursor:move;display:flex;justify-content:space-between;padding:10px 12px;background:var(--menu-bg);color:var(--menu-text);border-radius:8px 8px 0 0}
.draggable-panel .panel-content{flex:1;overflow-y:auto;padding:12px}
.panel-overlay{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.3);z-index:255}
.panel-item{padding:8px;border-bottom:1px solid var(--border);cursor:pointer}
.panel-item:hover{background:var(--border)}
.panel-actions{display:flex;gap:6px;margin-top:10px;flex-wrap:wrap}
.panel-actions button{font-size:12px;padding:5px 10px}
.panel-content-text{white-space:pre-wrap;line-height:1.8;margin:10px 0;padding:10px;background:var(--bg);border-radius:4px}
.pagination{display:flex;gap:4px;justify-content:center;padding:8px;flex-wrap:wrap}
.pagination button{padding:4px 10px;font-size:12px}
.pagination .active{background:#c62828}
.chat-btn{position:fixed;right:20px;bottom:20px;width:56px;height:56px;border-radius:50%;background:var(--accent);color:#fff;font-size:24px;z-index:150;cursor:pointer;box-shadow:0 4px 12px rgba(0,0,0,0.3);display:flex;align-items:center;justify-content:center}
.chat-window{width:380px;height:480px;left:auto;right:20px;top:50%;transform:translateY(-50%);resize:both;overflow:auto;min-width:320px;min-height:300px;max-width:600px;max-height:700px}
.chat-messages{flex:1;overflow-y:auto;padding:12px}
.chat-msg{margin-bottom:10px;display:flex;flex-direction:column}
.chat-msg.user{align-items:flex-end}
.chat-msg.ai{align-items:flex-start}
.chat-msg .bubble{padding:8px 12px;border-radius:12px;max-width:85%;word-wrap:break-word;font-size:13px}
.chat-msg.user .bubble{background:var(--accent);color:#fff;border-radius:12px 12px 0 12px}
.chat-msg.ai .bubble{background:var(--border);color:var(--text);border-radius:12px 12px 12px 0}
.chat-input-area{display:flex;padding:10px;border-top:1px solid var(--border)}
.chat-input-area input{flex:1;margin-right:8px}
.chat-actions-bar{display:flex;gap:4px;padding:4px 10px;flex-wrap:wrap;border-top:1px solid var(--border)}
.chat-actions-bar button{font-size:10px;padding:3px 8px}
.analysis-section{margin:10px 0;padding:10px;background:var(--bg);border-radius:8px}
.analysis-section h4{color:var(--accent);margin-bottom:6px}
.classics-panel{top:0;right:0;width:480px;height:100%;border-radius:0;resize:horizontal}
.expand-panel{width:500px;height:auto;left:50%;top:50%;transform:translate(-50%,-50%);resize:none}
.expand-panel .form-row{display:flex;gap:8px;margin:6px 0;align-items:center}
.expand-panel label{min-width:60px;font-size:13px}
.expand-panel select{flex:1}
</style></head><body>
<div class="menubar">
<div class="menu"><button class="menu-btn">文件</button><div class="dropdown">
<a onclick="exportTxt()">导出TXT</a><a onclick="exportImage()">导出图片</a><a onclick="exportLetter()">信笺</a><a onclick="saveWork()">保存</a><a onclick="openWorks()">作品库</a><a onclick="batchExport()">批量导出</a><a onclick="showUsage()">使用统计</a></div></div>
<div class="menu"><button class="menu-btn">创作</button><div class="dropdown">
<a onclick="randomTopic()">随机主题</a><a onclick="continueMode()">续写</a><a onclick="critiqueWork()">品评</a></div></div>
<div class="menu"><button class="menu-btn">经典</button><div class="dropdown">
<a onclick="openClassicsPanel('经部')">经部</a><a onclick="openClassicsPanel('史部')">史部</a><a onclick="openClassicsPanel('子部')">子部</a><a onclick="openClassicsPanel('集部')">集部</a><a onclick="openClassicsPanel('蒙学')">蒙学</a>
<hr><a onclick="openClassicsPanel('唐诗')">唐诗</a><a onclick="openClassicsPanel('宋词')">宋词</a><a onclick="openClassicsPanel('经典散文')">经典散文</a><a onclick="openClassicsPanel('论语')">论语</a><a onclick="openClassicsPanel('诗经')">诗经</a><a onclick="openClassicsPanel('楚辞')">楚辞</a>
<hr><a onclick="openHealthPanel()">数据健康</a><a onclick="showFavorites()">收藏</a></div></div>
<div class="menu"><button class="menu-btn">设置</button><div class="dropdown"><a onclick="openSettings()">API设置</a></div></div>
<div class="menu"><button class="menu-btn">帮助</button><div class="dropdown">
<a onclick="checkUpdate()">检查更新</a><a onclick="openDeepSeekChat()">DeepSeek对话</a><a onclick="showAbout()">关于</a><a onclick="showShortcuts()">快捷键</a></div></div>
</div>
<div class="toolbar">
<select id="genreSelect" onchange="updateStyles()"><option>五言绝句</option><option>七言绝句</option><option>如梦令</option><option>蝶恋花</option><option>现代歌词</option><option>抒情散文</option></select>
<select id="styleSelect"></select>
<input id="topicInput" placeholder="主题，如：秋夜">
<button onclick="randomTopic()">随机</button>
<button id="generateBtn" onclick="generate()">生成</button>
<button onclick="speakCurrent()">朗读</button>
</div>
<div class="tabs" id="tabs"></div>
<div class="result-card" id="resultCard">点击"生成"开始创作...</div>
<div class="check-result hidden" id="checkResult"></div>
<div class="action-btns">
<button onclick="exportTxt()">导出TXT</button><button onclick="exportImage()">导出图片</button><button onclick="saveWork()">保存</button><button onclick="copyResult()">复制</button>
</div>
<div class="status-bar" id="statusBar">就绪 | 心语 V8.2</div>
<div class="panel-overlay hidden" id="classicsOverlay" onclick="closeClassicsPanel()"></div>
<div class="draggable-panel classics-panel hidden" id="classicsPanel">
<div class="panel-header" id="classicsHeader"><span>经典文库</span><button onclick="closeClassicsPanel()" style="background:none;color:var(--menu-text);border:none;font-size:18px;cursor:pointer">x</button></div>
<div class="panel-content" id="classicsContent"></div>
<div class="pagination" id="classicsPagination"></div>
</div>
<div class="chat-btn" onclick="toggleChat()">🤖</div>
<div class="draggable-panel chat-window hidden" id="chatWindow">
<div class="panel-header" id="chatHeader"><span>AI 诗词助手</span><button onclick="closeChatWindow()" style="background:none;color:var(--menu-text);border:none;cursor:pointer;font-size:18px">x</button></div>
<div class="chat-messages" id="chatMessages"><div class="chat-msg ai"><div class="bubble">你好！我是心语AI诗词助手。<br>/deep 静夜思 - 六维赏析<br>/write 诗 李白 秋夜 - 创作<br>/expand 宋词 50 - 扩充<br>/stats - 统计<br>/help - 更多命令</div></div></div>
<div class="chat-actions-bar">
<button onclick="sendCmd('/deep ')">赏析</button><button onclick="sendCmd('/write ')">创作</button><button onclick="openExpandPanel()">扩充</button><button onclick="sendCmd('/stats')">统计</button><button onclick="sendCmd('/help')">帮助</button><button onclick="exportChat()">导出对话</button>
</div>
<div class="chat-input-area"><input id="chatInput" placeholder="输入消息或命令..." onkeydown="if(event.key==='Enter')sendChat()"><button onclick="sendChat()">发送</button></div>
</div>
<div class="panel-overlay hidden" id="expandOverlay" onclick="closeExpandPanel()"></div>
<div class="draggable-panel expand-panel hidden" id="expandPanel">
<div class="panel-header" id="expandHeader"><span>智能扩充</span><button onclick="closeExpandPanel()" style="background:none;color:var(--menu-text);border:none;font-size:18px;cursor:pointer">x</button></div>
<div class="panel-content">
<div class="form-row"><label>分类</label><select id="expandCat"><option>唐诗</option><option>宋词</option><option>元曲</option><option>经典散文</option><option>蒙学</option><option>经部</option><option>子部</option><option>史部</option><option>集部</option></select></div>
<div class="form-row"><label>时代</label><select id="expandEra"><option value="">不限</option><option>先秦</option><option>两汉</option><option>魏晋</option><option>唐</option><option>宋</option><option>元</option><option>明</option><option>清</option></select></div>
<div class="form-row"><label>流派</label><select id="expandSchool"><option value="">不限</option><option>婉约</option><option>豪放</option><option>山水</option><option>边塞</option><option>儒家</option><option>道家</option></select></div>
<div class="form-row"><label>数量</label><select id="expandCount"><option>10</option><option>30</option><option>50</option><option>100</option></select></div>
<button onclick="startExpand()" style="width:100%;margin-top:10px;padding:10px">开始智能扩充</button>
<div id="expandProgress" style="margin-top:10px;font-size:13px"></div>
<div style="margin-top:10px"><b>扩充日志</b><div id="expandLog" style="font-size:11px;max-height:120px;overflow-y:auto"></div></div>
</div></div>

<script>
let currentResults=[],currentGenre="",activeTab=0,chatHistory=[],currentPage=1,pageSize=20,panelData=[],panelCat="";
window.addEventListener("load",async()=>{await updateStyles();setTheme(localStorage.getItem("theme")||"paper");pywebview.api.load_chat_history().then(h=>{if(h&&h!=="[]"){chatHistory=JSON.parse(h);chatHistory.slice(-10).forEach(m=>addChatMsg(m.role,m.content))}});makeDraggable("classicsPanel","classicsHeader");makeDraggable("chatWindow","chatHeader");makeDraggable("expandPanel","expandHeader")});
function setTheme(t){document.body.className=t?"theme-"+t:"";localStorage.setItem("theme",t||"paper")}
function makeDraggable(panelId,headerId){let p=document.getElementById(panelId),h=document.getElementById(headerId);if(!p||!h)return;let ox,oy,px,py,down=false;h.onmousedown=function(e){down=true;ox=e.clientX;oy=e.clientY;px=p.offsetLeft;py=p.offsetTop;document.onmousemove=function(e){if(!down)return;p.style.left=(px+e.clientX-ox)+"px";p.style.top=(py+e.clientY-oy)+"px";p.style.right="auto";p.style.bottom="auto";p.style.transform="none"};document.onmouseup=function(){down=false}}}
async function updateStyles(){let g=document.getElementById("genreSelect").value;currentGenre=g;let s=await pywebview.api.get_styles(g),sel=document.getElementById("styleSelect");sel.innerHTML="<option value=''>默认风格</option>";s.forEach(x=>{let o=document.createElement("option");o.value=JSON.stringify(x);o.text=x.label;sel.appendChild(o)})}
async function generate(){let topic=document.getElementById("topicInput").value.trim();if(!topic){topic=await pywebview.api.get_random_topic();document.getElementById("topicInput").value=topic}let sv=document.getElementById("styleSelect").value,si=sv?JSON.parse(sv):null;let btn=document.getElementById("generateBtn");btn.disabled=true;btn.textContent="生成中...";try{let results=await pywebview.api.generate(currentGenre,topic,si);if(!Array.isArray(results))results=[results];currentResults=results;activeTab=0;renderTabs();if(currentGenre.includes("绝句")){let check=await pywebview.api.check_poem(results[0],currentGenre);document.getElementById("checkResult").classList.remove("hidden");document.getElementById("checkResult").innerHTML="<b>格律检测：</b>"+(Array.isArray(check)?check.join("<br>"):check)}else{document.getElementById("checkResult").classList.add("hidden")}showStatus("生成完毕")}catch(e){showStatus("生成失败: "+e)}btn.disabled=false;btn.textContent="生成"}
function renderTabs(){let td=document.getElementById("tabs");td.innerHTML="";for(let i=0;i<currentResults.length;i++){let b=document.createElement("button");b.className="tab-btn"+(i===activeTab?" active":"");b.textContent="候选 "+(i+1);b.onclick=()=>{activeTab=i;renderTabs();document.getElementById("resultCard").textContent=currentResults[activeTab]}};document.getElementById("resultCard").textContent=currentResults[activeTab]||""}
function showStatus(m){document.getElementById("statusBar").textContent=m}
async function exportTxt(){if(!currentResults.length)return;showStatus("已导出: "+await pywebview.api.export_txt(currentResults[activeTab]))}
async function exportImage(){if(!currentResults.length)return;showStatus("已导出: "+await pywebview.api.export_image_api(currentResults[activeTab],24,[255,250,240],""))}
async function exportLetter(){if(!currentResults.length)return;showStatus("已导出: "+await pywebview.api.export_letter(currentResults[activeTab],"","心语"))}
async function saveWork(){if(!currentResults.length)return;let sv=document.getElementById("styleSelect").value,si=sv?JSON.parse(sv):null,topic=document.getElementById("topicInput").value;await pywebview.api.save_work(currentGenre,si,topic,currentResults[activeTab]);showStatus("已保存")}
function copyResult(){if(!currentResults.length)return;navigator.clipboard.writeText(currentResults[activeTab]);showStatus("已复制")}
async function randomTopic(){document.getElementById("topicInput").value=await pywebview.api.get_random_topic()}
function speakCurrent(){if(!currentResults.length)return;let u=new SpeechSynthesisUtterance(currentResults[activeTab]);u.lang="zh-CN";u.rate=0.8;window.speechSynthesis.speak(u)}
async function critiqueWork(){if(!currentResults.length)return;alert(await pywebview.api.critique(currentResults[activeTab],currentGenre))}
function continueMode(){if(!currentResults.length)return;let l=prompt("输入诗句：","");if(l)pywebview.api.smart_continue(l).then(r=>alert(r.map(x=>"【"+x.direction+"】\n"+x.full_poem).join("\n\n")))}
async function openWorks(){let w=await pywebview.api.search_works();if(!w.length){alert("作品库为空");return}alert("最近作品：\n"+w.slice(0,8).map((x,i)=>(i+1)+". ["+x[1]+"] "+x[3]).join("\n"))}
function showShortcuts(){alert("快捷键\nCtrl+Enter 生成\nCtrl+S 保存")}
async function showAbout(){let i=await pywebview.api.get_version_info();alert(i.name+" V"+i.version+"\n"+i.codename+"\n"+i.author)}
async function checkUpdate(){let r=await pywebview.api.check_update();alert(r.has_update?"新版本 V"+r.latest+" 可用！":"已是最新版本 V"+r.current)}
async function openHealthPanel(){let d=await pywebview.api.health_dashboard();alert("数据健康度："+d.health_score+"\n总篇数："+d.total+"\n均分："+d.avg_score)}
async function openSettings(){alert("API设置：菜单→设置→API设置")}
function openDeepSeekChat(){window.open("https://chat.deepseek.com","_blank")}
async function batchExport(){let w=await pywebview.api.search_works();if(!w.length){alert("作品库为空");return}let all=w.map(x=>"【"+x[1]+"】"+x[3]+"\n"+x[4]).join("\n\n---\n\n");let p=await pywebview.api.export_txt(all);showStatus("已批量导出: "+p)}
async function showUsage(){let s=await pywebview.api.get_settings();let u=s.usage||{};alert("本月调用: "+u.monthly_calls+"次\nToken消耗: "+u.monthly_tokens)}

function openClassicsPanel(cat){panelCat=cat;currentPage=1;document.getElementById("classicsPanel").classList.remove("hidden");document.getElementById("classicsOverlay").classList.remove("hidden");loadClassicsPage()}
function closeClassicsPanel(){document.getElementById("classicsPanel").classList.add("hidden");document.getElementById("classicsOverlay").classList.add("hidden")}
async function loadClassicsPage(){let results=await pywebview.api.search_classics_v2("",panelCat,"","",500);panelData=results;renderClassicsPage()}
function renderClassicsPage(){let start=(currentPage-1)*pageSize,end=Math.min(start+pageSize,panelData.length);let items=panelData.slice(start,end);let html="<h3>"+panelCat+"（共"+panelData.length+"篇）</h3>";items.forEach((x,i)=>{html+="<div class='panel-item' onclick='showPanelDetail(\""+x.id+"\")'>"+(start+i+1)+"."+(x.is_famous?"⭐":"")+"《"+x.title+"》"+x.author+"（"+x.dynasty+"）</div>"});document.getElementById("classicsContent").innerHTML=html;renderPagination()}
function renderPagination(){let tp=Math.ceil(panelData.length/pageSize);let html="";html+="<button onclick='goPage(1)'>首页</button><button onclick='goPage("+(currentPage-1)+")'>上一页</button>";for(let i=Math.max(1,currentPage-2);i<=Math.min(tp,currentPage+2);i++){html+="<button class='"+(i==currentPage?"active":"")+"' onclick='goPage("+i+")'>"+i+"</button>"}html+="<button onclick='goPage("+(currentPage+1)+")'>下一页</button><button onclick='goPage("+tp+")'>末页</button>";html+="<span style='font-size:12px'>第"+currentPage+"/"+tp+"页</span>";document.getElementById("classicsPagination").innerHTML=html}
function goPage(p){currentPage=Math.max(1,Math.min(Math.ceil(panelData.length/pageSize),p));renderClassicsPage()}
async function showPanelDetail(id){let item=await pywebview.api.get_classic_by_id_v2(id);if(!item)return;let html="<h3>《"+item.title+"》</h3><p>"+item.author+"（"+item.dynasty+"） | "+item.category+"</p><div class='panel-content-text'>"+item.content.replace(/\\n/g,"<br>")+"</div><div class='panel-actions'><button onclick='speakText(\""+id+"\")'>朗读</button><button onclick='deepAnalysis(\""+id+"\")'>六维赏析</button><button onclick='qualityCheck(\""+id+"\")'>质量评分</button><button onclick='openRecreatePanel(\""+id+"\")'>二创</button><button onclick='favoritePanelDetail(\""+id+"\")'>收藏</button><button onclick='citePanelDetail(\""+item.title+"\")'>引用</button><button onclick='loadClassicsPage()'>返回列表</button></div>";document.getElementById("classicsContent").innerHTML=html;document.getElementById("classicsPagination").innerHTML=""}
function speakText(id){pywebview.api.get_classic_by_id_v2(id).then(item=>{if(item){let u=new SpeechSynthesisUtterance(item.content);u.lang="zh-CN";u.rate=0.7;window.speechSynthesis.speak(u)}})}
async function deepAnalysis(id){let r=await pywebview.api.deep_analysis(id);if(r.error){alert(r.error);return}let html="<h3>六维赏析</h3>";["background","text_analysis","artistic","rhythm","culture","teaching"].forEach(k=>{html+="<div class='analysis-section'><h4>"+{"background":"背景","text_analysis":"解读","artistic":"意境","rhythm":"格律","culture":"文化","teaching":"教学"}[k]+"</h4><p>"+(r[k]||"")+"</p></div>"});html+="<button onclick='loadClassicsPage()'>返回列表</button>";document.getElementById("classicsContent").innerHTML=html;document.getElementById("classicsPagination").innerHTML=""}
async function qualityCheck(id){let r=await pywebview.api.quality_score(id);let html="<h3>质量评分</h3><p style='font-size:24px'>"+r.score+"分 "+r.stars+" 等级"+r.grade+"</p>";html+="<button onclick='loadClassicsPage()'>返回列表</button>";document.getElementById("classicsContent").innerHTML=html;document.getElementById("classicsPagination").innerHTML=""}
function openRecreatePanel(id){let html="<h3>二创工坊</h3><div style='display:grid;grid-template-columns:1fr 1fr;gap:6px'>";["buyun","fangxie","fanxie","kuoxie","suoxie","modern","translate"].forEach(t=>{html+="<button onclick='doRecreate(\""+id+"\",\""+t+"\")'>"+{"buyun":"步韵","fangxie":"仿写","fanxie":"反写","kuoxie":"扩写","suoxie":"缩写","modern":"现代文","translate":"翻译"}[t]+"</button>"});html+="</div><div id='recreateResult' style='margin-top:12px'></div>";document.getElementById("classicsContent").innerHTML=html;document.getElementById("classicsPagination").innerHTML=""}
async function doRecreate(id,type){let r;if(type=="buyun")r=await pywebview.api.recreate_buyun(id);else if(type=="fangxie")r=await pywebview.api.recreate_fangxie(id);else if(type=="fanxie")r=await pywebview.api.recreate_fanxie(id);else if(type=="kuoxie")r=await pywebview.api.recreate_kuoxie(id);else if(type=="suoxie")r=await pywebview.api.recreate_suoxie(id);else if(type=="modern")r=await pywebview.api.recreate_modern(id);else if(type=="translate")r=await pywebview.api.recreate_translate(id);document.getElementById("recreateResult").innerHTML="<div class='panel-content-text'>"+r.replace(/\\n/g,"<br>")+"</div>"}
function favoritePanelDetail(id){pywebview.api.add_favorite(id);showStatus("已收藏")}
function citePanelDetail(title){document.getElementById("topicInput").value=title;closeClassicsPanel();showStatus("已设置主题为"+title)}
async function showFavorites(){let results=await pywebview.api.get_favorites();if(!results.length){alert("收藏夹为空");return}panelData=results;panelCat="我的收藏";currentPage=1;document.getElementById("classicsPanel").classList.remove("hidden");document.getElementById("classicsOverlay").classList.remove("hidden");renderClassicsPage()}

function toggleChat(){document.getElementById("chatWindow").classList.remove("hidden")}
function closeChatWindow(){document.getElementById("chatWindow").classList.add("hidden")}
function sendChat(){let input=document.getElementById("chatInput");let msg=input.value.trim();if(!msg)return;addChatMsg("user",msg);input.value="";processCommand(msg)}
function sendCmd(cmd){document.getElementById("chatInput").value=cmd;document.getElementById("chatInput").focus()}
function addChatMsg(role,text){chatHistory.push({role:role,content:text});let div=document.createElement("div");div.className="chat-msg "+role;div.innerHTML="<div class='bubble'>"+text.replace(/\n/g,"<br>")+"</div>";document.getElementById("chatMessages").appendChild(div);div.scrollIntoView({behavior:"smooth"})}
function exportChat(){let text=chatHistory.map(m=>"【"+(m.role=="user"?"我":"AI")+"】"+m.content).join("\n\n");pywebview.api.export_txt(text).then(p=>showStatus("对话已导出: "+p))}
async function processCommand(msg){
    let parts=msg.split(" ");let cmd=parts[0].toLowerCase();
    if(cmd==="/deep"){let t=parts.slice(1).join(" ");let r=await pywebview.api.search_classics_v2(t,"","","",1);if(r.length){let a=await pywebview.api.deep_analysis(r[0].id);addChatMsg("ai","《"+r[0].title+"》赏析\n背景:"+a.background+"\n解读:"+a.text_analysis+"\n意境:"+a.artistic+"\n格律:"+a.rhythm+"\n文化:"+a.culture+"\n教学:"+a.teaching)}else{addChatMsg("ai","未找到")}}
    else if(cmd==="/write"){let g=parts[1]||"诗";let s=parts[2]||"李白";let tp=parts.slice(3).join(" ")||"秋夜";let m={"诗":"五言绝句","词":"如梦令"};let r=await pywebview.api.generate(m[g]||"五言绝句",tp,{"instruction":"模仿"+s+"风格"});addChatMsg("ai","✍️ "+(Array.isArray(r)?r[0]:r))}
    else if(cmd==="/expand"){let cat=parts[1]||"唐诗";let cnt=parseInt(parts[2])||10;addChatMsg("ai","扩充中...");let r=await pywebview.api.smart_expand_advanced("","","",cat,cnt);addChatMsg("ai","已扩充 "+r.imported+" 篇")}
    else if(cmd==="/stats"){let s=await pywebview.api.get_classic_stats();addChatMsg("ai","总篇数："+s.total+"\n总字数："+s.total_chars.toLocaleString())}
    else if(cmd==="/health"){let d=await pywebview.api.health_dashboard();addChatMsg("ai","健康度："+d.health_score+"\n均分："+d.avg_score)}
    else if(cmd==="/version"){let v=await pywebview.api.get_version_info();addChatMsg("ai",v.name+" V"+v.version)}
    else if(cmd==="/update"){let r=await pywebview.api.check_update();addChatMsg("ai",r.has_update?"新版本 V"+r.latest+" 可用！":"已是最新")}
    else if(cmd==="/help"){addChatMsg("ai","命令：\n/deep 静夜思 - 赏析\n/write 诗 李白 秋夜 - 创作\n/expand 宋词 50 - 扩充\n/stats - 统计\n/health - 健康\n/version - 版本\n/update - 更新\n/clear - 清空")}
    else if(cmd==="/clear"){clearChat()}
    else{addChatMsg("ai","...");try{let r=await pywebview.api.chat(msg,JSON.stringify(chatHistory.slice(-20)));document.querySelector("#chatMessages .chat-msg.ai:last-child .bubble").textContent=r;chatHistory.push({role:"assistant",content:r});pywebview.api.save_chat_history(JSON.stringify(chatHistory))}catch(e){document.querySelector("#chatMessages .chat-msg.ai:last-child .bubble").textContent="错误: "+e}}
}
function clearChat(){document.getElementById("chatMessages").innerHTML='<div class="chat-msg ai"><div class="bubble">对话已清空。输入 /help 查看命令。</div></div>';chatHistory=[]}

function openExpandPanel(){document.getElementById("expandPanel").classList.remove("hidden");document.getElementById("expandOverlay").classList.remove("hidden");loadExpandLog()}
function closeExpandPanel(){document.getElementById("expandPanel").classList.add("hidden");document.getElementById("expandOverlay").classList.add("hidden")}
async function startExpand(){let cat=document.getElementById("expandCat").value;let era=document.getElementById("expandEra").value;let school=document.getElementById("expandSchool").value;let count=parseInt(document.getElementById("expandCount").value);closeExpandPanel();pywebview.api.smart_expand_advanced(era,"",school,cat,count).then(r=>{showStatus("扩充完成！新增 "+r.imported+" 篇");loadExpandLog()})}
async function loadExpandLog(){let logs=await pywebview.api.get_expand_log();let html=logs.slice(-10).reverse().map(l=>"📅 "+l.time+" | "+l.category+" +"+l.count+"篇").join("<br>");document.getElementById("expandLog").innerHTML=html||"暂无记录"}
</script></body></html>"""

if __name__ == "__main__":
    api = API()
    window = webview.create_window("心语 V8.2", html=HTML, js_api=api, width=1100, height=750)
    webview.start()
    api.close()