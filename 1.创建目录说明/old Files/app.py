"""
心语 V6.6 · 古典诗词 AI 工作站
文脉相承 — 诸子百家、秦汉唐宋、经典散文
开发者：hedongwei
联系邮箱：1265338136@qq.com
"""
import os
os.environ['MMKV_LOG_LEVEL'] = 'off'

import warnings
warnings.filterwarnings("ignore")

import webview
import json
import random
from datetime import datetime

from engine import CloudEngine, LocalEngine
from style_manager import StyleManager
from poetry_checker import check_jueju, check_cipai
from lyric_checker import get_rhyme_groups, check_structure
from database import Database
from exporter import (
    export_image, export_letter_style, export_fan_style,
    export_couplet_style, export_spring_couplet, export_social_card
)
from classic_library import ClassicLibrary
from classics_database import ClassicsDatabase
from classics_importer import ClassicsImporter
from online_importer import OnlineImporter
from preference_learner import PreferenceLearner
from annotation_manager import AnnotationManager
from plugin_manager import PluginManager
from backup_manager import BackupManager


class API:
    def __init__(self):
        self.engine = CloudEngine(provider="deepseek", api_key="sk-REPLACE_WITH_YOUR_KEY")
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
        self.cache = {}

        if self.classics_db.get_total_count() == 0:
            count = self.classics_importer.import_sample_data()
            print(f"已自动导入 {count} 篇经典范文到本地数据库")

    def set_engine(self, mode):
        if mode == "online":
            self.engine = CloudEngine(provider="deepseek", api_key="sk-REPLACE_WITH_YOUR_KEY")
        else:
            self.engine = LocalEngine("models/poem.gguf")
        return f"引擎切换至: {mode}"

    def generate(self, genre, topic, style_info):
        cache_key = f"{genre}|{topic}|{json.dumps(style_info or {})}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        prompt = self.style_mgr.build_prompt(genre, topic, style_info)
        results = []
        for _ in range(3):
            try:
                text = self.engine.generate(prompt)
                results.append(text.strip())
            except Exception as e:
                results.append(f"生成失败: {e}")
        if results:
            self.preferences.record(genre, style_info or {}, topic)
            self.cache[cache_key] = results
        return results

    def get_styles(self, genre):
        return self.style_mgr.get_styles_for_genre(genre)

    def check_poem(self, poem, genre):
        lines = [l.strip() for l in poem.split('\n') if l.strip()]
        if "绝句" in genre or "律诗" in genre:
            return check_jueju(lines)
        elif genre in ["如梦令", "蝶恋花"]:
            return check_cipai(genre, lines)
        return "无需格律检测"

    def check_lyric(self, lyric):
        lines = lyric.split('\n')
        _, rhyme_map = get_rhyme_groups(lines)
        struct = check_structure(lyric)
        return {"rhyme_groups": {k: v for k, v in rhyme_map.items()}, "issues": struct}

    def get_word_suggestions(self, char):
        try:
            with open("resources/word_relations.json", 'r', encoding='utf-8') as f:
                relations = json.load(f)
        except:
            relations = {}
        rhymes = self.get_rhyme_suggestions(char)
        result = {"char": char, "rhymes": rhymes, "synonyms": [], "allusions": [], "collocations": []}
        if char in relations:
            result["synonyms"] = relations[char].get("synonyms", [])[:8]
            result["allusions"] = relations[char].get("allusions", [])[:5]
            result["collocations"] = relations[char].get("collocations", [])[:6]
        return result

    def get_rhyme_suggestions(self, char):
        from pypinyin import pinyin, Style
        final = pinyin(char, style=Style.FINALS)[0][0]
        try:
            with open("resources/rhyme_dict.json", 'r', encoding='utf-8') as f:
                rhyme_dict = json.load(f)
            return rhyme_dict.get(final, [])[:20]
        except:
            return []

    def replace_word(self, full_text, line_idx, char_idx, new_word):
        lines = full_text.split('\n')
        if line_idx < len(lines):
            chars = list(lines[line_idx])
            if char_idx < len(chars):
                chars[char_idx] = new_word
                lines[line_idx] = ''.join(chars)
        return '\n'.join(lines)

    def critique(self, poem, genre):
        prompt = f"你是古典文学教授，请对下面这首{genre}进行品评。\n从意境、章法、炼字、用典四方面打分(1-10)并评语，最后总评。\n作品：\n{poem}"
        return self.engine.generate(prompt)

    def smart_continue(self, user_line):
        directions = [
            {"name": "意境延伸", "instruction": "保持意境，自然延伸"},
            {"name": "情感转折", "instruction": "在结尾制造情感转折"},
            {"name": "哲理升华", "instruction": "由景入理，升华哲理"}
        ]
        results = []
        for d in directions:
            prompt = f"续写诗句。\n原句：{user_line}\n方向：{d['instruction']}\n请输出完整诗作。"
            results.append({"direction": d["name"], "full_poem": self.engine.generate(prompt)})
        return results

    def create_cento(self, keywords):
        prompt = f"请以「{keywords}」为主题，创作一首集句诗。\n要求：每句需化用或引用经典名句，注明出处，整体意境连贯。"
        return self.engine.generate(prompt)

    def generate_couplet(self, upper=""):
        if upper:
            prompt = f"上联：{upper}\n请对出下联，并给出横批。要求对仗工整，平仄相对。"
        else:
            prompt = "请创作一副完整的对联（上联、下联、横批），主题不限，要求对仗工整。"
        return self.engine.generate(prompt)

    def poem_response(self, original):
        prompt = f"原诗：\n{original}\n\n请以同样的韵脚和相似意境创作一首唱和诗。"
        return self.engine.generate(prompt)

    def allusion_deep_dive(self, allusion_name):
        prompt = f"请详细解析典故「{allusion_name}」，包括：出处、原文、含义、常见用法、相关诗词例句。"
        return self.engine.generate(prompt)

    def get_suggestion(self, poem, errors):
        suggestions = []
        if isinstance(errors, list) and errors:
            suggestions.append(f"检测到{len(errors)}处格律问题")
        if '明月' in poem:
            suggestions.append('"明月"可替换为"冰轮""玉盘"')
        return suggestions

    # ========== 经典文库（JSON版） ==========
    def search_classics(self, keyword="", category=""):
        return self.library.search(keyword, category)

    def get_classic_categories(self):
        return self.library.get_categories()

    def random_classic(self):
        return self.library.get_random()

    # ========== 经典文库（数据库版） ==========
    def search_classics_v2(self, keyword="", category="", dynasty="", author="", limit=50):
        return self.classics_db.search(keyword, category, dynasty, author, None, limit)

    def get_classic_stats(self):
        return self.classics_db.get_stats()

    def get_classic_categories_v2(self):
        return self.classics_db.get_categories()

    def get_classic_dynasties_v2(self):
        return self.classics_db.get_dynasties()

    def get_classic_authors_v2(self):
        return self.classics_db.get_authors()

    def get_classic_by_id_v2(self, classic_id):
        return self.classics_db.get_by_id(classic_id)

    def import_classics_from_json(self, json_path):
        count = self.classics_importer.import_from_json(json_path)
        return f"成功导入 {count} 篇经典"

    def record_classic_read(self, classic_id):
        self.classics_db.record_read(classic_id)

    def add_classic_note(self, classic_id, note_text):
        self.classics_db.add_note(classic_id, note_text)

    def get_classic_notes(self, classic_id):
        return self.classics_db.get_notes(classic_id)

    def add_favorite(self, classic_id):
        self.classics_db.add_favorite(classic_id)

    def remove_favorite(self, classic_id):
        self.classics_db.remove_favorite(classic_id)

    def get_favorites(self):
        return self.classics_db.get_favorites()

    def get_random_classic(self):
        return self.classics_db.get_random()

    # ========== 在线导入 ==========
    def search_online_classics(self, keyword="", category="", source="auto", limit=30):
        return self.online_importer.search_online(keyword, category, limit)

    def download_and_import_items(self, selected_items_json):
        items = json.loads(selected_items_json)
        count = self.online_importer.download_and_import(items)
        return f"成功导入 {count} 篇"

    def download_dataset(self, dataset_name):
        return self.online_importer.download_dataset(dataset_name)

    def import_cache(self, dataset_name="", limit=None):
        return self.online_importer.import_cache(dataset_name, limit)

    def get_available_datasets(self):
        return [
            {"name": "唐诗", "description": "全唐诗精选", "size": "约 300KB"},
            {"name": "宋词", "description": "全宋词精选", "size": "约 240KB"},
            {"name": "论语", "description": "论语全文", "size": "约 50KB"},
            {"name": "诗经", "description": "诗经全文", "size": "约 200KB"},
            {"name": "楚辞", "description": "楚辞全文", "size": "约 100KB"}
        ]

    # ========== 作品管理 ==========
    def save_work(self, genre, style, topic, content):
        self.db.save(genre, json.dumps(style) if isinstance(style, dict) else style, topic, content)

    def search_works(self, keyword=""):
        return self.db.search(keyword)

    def delete_work(self, work_id):
        self.db.delete(int(work_id))

    def get_work_by_id(self, work_id):
        row = self.db.get_by_id(int(work_id))
        if row:
            return {"id": row[0], "genre": row[1], "style": row[2], "topic": row[3], "content": row[4], "time": row[5]}
        return None

    def save_journal(self, date, genre, topic, content, mood=""):
        self.db.save_journal(date, genre, topic, content, "", mood)

    def get_journals(self, limit=30):
        return self.db.get_journals(limit)

    # ========== 导出 ==========
    def export_txt(self, text):
        with open("output.txt", 'w', encoding='utf-8') as f:
            f.write(text)
        return os.path.abspath("output.txt")

    def export_image_api(self, text, font_size, bg_color, author):
        return export_image(text, output="output.png", font_size=font_size, bg_color=tuple(bg_color), author=author)

    def export_letter(self, text, author, seal):
        return export_letter_style(text, output="letter.png", author=author, seal_text=seal)

    def export_fan(self, text, author):
        return export_fan_style(text, output="fan.png", author=author)

    def export_couplet_img(self, upper, lower, horizontal):
        return export_couplet_style(upper, lower, horizontal, output="couplet.png")

    def export_spring(self, upper, lower, horizontal):
        return export_spring_couplet(upper, lower, horizontal, output="spring.png")

    def export_card(self, poem, title, author):
        return export_social_card(poem, title=title, author=author, output="social.png")

    # ========== 备份 ==========
    def create_backup(self):
        return self.backup_mgr.create()

    def restore_backup(self, path):
        return self.backup_mgr.restore(path)

    def list_backups(self):
        return self.backup_mgr.list_backups()

    # ========== 翻译 ==========
    def translate_poem(self, poem, target_lang):
        from poetry_translator import PoetryTranslator
        return PoetryTranslator(self.engine).translate(poem, target_lang)

    # ========== 画像 ==========
    def get_profile(self):
        from poet_profiler import PoetProfiler
        return PoetProfiler(self.db).generate()

    def get_random_topic(self):
        topics = [
            "雨后空山", "江南春晓", "边塞风雪", "秋夜寄北", "仗剑天涯",
            "月下独酌", "桃花源", "登高怀古", "故乡的河", "竹林听雨",
            "大漠孤烟", "海上明月", "雪中寻梅", "山居秋暝", "送别长亭",
            "诸子论道", "兰亭雅集", "赤壁怀古", "滕王高阁", "春江花月"
        ]
        return random.choice(topics)

    def close(self):
        self.db.close()
        self.classics_db.close()
        self.online_importer.close()


