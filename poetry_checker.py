# -*- coding: utf-8 -*-
"""平水韵格律检测（近似实现）。

说明：
* 以《平水韵》常用入声字表 + 普通话声调反推平仄，多音字无法完全还原；
* 五/七言绝句用四句式平仄模板，律诗用八句式模板；
* 词牌格律差异大，当前版本不做自动判定，明确返回"需人工核对"，
  不再返回容易误导用户的"已就绪"。
"""
import re

from pypinyin import Style, pinyin

# 常用入声字（平水韵入声，普通话多读阴平/阳平/去声，易被误判为平声）
RUSHENG = set(
    "一七八十百白薄雹剥驳伯拨别出吃答读乏佛国黑忽急决绝觉哭乐六绿落麦密木拍切却热日十石失湿实说压鸭约月窄竹逐烛足族昨折"
    "及吉极级急集疾嫉籍藉击激积迹绩寂即亟革隔格阁各恶鄂萼遏握渥屋沃兀物勿屈曲局菊掬鞠橘觉角脚觉爵嚼"
    "甲夹颊荚铗劫接节杰竭截洁结拮捷睫揭羯碣竭桀孑讦劫")
RUSHENG |= set(
    "学雪血削薛穴雪谑岳乐药钥跃阅悦越粤月钺刖玥"
    "福幅辐蝠复腹覆蝮馥服伏茯袱绂绋弗拂佛"
    "达答搭沓踏榻塌塔獭闼挞"
    "杀刹煞刷率蟀帅"
    "发法伐筏阀罚"
    "合盒盍阖嗑喝褐鹤壑"
    "察擦插锸"
    "直值植殖执职织汁质窒炙"
    "食蚀识实石拾十什"
    "鼻笔必毕弼壁璧碧"
    "匹辟僻癖劈霹"
    "的滴嫡敌狄迪笛籴"
    "立粒笠栗历力沥雳"
    "骨谷毂哭窟"
    "曲屈诎"
    "托脱橐"
    "作昨凿"
    "索塞色"
)

# 平仄模板：0=平，1=仄，-1=可平可仄（一三五不论）
# 每个元素是一种"起式"的四句模板，律诗则复用两遍。
WUJUE_PATTERNS = [
    # 仄起首句不入韵：仄仄平平仄，平平仄仄平。平平平仄仄，仄仄仄平平。
    [[-1, 1, -1, 0, 1], [-1, 0, -1, 1, 0], [-1, 0, -1, 1, 1], [-1, 1, -1, 0, 0]],
    # 仄起首句入韵：仄仄仄平平，平平仄仄平。平平平仄仄，仄仄仄平平。
    [[-1, 1, -1, 0, 0], [-1, 0, -1, 1, 0], [-1, 0, -1, 1, 1], [-1, 1, -1, 0, 0]],
    # 平起首句不入韵：平平平仄仄，仄仄仄平平。仄仄平平仄，平平仄仄平。
    [[-1, 0, -1, 1, 1], [-1, 1, -1, 0, 0], [-1, 1, -1, 0, 1], [-1, 0, -1, 1, 0]],
    # 平起首句入韵：平平仄仄平，仄仄仄平平。仄仄平平仄，平平仄仄平。
    [[-1, 0, -1, 1, 0], [-1, 1, -1, 0, 0], [-1, 1, -1, 0, 1], [-1, 0, -1, 1, 0]],
]
QIJUE_PATTERNS = [
    # 仄起首句不入韵
    [[-1, 1, -1, 0, -1, 1, 1], [-1, 0, -1, 1, -1, 0, 0], [-1, 0, -1, 1, -1, 0, 1], [-1, 1, -1, 0, -1, 1, 0]],
    # 仄起首句入韵
    [[-1, 1, -1, 0, -1, 1, 0], [-1, 0, -1, 1, -1, 0, 0], [-1, 0, -1, 1, -1, 0, 1], [-1, 1, -1, 0, -1, 1, 0]],
    # 平起首句不入韵
    [[-1, 0, -1, 1, -1, 0, 1], [-1, 1, -1, 0, -1, 1, 0], [-1, 1, -1, 0, -1, 1, 1], [-1, 0, -1, 1, -1, 0, 0]],
    # 平起首句入韵
    [[-1, 0, -1, 1, -1, 0, 0], [-1, 1, -1, 0, -1, 1, 0], [-1, 1, -1, 0, -1, 1, 1], [-1, 0, -1, 1, -1, 0, 0]],
]


