# -*- coding: utf-8 -*-
"""风格管理器：体裁提示词与诗人风格库。

风格条目统一包含 ``label / poet / instruction / examples``，
前端下拉框直接消费这些字段，避免"下拉里有李白、提示词里却没有"。
"""
import json
import os

from utils import app_path

GENRE_PROMPTS = {
    "五言绝句": "写一首五言绝句，语言凝练，意境深远，严格遵循平仄。禁止现代词汇。",
    "七言绝句": "写一首七言绝句，讲究平仄，意象生动。禁止现代词汇。",
    "五言律诗": "写一首五言律诗，共八句，中间两联对仗，严格遵循平仄。",
    "七言律诗": "写一首七言律诗，共八句，中间两联对仗，严格遵循平仄。",
    "如梦令": "填一首《如梦令》，三十三字，仄韵，含蓄典雅。",
    "蝶恋花": "填一首《蝶恋花》，六十字，上下片各五句四仄韵。",
    "现代歌词": "写一首主歌+副歌结构的歌词，押韵流畅，段落对称。",
    "中国风歌词": "写一首中国风歌词，融入古典意象，段落整齐。",
    "抒情散文": "写一篇约300字抒情散文，文字优美，注重描写。",
    "哲思小品": "写一篇约200字哲理小品，言浅意深。",
    "写景游记": "写一篇约250字写景游记，情景交融。",
}

STYLES = {
    "诗词": [
        {
            "label": "盛唐·浪漫（李白）",
            "dynasty": "盛唐",
            "school": "浪漫主义",
            "poet": "李白",
            "instruction": "你是李白，想象奇崛、气势奔放，善用夸张与明月、酒、剑等意象。",
            "examples": ["君不见黄河之水天上来，奔流到海不复回。", "举杯邀明月，对影成三人。"],
        },
        {
            "label": "盛唐·沉郁（杜甫）",
            "dynasty": "盛唐",
            "school": "现实主义",
            "poet": "杜甫",
            "instruction": "你是杜甫，格律严谨、沉郁顿挫，关注家国与民生。",
            "examples": ["无边落木萧萧下，不尽长江滚滚来。", "朱门酒肉臭，路有冻死骨。"],
        },
        {
            "label": "盛唐·山水田园（王维）",
            "dynasty": "盛唐",
            "school": "山水田园",
            "poet": "王维",
            "instruction": "你是王维，隐居辋川，诗中有画，空灵禅意。",
            "examples": ["空山新雨后，天气晚来秋。", "明月松间照，清泉石上流。"],
        },
        {
            "label": "盛唐·边塞（岑参）",
            "dynasty": "盛唐",
            "school": "边塞诗",
            "poet": "岑参",
            "instruction": "你是岑参，诗风雄奇壮阔，多写大漠风沙与边塞苦寒。",
            "examples": ["北风卷地白草折，胡天八月即飞雪。"],
        },
        {
            "label": "两宋·婉约（李清照）",
            "dynasty": "两宋",
            "school": "婉约词",
            "poet": "李清照",
            "instruction": "你是李清照，词风婉约细腻，善以日常物象写深沉情感。",
            "examples": ["寻寻觅觅，冷冷清清，凄凄惨惨戚戚。"],
        },
        {
            "label": "两宋·豪放（苏轼）",
            "dynasty": "两宋",
            "school": "豪放词",
            "poet": "苏轼",
            "instruction": "你是苏轼，旷达超逸，词风豪放，善将人生感慨化入自然。",
            "examples": ["大江东去，浪淘尽，千古风流人物。", "一蓑烟雨任平生。"],
        },
    ],
    "歌词": [
        {
            "label": "流行情歌（林夕风格）",
            "style": "流行情歌",
            "instruction": "你是林夕，细腻描写情感，韵律流畅，善用意象叠加。",
            "examples": ["有生之年，狭路相逢，终不能幸免。"],
        },
        {
            "label": "中国风（方文山风格）",
            "style": "中国风",
            "instruction": "你是方文山，融合古典意象与现代语法，画面感强。",
            "examples": ["素胚勾勒出青花笔锋浓转淡。"],
        },
    ],
    "散文": [
        {
            "label": "古典文言（归有光风格）",
            "style": "文言散文",
            "instruction": "你是归有光，文笔简洁有韵味，善写日常琐事中的深情。",
            "examples": ["项脊轩，旧南阁子也。"],
        },
        {
            "label": "现代典雅（朱自清风格）",
            "style": "现代散文",
            "instruction": "你是朱自清，文笔优美流畅，长于写景与抒情。",
            "examples": ["月光如流水一般，静静地泻在这一片叶子和花上。"],
        },
    ],
}


class StyleManager:
    def __init__(self):
        self.genres = GENRE_PROMPTS
        self.custom_styles = self._load_custom()

    @staticmethod
    def _load_custom():
        path = app_path("data", "user_styles.json")
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def save_custom(self):
        path = app_path("data", "user_styles.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.custom_styles, handle, ensure_ascii=False, indent=2)

    def get_genres(self):
        return list(self.genres.keys())

    def get_styles_for_genre(self, genre):
        genre = str(genre or "")
        if "绝句" in genre or "律诗" in genre or "词" in genre:
            key = "诗词"
        elif "歌词" in genre:
            key = "歌词"
        elif any(word in genre for word in ("散文", "小品", "游记")):
            key = "散文"
        else:
            key = ""
        styles = list(STYLES.get(key, [])) if key else []
        styles.extend(self.custom_styles.get(genre, []))
        return styles

    def build_prompt(self, genre, topic, style_info):
        base = self.genres.get(genre, "请创作。")
        style_desc = ""
        if isinstance(style_info, dict):
            instruction = style_info.get("instruction", "")
            if instruction:
                style_desc = f"【角色】{instruction}\n"
            examples = style_info.get("examples") or []
            if isinstance(examples, str):
                examples = [examples]
            if examples:
                style_desc += f"【范例】{examples[0]}\n"
        elif style_info:
            style_desc = f"【风格】{style_info}\n"

        prompt = f"{style_desc}【任务】{base}\n【主题】{topic or '秋夜'}\n"
        if "绝句" in genre or "律诗" in genre or "词" in genre:
            prompt += "【硬性要求】禁止现代词汇与网络用语；必须合平仄，押同一韵部。\n"
        prompt += "作品："
        return prompt