# ==================== HTML 界面 ====================
HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><title>心语 V6.6 · 文脉相承</title>
<style>
    :root { --bg:#f5f0e6; --text:#4e342e; --card:#fff; --menu-bg:#5d4037; --menu-text:#ffecb3; --border:#d7ccc8; --accent:#8d6e63; --font-size:14px; }
    .theme-dark { --bg:#1e1e1e; --text:#d4c5a9; --card:#2c2c2c; --menu-bg:#111; --menu-text:#d4c5a9; --border:#444; --accent:#a08060; }
    .theme-paper { --bg:#f5f0e6; --text:#3e2e1e; --card:#fffbf0; --menu-bg:#4a3628; --menu-text:#e8d5b0; --border:#c8b8a0; --accent:#7a5e4e; }
    * { box-sizing:border-box; margin:0; padding:0; }
    body { font-family:"Microsoft YaHei",sans-serif; background:var(--bg); color:var(--text); font-size:var(--font-size); transition:background 0.3s,color 0.3s; }
    .menubar { display:flex; background:var(--menu-bg); padding:0 8px; }
    .menu { position:relative; }
    .menu-btn { background:none; border:none; color:var(--menu-text); padding:8px 14px; cursor:pointer; }
    .menu-btn:hover { background:rgba(255,255,255,0.15); }
    .dropdown { display:none; position:absolute; background:var(--card); min-width:220px; box-shadow:0 4px 12px rgba(0,0,0,0.2); z-index:100; border-radius:0 0 6px 6px; max-height:500px; overflow-y:auto; }
    .dropdown a { display:block; padding:8px 16px; color:var(--text); text-decoration:none; cursor:pointer; }
    .dropdown a:hover { background:var(--border); }
    .menu:hover .dropdown { display:block; }
    .toolbar { display:flex; gap:8px; padding:10px; flex-wrap:wrap; align-items:center; }
    select, input, button { padding:6px 12px; border:1px solid var(--border); border-radius:4px; background:var(--card); color:var(--text); }
    button { background:var(--accent); color:#fff; cursor:pointer; border:none; }
    button:hover { opacity:0.85; }
    button:disabled { opacity:0.5; }
    input { flex:1; min-width:150px; }
    .result-card { background:var(--card); border:1px solid var(--border); padding:15px; white-space:pre-wrap; line-height:1.8; min-height:150px; margin:10px; position:relative; }
    .tabs { display:flex; gap:4px; margin:0 10px; }
    .tab-btn { background:var(--border); padding:6px 16px; border-radius:4px 4px 0 0; cursor:pointer; }
    .tab-btn.active { background:var(--accent); color:#fff; }
    .check-result { margin:8px 10px; padding:8px 12px; background:#fff8e1; border-left:4px solid #ff8f00; color:#bf360c; }
    .action-btns { display:flex; gap:6px; padding:10px; flex-wrap:wrap; }
    .hidden { display:none !important; }
    .status-bar { position:fixed; bottom:0; left:0; right:0; background:var(--menu-bg); color:var(--menu-text); text-align:center; padding:4px; font-size:12px; z-index:200; }
    .progress-bar { height:4px; background:var(--border); margin:0 10px; border-radius:2px; overflow:hidden; }
    .progress-fill { height:100%; background:var(--accent); width:0%; transition:width 0.3s; }
</style>
</head>
<body>

<div class="menubar">
    <div class="menu"><button class="menu-btn">文件</button>
        <div class="dropdown">
            <a onclick="exportTxt()">导出 TXT</a>
            <a onclick="exportImage()">导出图片</a>
            <a onclick="exportLetter()">信笺格式</a>
            <a onclick="exportFan()">扇面格式</a>
            <a onclick="exportCouplet()">对联格式</a>
            <a onclick="exportSpring()">春联格式</a>
            <a onclick="exportCard()">社交卡片</a>
            <hr><a onclick="saveWork()">保存作品</a>
            <a onclick="openWorks()">作品库</a>
            <a onclick="openJournals()">创作手札</a>
            <hr><a onclick="createBackup()">创建备份</a>
            <a onclick="restoreBackup()">恢复备份</a>
        </div>
    </div>
    <div class="menu"><button class="menu-btn">创作</button>
        <div class="dropdown">
            <a onclick="randomTopic()">随机主题</a>
            <a onclick="continueMode()">智能续写</a>
            <a onclick="createCento()">集句创作</a>
            <a onclick="generateCouplet()">自动对联</a>
            <a onclick="poemResponse()">诗词唱和</a>
            <hr><a onclick="critiqueWork()">AI 品评</a>
            <a onclick="translateWork()">翻译</a>
        </div>
    </div>
    <div class="menu"><button class="menu-btn">经典</button>
        <div class="dropdown">
            <a onclick="browseClassics('经部')">经部（四书五经）</a>
            <a onclick="browseClassics('史部')">史部（历史典籍）</a>
            <a onclick="browseClassics('子部')">子部（诸子百家）</a>
            <a onclick="browseClassics('集部')">集部（诗文总集）</a>
            <a onclick="browseClassics('蒙学')">蒙学（启蒙经典）</a>
            <hr><a onclick="browseClassics('唐诗')">唐诗</a>
            <a onclick="browseClassics('宋词')">宋词</a>
            <a onclick="browseClassics('经典散文')">经典散文</a>
            <hr><a onclick="advancedSearch()">高级检索</a>
            <a onclick="showStats()">文库统计</a>
            <a onclick="dailyRecommend()">每日推荐</a>
            <a onclick="showFavorites()">我的收藏</a>
            <hr><a onclick="categoryBrowse()">分类浏览</a>
            <a onclick="searchOnline()">在线搜索古典</a>
            <a onclick="showDatasets()">下载数据集</a>
            <a onclick="importFromCache()">从缓存导入</a>
        </div>
    </div>
    <div class="menu"><button class="menu-btn">查看</button>
        <div class="dropdown">
            <a onclick="showProfile()">创作画像</a>
            <hr><a onclick="setTheme('light')">浅色</a>
            <a onclick="setTheme('dark')">深色</a>
            <a onclick="setTheme('paper')">宣纸</a>
            <hr><a onclick="changeFontSize(1)">放大</a>
            <a onclick="changeFontSize(-1)">缩小</a>
        </div>
    </div>
    <div class="menu"><button class="menu-btn">帮助</button>
        <div class="dropdown">
            <a onclick="about()">关于心语</a>
            <a onclick="startTutorial()">新手教程</a>
            <a onclick="showShortcuts()">快捷键</a>
        </div>
    </div>
</div>

<div class="toolbar">
    <select id="modeSelect" onchange="switchEngine()">
        <option value="online">在线引擎</option>
        <option value="offline">离线引擎</option>
    </select>
    <select id="genreSelect" onchange="updateStyles()">
        <option>五言绝句</option><option>七言绝句</option>
        <option>五言律诗</option><option>七言律诗</option>
        <option>如梦令</option><option>蝶恋花</option>
        <option>现代歌词</option><option>中国风歌词</option>
        <option>抒情散文</option><option>哲思小品</option>
    </select>
    <select id="styleSelect"></select>
    <input id="topicInput" placeholder="主题，如：秋夜">
    <button onclick="randomTopic()">🎲</button>
    <button id="generateBtn" onclick="generate()">生成</button>
    <button onclick="speakCurrent()">🔊</button>
</div>

<div class="progress-bar hidden" id="progressBar"><div class="progress-fill" id="progressFill"></div></div>
<div class="tabs" id="tabs"></div>
<div class="result-card" id="resultCard">点击"生成"开始创作...</div>
<div class="check-result hidden" id="checkResult"></div>
<div class="action-btns">
    <button onclick="exportTxt()">导出TXT</button>
    <button onclick="exportImage()">导出图片</button>
    <button onclick="exportLetter()">信笺</button>
    <button onclick="saveWork()">保存</button>
    <button onclick="copyResult()">复制</button>
    <button onclick="critiqueWork()">品评</button>
</div>
<div class="status-bar" id="statusBar">就绪 | 心语 V6.6 · 文脉相承</div>

<script>
let currentResults=[], currentGenre="五言绝句", activeTab=0, typingTimer=null;

window.addEventListener('load',async()=>{
    await updateStyles();
    setTheme(localStorage.getItem('theme')||'paper');
    let fs=localStorage.getItem('fontSize')||'1';
    document.documentElement.style.setProperty('--font-size',(14*parseFloat(fs))+'px');
    if(!localStorage.getItem('tutorial_done')) setTimeout(startTutorial,800);
    document.addEventListener('keydown',handleShortcut);
});

function setTheme(t){document.body.className=t?'theme-'+t:'';localStorage.setItem('theme',t||'paper');}
function changeFontSize(d){let c=parseFloat(localStorage.getItem('fontSize')||'1'),n=Math.max(0.8,Math.min(2,c+d*0.1));localStorage.setItem('fontSize',n);document.documentElement.style.setProperty('--font-size',(14*n)+'px');}
async function switchEngine(){let m=document.getElementById('modeSelect').value;showStatus(await pywebview.api.set_engine(m));}
async function updateStyles(){let g=document.getElementById('genreSelect').value;currentGenre=g;let s=await pywebview.api.get_styles(g),sel=document.getElementById('styleSelect');sel.innerHTML='<option value="">默认风格</option>';s.forEach(x=>{let o=document.createElement('option');o.value=JSON.stringify(x);o.text=x.label;sel.appendChild(o);});}

async function generate(){
    let topic=document.getElementById('topicInput').value.trim();
    if(!topic){topic=await pywebview.api.get_random_topic();document.getElementById('topicInput').value=topic;}
    let sv=document.getElementById('styleSelect').value,si=sv?JSON.parse(sv):null;
    let btn=document.getElementById('generateBtn');btn.disabled=true;btn.textContent='生成中...';
    let bar=document.getElementById('progressBar'),fill=document.getElementById('progressFill');
    bar.classList.remove('hidden');fill.style.width='0%';
    showStatus('正在创作...');
    let progress=0,interval=setInterval(()=>{progress+=10;if(progress<=90)fill.style.width=progress+'%';},200);
    try{
        let results=await pywebview.api.generate(currentGenre,topic,si);
        clearInterval(interval);fill.style.width='100%';
        if(!Array.isArray(results))results=[results];
        currentResults=results;activeTab=0;renderTabs();
        typewriterEffect(results[0]);
        if(currentGenre.includes('绝句')||currentGenre.includes('律诗')||currentGenre.includes('如梦令')){
            let check=await pywebview.api.check_poem(results[0],currentGenre);
            document.getElementById('checkResult').classList.remove('hidden');
            document.getElementById('checkResult').innerHTML='<b>格律检测：</b>'+(Array.isArray(check)?check.join('<br>'):check);
        }else{document.getElementById('checkResult').classList.add('hidden');}
        showStatus('生成完毕');
    }catch(e){showStatus('生成失败: '+e);}
    btn.disabled=false;btn.textContent='生成';
    setTimeout(()=>bar.classList.add('hidden'),500);
}

function typewriterEffect(text){
    let card=document.getElementById('resultCard');
    card.textContent='';let i=0;
    clearInterval(typingTimer);
    typingTimer=setInterval(()=>{if(i<text.length){card.textContent+=text.charAt(i);i++;}else clearInterval(typingTimer);},10);
}

function renderTabs(){
    let td=document.getElementById('tabs');td.innerHTML='';
    for(let i=0;i<currentResults.length;i++){
        let b=document.createElement('button');b.className='tab-btn'+(i===activeTab?' active':'');
        b.textContent='候选 '+(i+1);b.onclick=()=>{activeTab=i;renderTabs();typewriterEffect(currentResults[activeTab]);};
        td.appendChild(b);
    }
}

function showStatus(m){document.getElementById('statusBar').textContent=m;}

async function exportTxt(){if(!currentResults.length)return;showStatus('已导出: '+await pywebview.api.export_txt(currentResults[activeTab]));}
async function exportImage(){if(!currentResults.length)return;showStatus('已导出: '+await pywebview.api.export_image_api(currentResults[activeTab],24,[255,250,240],''));}
async function exportLetter(){if(!currentResults.length)return;showStatus('已导出: '+await pywebview.api.export_letter(currentResults[activeTab],'','心语'));}
async function exportFan(){if(!currentResults.length)return;showStatus('已导出: '+await pywebview.api.export_fan(currentResults[activeTab],''));}
async function exportCouplet(){if(!currentResults.length)return;let u=prompt('上联：',currentResults[activeTab]),l=prompt('下联：',''),h=prompt('横批：','');if(u&&l)showStatus('已导出: '+await pywebview.api.export_couplet_img(u,l,h));}
async function exportSpring(){if(!currentResults.length)return;let u=prompt('上联：',currentResults[activeTab]),l=prompt('下联：',''),h=prompt('横批：','');if(u&&l)showStatus('已导出: '+await pywebview.api.export_spring(u,l,h));}
async function exportCard(){if(!currentResults.length)return;showStatus('已导出: '+await pywebview.api.export_card(currentResults[activeTab],'',''));}

async function saveWork(){if(!currentResults.length)return;let sv=document.getElementById('styleSelect').value,si=sv?JSON.parse(sv):null,topic=document.getElementById('topicInput').value;await pywebview.api.save_work(currentGenre,si,topic,currentResults[activeTab]);showStatus('已保存');}
function copyResult(){if(!currentResults.length)return;navigator.clipboard.writeText(currentResults[activeTab]);showStatus('已复制');}
async function randomTopic(){document.getElementById('topicInput').value=await pywebview.api.get_random_topic();}
function speakCurrent(){if(!currentResults.length)return;let u=new SpeechSynthesisUtterance(currentResults[activeTab]);u.lang='zh-CN';u.rate=0.8;window.speechSynthesis.speak(u);}

async function critiqueWork(){if(!currentResults.length)return;alert(await pywebview.api.critique(currentResults[activeTab],currentGenre));}
async function translateWork(){if(!currentResults.length)return;alert(await pywebview.api.translate_poem(currentResults[activeTab],'en'));}
function continueMode(){if(!currentResults.length)return;let l=prompt('输入诗句：','');if(l)pywebview.api.smart_continue(l).then(r=>alert(r.map(x=>`【${x.direction}】\n${x.full_poem}`).join('\n\n')));}
async function createCento(){let kw=prompt('集句主题：','');if(kw)alert(await pywebview.api.create_cento(kw));}
async function generateCouplet(){let u=prompt('上联（留空自动生成）：','');alert(await pywebview.api.generate_couplet(u));}
async function poemResponse(){if(!currentResults.length)return;alert(await pywebview.api.poem_response(currentResults[activeTab]));}

async function browseClassics(cat){
    let results=await pywebview.api.search_classics_v2('',cat,'','',5000);
    if(!results.length){alert('「'+cat+'」暂无数据');return;}
    showClassicList(results,cat);
}

function showClassicList(results,title){
    let total = results.length;
    let pageSize = 20;
    let totalPages = Math.ceil(total / pageSize);
    let currentPage = 0;
    
    function showPage(page) {
        currentPage = page;
        let start = page * pageSize;
        let end = Math.min(start + pageSize, total);
        let items = results.slice(start, end);
        let msg = '📚 ' + (title||'检索结果') + '（共' + total + '篇，第' + (page+1) + '/' + totalPages + '页）\n\n';
        msg += items.map((x,i) => (start+i+1) + '.' + (x.is_famous?'⭐':'') + '《' + x.title + '》 ' + x.author + '（' + x.dynasty + '）').join('\n');
        msg += '\n\n【操作】输入数字查看详情 | N下一页 | P上一页 | J跳转页码 | 0返回菜单';
        let input = prompt(msg, '');
        if (input === '0' || input === null) return;
        if (input === 'N' || input === 'n') { if (page+1 < totalPages) showPage(page+1); else showPage(page); }
        else if (input === 'P' || input === 'p') { if (page > 0) showPage(page-1); else showPage(page); }
        else if (input === 'J' || input === 'j') {
            let p = prompt('输入页码（1-' + totalPages + '）：', '');
            if (p && parseInt(p) >= 1 && parseInt(p) <= totalPages) showPage(parseInt(p)-1);
            else showPage(page);
        }
        else if (parseInt(input) >= 1 && parseInt(input) <= total) {
            let item = results[parseInt(input)-1];
            if (item) showClassicDetail(item);
        }
        else { showPage(page); }
    }
    showPage(0);
}

async function showClassicDetail(item){
    await pywebview.api.record_classic_read(item.id);
    let detail='《'+item.title+'》\n作者：'+item.author+'（'+item.dynasty+'）\n分类：'+item.category+'\n字数：'+item.char_count+'\n\n原文：\n'+item.content+'\n\n注释：'+(item.annotation||'暂无');
    alert(detail);
    let actions=['朗读原文','AI深度赏析','添加笔记','收藏','以此为范本创作','翻译为英文'];
    let action=prompt('请选择操作：\n\n'+actions.map((a,i)=>(i+1)+'. '+a).join('\n'),'1');
    if(action==='1'){let u=new SpeechSynthesisUtterance(item.content);u.lang='zh-CN';u.rate=0.7;window.speechSynthesis.speak(u);showStatus('正在朗读《'+item.title+'》');}
    else if(action==='2'){showStatus('正在生成赏析...');let analysis=await pywebview.api.allusion_deep_dive(item.title);alert('AI赏析：《'+item.title+'》\n\n'+analysis);}
    else if(action==='3'){let note=prompt('请输入笔记：','');if(note){await pywebview.api.add_classic_note(item.id,note);showStatus('笔记已保存');}}
    else if(action==='4'){await pywebview.api.add_favorite(item.id);showStatus('已收藏');}
    else if(action==='5'){document.getElementById('topicInput').value=item.title;showStatus('已设置主题为「'+item.title+'」，点击生成开始创作');}
    else if(action==='6'){let translation=await pywebview.api.translate_poem(item.content,'en');alert('英文翻译：\n\n'+translation);}
}

async function advancedSearch(){
    let kw=prompt('关键词：','')||'';
    let cats=await pywebview.api.get_classic_categories_v2();
    let catMsg=cats.map((c,i)=>(i+1)+'. '+c.category+'（'+c.count+'篇）').join('\n');
    let catIdx=prompt('选择分类（0=全部）：\n\n'+catMsg,'0');
    let category=catIdx&&parseInt(catIdx)>0?cats[parseInt(catIdx)-1].category:'';
    let dynasty=prompt('朝代（回车跳过）：','')||'';
    let author=prompt('作者（回车跳过）：','')||'';
    let results=await pywebview.api.search_classics_v2(kw,category,dynasty,author,100);
    if(!results.length){alert('未找到匹配结果');return;}
    showClassicList(results,'高级检索结果');
}

async function showStats(){let stats=await pywebview.api.get_classic_stats();let msg='古典文库统计\n\n总篇数：'+stats.total+'\n总字数：'+stats.total_chars.toLocaleString()+'\n\n分类统计：\n';msg+=stats.categories.map(c=>'  '+c.category+'：'+c.count+'篇').join('\n');msg+='\n\n朝代统计：\n';msg+=stats.dynasties.map(d=>'  '+d.dynasty+'：'+d.count+'篇').join('\n');alert(msg);}
async function dailyRecommend(){let item=await pywebview.api.get_random_classic();if(item)showClassicDetail(item);}
async function showFavorites(){let results=await pywebview.api.get_favorites();if(!results.length){alert('收藏夹为空');return;}showClassicList(results,'我的收藏');}
async function categoryBrowse(){
    let cats=await pywebview.api.get_classic_categories_v2();
    let dynasties=await pywebview.api.get_classic_dynasties_v2();
    let msg="【时代】\n"+dynasties.map(d=>d.dynasty).join(" | ");
    msg+="\n\n【分类】\n"+cats.map(c=>c.category).join(" | ");
    msg+="\n\n输入筛选条件（如：唐 诗）：";
    let kw=prompt(msg,"");
    if(!kw) return;
    let parts=kw.split(" ");
    let dynasty=parts.find(p=>dynasties.some(d=>d.dynasty===p))||"";
    let category=parts.find(p=>cats.some(c=>c.category===p))||"";
    let results=await pywebview.api.search_classics_v2("",category,dynasty,"",200);
    if(!results.length){alert("无匹配结果");return;}
    showClassicList(results,"筛选结果");
}
async function searchOnline(){
    let kw=prompt('输入关键词搜索古典文献：','')||'';
    let cat=prompt('分类（唐诗/宋词/论语/诗经/楚辞，回车搜索全部）：','')||'';
    showStatus('正在在线搜索...');
    let results=await pywebview.api.search_online_classics(kw,cat,'auto',50);
    if(!results.length){alert('未找到匹配结果');return;}
    showOnlineResults(results);
}

function showOnlineResults(results){
    let msg='搜索结果（共'+results.length+'篇）：\n\n';
    msg+=results.map((x,i)=>(i+1)+'.《'+x.title+'》 '+x.author+'（'+x.dynasty+'）').join('\n');
    msg+='\n\nA. 导入全部  B. 选择导入  C. 取消';
    let action=prompt(msg,'B');
    if(action==='A'||action==='a'){pywebview.api.download_and_import_items(JSON.stringify(results)).then(m=>showStatus(m));}
    else if(action==='B'||action==='b'){let indices=prompt('输入序号（逗号分隔）：','');if(indices){let selected=indices.split(',').map(i=>results[parseInt(i.trim())-1]).filter(x=>x);pywebview.api.download_and_import_items(JSON.stringify(selected)).then(m=>showStatus(m));}}
}

async function showDatasets(){
    let datasets=await pywebview.api.get_available_datasets();
    let msg='可下载数据集：\n\n'+datasets.map((d,i)=>(i+1)+'. '+d.name+'（'+d.description+'，'+d.size+'）').join('\n');
    let choice=prompt(msg+'\n\n输入序号下载：','');
    if(choice&&parseInt(choice)>0){
        let ds=datasets[parseInt(choice)-1];
        showStatus('正在下载「'+ds.name+'」...');
        let result=await pywebview.api.download_dataset(ds.name);
        if(result.success){alert('下载成功！\n数据集：'+ds.name+'\n篇数：'+result.count+'\n大小：'+result.file_size+'\n请使用「从缓存导入」导入到数据库');}
        else{alert('下载失败：'+(result.error||'未知错误'));}
    }
}

async function importFromCache(){
    let ds=prompt('数据集名称（唐诗/宋词/论语/诗经/楚辞，回车全部）：','');
    let limit=prompt('导入数量（回车全部）：','');
    showStatus('正在导入...');
    let result=await pywebview.api.import_cache(ds||'',limit?parseInt(limit):null);
    alert('导入完成！共 '+result.imported+' 篇');
    showStatus('已导入 '+result.imported+' 篇');
}

async function openWorks(){let w=await pywebview.api.search_works();if(!w.length){alert('作品库为空');return;}alert('最近作品：\n\n'+w.slice(0,8).map((x,i)=>(i+1)+'. ['+x[1]+'] '+x[3]+'\n'+x[4].substring(0,40)+'...').join('\n\n'));}
async function openJournals(){let j=await pywebview.api.get_journals();if(!j.length){alert('创作手札为空');return;}alert('创作手札：\n\n'+j.slice(0,10).map(x=>'['+x[2]+'] '+x[3]+'\n'+x[4].substring(0,40)+'...').join('\n\n'));}
async function createBackup(){showStatus('备份已创建: '+await pywebview.api.create_backup());}
async function restoreBackup(){let p=prompt('输入备份文件路径：','');if(p){await pywebview.api.restore_backup(p);showStatus('已恢复');}}
async function showProfile(){let p=await pywebview.api.get_profile();if(!p){alert('暂无数据');return;}alert('创作画像\n\n总作品: '+p.total_works+'\n总字数: '+p.total_chars+'\n最爱主题: '+(p.favorite_topics?.[0]?.[0]||'无'));}

function startTutorial(){alert('新手教程\n\n欢迎使用心语！\n\n1. 选择体裁和风格\n2. 输入主题\n3. 点击生成\n4. 导出分享\n\n祝你创作愉快！');localStorage.setItem('tutorial_done','1');}
function handleShortcut(e){if(e.ctrlKey&&e.key==='Enter'){e.preventDefault();generate();}if(e.ctrlKey&&e.key==='s'){e.preventDefault();saveWork();}if(e.ctrlKey&&e.key==='n'){e.preventDefault();randomTopic();}}
function showShortcuts(){alert('快捷键\n\nCtrl+Enter 生成\nCtrl+S 保存\nCtrl+N 随机主题');}
function about(){alert('心语 V6.6 · 文脉相承\n古典诗词 AI 工作站\n秦汉唐宋，诸子百家\n开发者：hedongwei\n邮箱：1265338136@qq.com\nAI引擎：DeepSeek');}
</script>
</body>
</html>"""

if __name__ == '__main__':
    api = API()
    window = webview.create_window('心语 V6.6', html=HTML, js_api=api, width=1100, height=750)
    webview.start()
    api.close()