def _patterns_for(length):
    return WUJUE_PATTERNS if length == 5 else QIJUE_PATTERNS


def _check_with_patterns(lines, patterns):
    """在多种起式中选错误最少的一种，避免只按单一起式误判。"""
    best_errors = None
    for base in patterns:
        template = (base * ((len(lines) + 3) // 4))[: len(lines)]
        errors = _check_lines(lines, template)
        if best_errors is None or len(errors) < len(best_errors):
            best_errors = errors
            if not errors:
                break
    return best_errors or []


def check_jueju(lines):
    """检测五/七言绝句，返回错误列表或"格律正确"。"""
    lines = [str(line).strip() for line in (lines or []) if str(line).strip()]
    if len(lines) != 4:
        return "需要四句"
    lengths = [len(re.findall(r"[\u4e00-\u9fff]", line)) for line in lines]
    if all(length == 5 for length in lengths):
        patterns = WUJUE_PATTERNS
    elif all(length == 7 for length in lengths):
        patterns = QIJUE_PATTERNS
    else:
        return "每句需全为五言或七言"
    errors = _check_with_patterns(lines, patterns)
    return errors if errors else "格律正确（近似检测，多音字请人工复核）"


def check_lvshi(lines):
    """检测五/七言律诗（八句）。"""
    lines = [str(line).strip() for line in (lines or []) if str(line).strip()]
    if len(lines) != 8:
        return "律诗需要八句"
    lengths = [len(re.findall(r"[\u4e00-\u9fff]", line)) for line in lines]
    if all(length == 5 for length in lengths):
        patterns = WUJUE_PATTERNS
    elif all(length == 7 for length in lengths):
        patterns = QIJUE_PATTERNS
    else:
        return "每句需全为五言或七言"
    errors = _check_with_patterns(lines, patterns)
    return errors if errors else "格律正确（近似检测，多音字请人工复核）"


def is_rusheng(char):
    return char in RUSHENG


def get_ping_ze(char):
    """返回 0=平，1=仄。非汉字、无法取声调时按仄处理。"""
    if not char or not ("\u4e00" <= char <= "\u9fff"):
        return 1
    if is_rusheng(char):
        return 1
    try:
        tone = pinyin(char, style=Style.TONE3, errors="ignore")[0][0]
    except (IndexError, TypeError):
        return 1
    numbers = re.findall(r"\d", tone)
    if not numbers:
        return 1
    return 0 if int(numbers[-1]) in (1, 2) else 1


def _check_lines(lines, template):
    errors = []
    for index, line in enumerate(lines):
        chars = re.findall(r"[\u4e00-\u9fff]", line)
        for position, (char, rule) in enumerate(zip(chars, template[index])):
            if rule == -1:
                continue
            actual = get_ping_ze(char)
            if actual != rule:
                errors.append(
                    f"第{index + 1}句第{position + 1}字'{char}'应为{'平' if rule == 0 else '仄'}"
                )
    return errors


def check_cipai(name, lines):
    """词牌暂不做自动判定，明确告知用户，避免假阳性结论。"""
    return f"词牌《{name}》暂不支持自动检测，请对照词谱人工核对。"


def check_poem(genre, lines):
    """按体裁分发检测。"""
    genre = str(genre or "")
    if "绝句" in genre:
        return check_jueju(lines)
    if "律诗" in genre:
        return check_lvshi(lines)
    if genre in {"如梦令", "蝶恋花", "浣溪沙", "水调歌头", "念奴娇", "临江仙"}:
        return check_cipai(genre, lines)
    return "该体裁无需格律检测"
