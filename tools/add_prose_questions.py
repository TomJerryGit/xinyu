# -*- coding: utf-8 -*-
"""为新增 20 篇古文补逐篇理解/分析题，写入已审核题库。

用法：python tools/add_prose_questions.py --apply
"""
import argparse
import json
import os
import sqlite3

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "classics.db")

UNDERSTANDING = [
    ("prose_curated_001", "理解", "“静以修身，俭以养德”中的“静”“俭”分别指什么？这句话在文中有什么作用？",
     "静指宁静专一，俭指节俭。这句话提出修身养德的两个根本，总领下文的学习、立志与惜时。"),
    ("prose_curated_002", "分析", "文章开头列举六位历史人物，有什么共同点？作用是什么？",
     "他们都出身卑微或经历磨难，后来被任用。作为事实论据，引出“生于忧患”的观点，增强说服力。"),
    ("prose_curated_003", "分析", "本文的中心论点是什么？作者从哪两个层面论证？",
     "中心论点是“天时不如地利，地利不如人和”。先以攻城、守城说明地利不如人和，再从“域民、固国、威天下”说明得道多助。"),
    ("prose_curated_004", "分析", "孟子如何反驳景春对“大丈夫”的判断？",
     "先反问“是焉得为大丈夫乎”，指出公孙衍、张仪顺从君王只是“妾妇之道”；再正面提出居广居、立正位、行大道，以及富贵、贫贱、威武“三不能”。"),
    ("prose_curated_005", "分析", "鲲鹏形象用了什么手法？有什么作用？",
     "用夸张和想象极写鲲鹏之大、飞之高远，营造雄奇开阔的意境，象征自由与宏大的精神境界。"),
    ("prose_curated_006", "分析", "文章怎样一步步推出“教学相长”的观点？",
     "以嘉肴、至道类比，说明不学不知其善；再指出学然后知不足、教然后知困；知不足能自反、知困能自强，所以教与学互相促进。"),
    ("prose_curated_007", "理解", "大同社会有哪些基本特征？请用原文概括。",
     "天下为公、选贤与能、讲信修睦；老有所终、壮有所用、幼有所长，矜寡孤独废疾者皆有所养；货不必藏于己，力不必为己；谋闭不兴、盗窃不作、外户不闭。"),
    ("prose_curated_008", "分析", "两小儿各自的依据是什么？这个故事说明什么？",
     "一儿以视觉大小判断远近，一儿以温度冷暖判断远近。说明认识受角度和条件限制，也表现孔子实事求是、不妄断。"),
    ("prose_curated_009", "分析", "“撒盐空中”和“柳絮因风起”两个比喻各有什么特点？作者更倾向哪一个？",
     "撒盐重形似，写雪的白和重；柳絮重神似，写雪的轻盈飘逸。作者以“大笑乐”和补叙谢道韫，倾向“柳絮因风起”。"),
    ("prose_curated_010", "分析", "元方从哪两个角度反驳友人？这样说的力量在哪里？",
     "从“无信”（期日中不至）和“无礼”（对子骂父）两个角度反驳；以对方的行为直接指出矛盾，简洁有力。"),
    ("prose_curated_011", "分析", "传言为什么会失真？这个故事给什么启示？",
     "丁氏“得一人之使”被省略、误传为“得一人”，经多人转述后变形。启示是听取传闻要核实，不能以讹传讹。"),
    ("prose_curated_012", "分析", "卖油翁怎样用行动说明“手熟”？文章对比有什么作用？",
     "他把钱盖在葫芦口上，用勺酌油沥入而钱不湿。与陈尧咨的自矜形成对比，突出熟能生巧、谦逊的道理。"),
    ("prose_curated_013", "分析", "吕蒙的进步是从谁的角度写出的？有什么作用？",
     "从鲁肃“大惊”“非复吴下阿蒙”的侧面写出。侧面烘托吕蒙学有所成，突出孙权劝学的效果。"),
    ("prose_curated_014", "分析", "讲学家和老河兵寻找石兽的方法有何不同？故事说明什么？",
     "讲学家主张在原地深挖，老河兵主张到上游找，因为反激水流会冲刷坎穴使石兽逆流翻转。说明不能只凭常理主观臆断，要实践并全面分析。"),
    ("prose_curated_015", "分析", "文章用霸上、棘门军与细柳军对比，作用是什么？",
     "霸上、棘门军纪松弛，细柳军军纪严明；对比突出周亚夫治军有方，塑造“真将军”形象。"),
    ("prose_curated_016", "理解", "作者从哪些角度写石门山？表达了什么情感？",
     "视觉写森壁、孤峰、幽岫、深溪，听觉写蝉吟、鹤唳、水响、猿啼；写幽静美景，表达归隐山水之乐。"),
    ("prose_curated_017", "分析", "右溪美景无人赏爱，作者为什么“怅然”？寄托了什么？",
     "美景被埋没，触发人才不遇的感慨；借右溪寄托怀才不遇、希望被发现赏识的情怀。"),
    ("prose_curated_018", "分析", "作者登西山后为什么说“游于是乎始”？",
     "此前游山水只是外观，登西山后见天地广阔，心神与万物融合，获得精神解脱，才真正懂得游赏。"),
    ("prose_curated_019", "分析", "文章借墨池说明什么道理？属于什么写法？",
     "借王羲之临池学书说明书法成就来自勤学，不是天成；借事说理、叙议结合，勉励学者深造。"),
    ("prose_curated_020", "分析", "“病梅”象征什么？作者“疗梅”表达了什么？",
     "病梅象征被束缚、扭曲的人才；疗梅表达解放人才、顺其自然、反抗束缚的愿望，属于托物言志。"),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        print("would_insert", len(UNDERSTANDING))
        return
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    count = 0
    for idx, (cid, cognitive, question, answer) in enumerate(UNDERSTANDING, 1):
        work = conn.execute("SELECT title,category,dynasty FROM classics WHERE id=?", (cid,)).fetchone()
        if not work:
            continue
        rubric = ([{"dimension": "信息准确", "points": 60, "criteria": "覆盖原文关键信息"},
                   {"dimension": "语言表达", "points": 40, "criteria": "通顺、完整"}]
                  if cognitive == "理解" else
                  [{"dimension": "观点明确", "points": 30, "criteria": "准确概括"},
                   {"dimension": "原文依据", "points": 40, "criteria": "引用词句并说明"},
                   {"dimension": "分析深度", "points": 30, "criteria": "说明手法/结构/情感"}])
        conn.execute(
            """INSERT OR REPLACE INTO question_bank
               (id,classic_id,category,dynasty,difficulty,type,question,options,answer,explanation,
                cognitive,rubric,source,verified)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'reviewed',1)""",
            (f"prose_q_{idx:02d}", cid, work["category"], work["dynasty"], 2, "简答",
             question, "[]", answer, "开放题，按量规人工评分。", cognitive,
             json.dumps(rubric, ensure_ascii=False)),
        )
        count += 1
    conn.commit()
    conn.close()
    print("inserted", count)


if __name__ == "__main__":
    main()
