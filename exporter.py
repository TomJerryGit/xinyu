"""
心语 V6.5 — 导出排版模块（完整版）
"""
import os, math
from PIL import Image, ImageDraw, ImageFont

from utils import resource_path

# 依次尝试项目字体、系统中文字体，最后回退到 Pillow 默认字体
_FONT_CANDIDATES = [
    resource_path("resources", "fonts", "LXGWWenKai-Regular.ttf"),
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simsun.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]


def get_font(size=20):
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()

def _add_seal(draw, pos, text="心语", size=50):
    x, y = pos
    font = get_font(size // 2)
    draw.rectangle([x, y, x+size, y+size], outline='red', width=3)
    if len(text) == 2:
        draw.text((x+8, y+8), text[0], fill='red', font=font)
        draw.text((x+8, y+size//2), text[1], fill='red', font=font)
    elif len(text) >= 4:
        draw.text((x+4, y+4), text[:2], fill='red', font=font)
        draw.text((x+4, y+size//2), text[2:4], fill='red', font=font)

# ========== 横排图片 ==========
def export_image(text, output="output.png", font_size=24, bg_color=(255,250,240), author=""):
    font = get_font(font_size)
    lines = text.split('\n')
    w = max((len(line)*font_size//2 for line in lines), default=200) + 40
    h = (font_size+6)*len(lines) + 60
    img = Image.new('RGB', (w, h), bg_color)
    draw = ImageDraw.Draw(img)
    y = 20
    for line in lines:
        draw.text((20, y), line, fill=(40,40,40), font=font)
        y += font_size + 6
    if author:
        draw.text((w-120, h-30), author, fill=(100,80,60), font=get_font(14))
    img.save(output)
    return os.path.abspath(output)

# ========== 信笺模式 ==========
def export_letter_style(text, output="letter.png", author="", seal_text="心语"):
    w, h = 800, 650
    img = Image.new('RGB', (w, h), (255, 248, 240))
    draw = ImageDraw.Draw(img)
    for x in range(60, w-40, 45):
        draw.line([(x, 30), (x, h-50)], fill=(200,160,140), width=1)
    font = get_font(20)
    lines = text.strip().split('\n')
    x = w - 80
    for line in lines:
        y = 50
        for ch in line:
            if '\u4e00' <= ch <= '\u9fff' or ch in '，。！？；、':
                draw.text((x+12, y), ch, fill=(30,30,30), font=font)
                y += 28
        x -= 45
    if author:
        draw.text((80, h-100), author, fill=(100,80,60), font=get_font(14))
    if seal_text:
        _add_seal(draw, (100, h-150), seal_text)
    img.save(output)
    return os.path.abspath(output)

# ========== 扇面模式 ==========
def export_fan_style(text, output="fan.png", author=""):
    w, h = 650, 450
    img = Image.new('RGB', (w, h), (250,245,235))
    draw = ImageDraw.Draw(img)
    fan_center = (w//2, h+50)
    for angle in range(25, 155, 5):
        rad = math.radians(angle)
        ex = fan_center[0] + 350 * math.cos(rad)
        ey = fan_center[1] - 350 * math.sin(rad)
        draw.line([fan_center, (ex, ey)], fill=(200,180,160), width=1)
    font = get_font(16)
    all_chars = []
    for line in text.strip().split('\n'):
        all_chars.extend([c for c in line if c.strip()])
    angle_step = 110 / max(len(all_chars), 1)
    for i, ch in enumerate(all_chars):
        angle = 35 + i * angle_step
        rad = math.radians(angle)
        r = 220
        x = fan_center[0] + r*math.cos(rad) - 10
        y = fan_center[1] - r*math.sin(rad) - 30
        char_img = Image.new('RGBA', (30,30), (0,0,0,0))
        d = ImageDraw.Draw(char_img)
        d.text((5,5), ch, fill=(30,30,30), font=font)
        rotated = char_img.rotate(90-angle, expand=True)
        img.paste(rotated, (int(x), int(y)), rotated)
    if author:
        draw.text((w-120, h-40), author, fill=(100,80,60), font=get_font(12))
    img.save(output)
    return os.path.abspath(output)

# ========== 对联模式（红底金字）==========
def export_couplet_style(upper, lower, horizontal="", output="couplet.png"):
    w, h = 450, 700
    img = Image.new('RGB', (w, h), (160,30,30))
    draw = ImageDraw.Draw(img)
    font = get_font(32)
    y = 120
    for ch in upper:
        if ch.strip():
            draw.text((w-100, y), ch, fill=(255,215,0), font=font)
            y += 50
    y = 120
    for ch in lower:
        if ch.strip():
            draw.text((50, y), ch, fill=(255,215,0), font=font)
            y += 50
    if horizontal:
        hf = get_font(36)
        hw = len(horizontal)*40
        hx = (w - hw)//2
        for i, ch in enumerate(horizontal):
            draw.text((hx+i*40, 30), ch, fill=(255,215,0), font=hf)
    draw.rectangle([15,15,w-15,h-15], outline=(200,160,20), width=3)
    img.save(output)
    return os.path.abspath(output)

# ========== 春联模式（红纸黑字）==========
def export_spring_couplet(upper, lower, horizontal="", output="spring.png"):
    w, h = 450, 700
    img = Image.new('RGB', (w, h), (200,40,40))
    draw = ImageDraw.Draw(img)
    font = get_font(30)
    y = 100
    for ch in upper:
        if ch.strip():
            draw.text((w-110, y), ch, fill=(10,10,10), font=font)
            y += 55
    y = 100
    for ch in lower:
        if ch.strip():
            draw.text((60, y), ch, fill=(10,10,10), font=font)
            y += 55
    if horizontal:
        hf = get_font(38)
        hw = len(horizontal)*42
        hx = (w - hw)//2
        for i, ch in enumerate(horizontal):
            draw.text((hx+i*42, 25), ch, fill=(10,10,10), font=hf)
    img.save(output)
    return os.path.abspath(output)

# ========== 社交媒体卡片 ==========
def export_social_card(poem, title="", author="", output="social.png"):
    w, h = 600, 800
    img = Image.new('RGB', (w, h), (40,30,50))
    draw = ImageDraw.Draw(img)
    draw.rectangle([20,20,w-20,h-20], outline=(180,150,120), width=2)
    draw.rectangle([30,30,w-30,h-30], outline=(180,150,120), width=1)
    if title:
        tf = get_font(28)
        draw.text(((w-len(title)*30)//2, 60), title, fill=(220,200,160), font=tf)
    draw.line([(80,110),(w-80,110)], fill=(180,150,120), width=1)
    pf = get_font(22)
    y = 150
    for line in poem.strip().split('\n'):
        draw.text(((w-len(line)*24)//2, y), line, fill=(240,230,210), font=pf)
        y += 40
    if author:
        draw.text((w-150, h-80), f"—— {author}", fill=(160,140,120), font=get_font(16))
    draw.text((30, h-40), "心语 · AI 文学工坊", fill=(120,100,80), font=get_font(12))
    img.save(output)
    return os.path.abspath(output)