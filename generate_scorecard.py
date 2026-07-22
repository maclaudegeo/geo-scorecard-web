#!/usr/bin/env python3
"""
GEO Score Card Generator — Landscape Dashboard Edition
Generates a 1280x720px landscape dashboard (16:9, presentation ready).

Data format (JSON):
{
  "brand_name":     "雅漾",
  "title":          "GEO 系統診斷：\n數位資產能見度斷層",
  "geo_score":      46,
  "diagnosis_text": "診斷說明文字",
  "date":           "2026-04-22",
  "dimensions": [
    {"label": "內容 E-E-A-T",      "score": 58},
    {"label": "技術基礎",          "score": 62},
    {"label": "品牌權威度",        "score": 52},
    {"label": "AI 平台準備度",     "score": 38},
    {"label": "Schema 結構化資料", "score": 18, "color": "yellow"}
  ],
  "ai_platforms": [
    {"name": "ChatGPT",       "score": 44},
    {"name": "Google Gemini", "score": 42},
    {"name": "Google AI",     "score": 41},
    {"name": "Perplexity",    "score": 36}
  ],
  "citation_matrix": {
    "top_left":     {"label": "媒體報導",   "score": 18, "max": 40},
    "top_right":    {"label": "內容深度",   "score": 13, "max": 20},
    "bottom_left":  {"label": "社群口碑",   "score": 12, "max": 20},
    "bottom_right": {"label": "實體辨識度", "score": 9,  "max": 20},
    "center_avg": 52
  }
}

Usage: python3 generate_scorecard.py data.json [output.png]
"""

import sys
import json
import random
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
except ImportError:
    print("ERROR: Pillow not installed. Run: pip install Pillow")
    sys.exit(1)

# ── Canvas ────────────────────────────────────────────────────────────────────
W, H   = 1280, 720
PAD    = 60

# ── Palette ───────────────────────────────────────────────────────────────────
BG          = (0,    0,   0)
BG_CELL     = (18,  18,  18)
TEXT_WHITE  = (255, 255, 255)
TEXT_MUTED  = (150, 165, 185)
TEXT_DIM    = (90,  90,  90)
TEAL        = (32,  230, 180)
TEAL_DIM    = (18,  70,  58)
YELLOW      = (255, 210,  55)
YELLOW_DIM  = (80,   62,  14)
BORDER      = (50,  50,  50)
DIVIDER     = (35,   48,  65)

# ── Font loader ───────────────────────────────────────────────────────────────
def load_font(size):
    candidates = [
        str(Path(__file__).parent / "NotoSansCJKtc-Regular.otf"),
        str(Path(__file__).parent / "NotoSansTC-Regular.ttf"),
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()

# ── Drawing helpers ───────────────────────────────────────────────────────────
def text_w(draw, text, font):
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0]

def text_h(draw, text, font):
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[3] - bb[1]

def draw_left(draw, text, font, x, y, color):
    draw.text((x, y), text, font=font, fill=color)

def draw_right(draw, text, font, rx, y, color):
    w = text_w(draw, text, font)
    draw.text((rx - w, y), text, font=font, fill=color)

def draw_center(draw, text, font, cx, y, color):
    w = text_w(draw, text, font)
    draw.text((cx - w // 2, y), text, font=font, fill=color)

def draw_progress_bar(draw, x, y, w, h, pct, fg, bg):
    r = h // 2
    draw.rounded_rectangle([x, y, x + w, y + h], radius=r, fill=bg)
    filled = max(int(w * min(pct, 1.0)), h)
    draw.rounded_rectangle([x, y, x + filled, y + h], radius=r, fill=fg)

def draw_glow_arc(img, cx, cy, r, start_deg, end_deg, fg_color, track_color, layers=6, width=14):
    for i in range(layers, 0, -1):
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        alpha = int(55 * (1 - i / (layers + 1)))
        bbox = [cx - r, cy - r, cx + r, cy + r]
        ld.arc(bbox, start=start_deg, end=end_deg,
               fill=(*fg_color, alpha), width=width + i * 5)
        blurred = layer.filter(ImageFilter.GaussianBlur(radius=i * 2.5))
        img = Image.alpha_composite(img.convert("RGBA"), blurred).convert("RGB")

    d = ImageDraw.Draw(img)
    bbox = [cx - r, cy - r, cx + r, cy + r]
    d.arc(bbox, start=135, end=405, fill=track_color, width=width - 2)
    d.arc(bbox, start=start_deg, end=end_deg, fill=fg_color, width=width)
    return img

def wrap_text(draw, text, font, max_w):
    lines = []
    for para in text.split("\n"):
        line = ""
        for ch in para:
            test = line + ch
            if text_w(draw, test, font) > max_w and line:
                lines.append(line)
                line = ch
            else:
                line = test
        if line:
            lines.append(line)
    return lines

# ── Main generator ────────────────────────────────────────────────────────────
def generate_scorecard(data: dict, output_path: str):
    random.seed(42)

    img = Image.new("RGB", (W, H), BG)

    # Flat black background (no gradient)

    draw = ImageDraw.Draw(img)

    # Fonts
    f44 = load_font(44)
    f34 = load_font(34)
    f24 = load_font(24)
    f20 = load_font(20)
    f18 = load_font(18)
    f16 = load_font(16)
    f14 = load_font(14)
    f90 = load_font(90)   # big score
    f30 = load_font(30)

    url        = data.get("url", "")
    geo_score  = float(data.get("geo_score", 0))
    diag_text  = data.get("diagnosis_text", "")
    date_str   = data.get("date", "")
    dimensions = data.get("dimensions", [])
    ai_plats   = data.get("ai_platforms", [])
    citation   = data.get("citation_matrix", {})

    # ── Column boundaries ─────────────────────────────────────────────────────
    L_X  = PAD          # left col start  = 60
    L_W  = 290          # left col width  → ends at 350
    R_X  = 920          # right col start
    R_W  = W - PAD - R_X   # right col width = 300
    CX   = (L_X + L_W + R_X) // 2   # centre X = 635

    # ─────────────────────────────────────────────────────────────────────────
    # LEFT COLUMN — title + 5-dimension analysis
    # ─────────────────────────────────────────────────────────────────────────
    CONTENT_TOP = PAD
    CONTENT_BOT = H - PAD - 30   # 630

    y = CONTENT_TOP

    # Title
    draw_left(draw, "GEO 檢測報告", f44, L_X, y, TEXT_WHITE)
    y += 62
    draw_left(draw, url, f20, L_X, y, TEXT_MUTED)
    y += 44

    # "5-Dimension Analysis"
    draw_left(draw, "5-Dimension Analysis", f20, L_X, y, TEXT_WHITE)
    y += 38

    # Horizontal rule
    draw.line([(L_X, y), (L_X + L_W, y)], fill=DIVIDER, width=1)
    y += 18

    # Dimension rows — spread to fill left column height
    DIM_ROW_H = (CONTENT_BOT - y) // max(len(dimensions), 1)

    for dim in dimensions:
        label = dim.get("label", "")
        score = int(dim.get("score", 0))
        color = YELLOW if dim.get("color") == "yellow" else TEAL
        bg    = YELLOW_DIM if dim.get("color") == "yellow" else TEAL_DIM

        score_str_main = str(score)
        score_str_sub  = "/100"

        draw_left(draw, label + "：", f20, L_X, y, TEXT_WHITE)

        rx = L_X + L_W
        sw_sub = text_w(draw, score_str_sub, f16)
        sw_num = text_w(draw, score_str_main, f24)
        draw.text((rx - sw_sub - sw_num - 2, y + 2), score_str_main, font=f24, fill=color)
        draw.text((rx - sw_sub,              y + 6), score_str_sub,  font=f16, fill=TEXT_MUTED)

        y += 32

        # Progress bar
        draw_progress_bar(draw, L_X, y, L_W, 7, score / 100, color, bg)
        y += DIM_ROW_H - 32

    # ─────────────────────────────────────────────────────────────────────────
    # CENTER — gauge
    # ─────────────────────────────────────────────────────────────────────────
    GCY = (CONTENT_TOP + CONTENT_BOT) // 2   # vertically centred = 345
    GR  = 190

    # Glow arc
    start_angle = 135
    sweep       = 270 * (geo_score / 100)
    end_angle   = start_angle + max(sweep, 1)
    img = draw_glow_arc(img, CX, GCY, GR, start_angle, end_angle, TEAL, TEAL_DIM)
    draw = ImageDraw.Draw(img)

    # Score label + number + /100
    draw_center(draw, "整體分數", f18, CX, GCY - 88, TEXT_MUTED)
    score_str = str(int(geo_score))
    draw_center(draw, score_str, f90, CX, GCY - 62, TEXT_WHITE)
    draw_center(draw, "/100",    f30, CX, GCY + 62,  TEXT_MUTED)

    # ─────────────────────────────────────────────────────────────────────────
    # RIGHT COLUMN — AI platform scores + citation matrix
    # ─────────────────────────────────────────────────────────────────────────
    y = CONTENT_TOP

    # -- AI Platform Scores --
    draw_left(draw, "AI 能見度分析", f20, R_X, y, TEXT_WHITE)
    y += 28

    for plat in ai_plats:
        name  = plat.get("name", "")
        score = int(plat.get("score", 0))
        color = TEAL

        draw_left(draw, name + "：", f16, R_X, y, TEXT_MUTED)

        rx = R_X + R_W
        sw_num = text_w(draw, str(score), f18)
        sw_sub = text_w(draw, "/100", f14)
        draw.text((rx - sw_sub - sw_num - 2, y), str(score), font=f18, fill=color)
        draw.text((rx - sw_sub, y + 3), "/100", font=f14, fill=TEXT_MUTED)

        y += 22
        draw_progress_bar(draw, R_X, y, R_W, 5, score / 100, color, TEAL_DIM)
        y += 5 + 12

    y += 14

    # -- Brand Citation Matrix --
    draw_left(draw, "品牌權威度分析", f20, R_X, y, TEXT_WHITE)
    y += 26

    GAP      = 8
    CELL_W   = (R_W - GAP) // 2                       # ≈ 146px
    available = CONTENT_BOT - y - GAP
    CELL_H   = (available - GAP) // 2                 # fill all remaining height

    cells = [
        citation.get("top_left",     {"label": "媒體報導",   "score": 0, "max": 40}),
        citation.get("top_right",    {"label": "內容深度",   "score": 0, "max": 20}),
        citation.get("bottom_left",  {"label": "社群口碑",   "score": 0, "max": 20}),
        citation.get("bottom_right", {"label": "實體辨識度", "score": 0, "max": 20}),
    ]
    center_avg = citation.get("center_avg", 0)
    GRID_TOP = y

    for i, cell in enumerate(cells):
        col = i % 2
        row = i // 2
        cx1 = R_X + col * (CELL_W + GAP)
        cy1 = GRID_TOP + row * (CELL_H + GAP)
        cx2 = cx1 + CELL_W
        cy2 = cy1 + CELL_H

        draw.rounded_rectangle([cx1, cy1, cx2, cy2], radius=10,
                               fill=BG_CELL, outline=BORDER, width=1)

        lbl   = cell.get("label", "")
        score = cell.get("score", 0)
        max_s = cell.get("max", 20)

        # Vertically center content in cell
        mid_y = (cy1 + cy2) // 2
        draw_left(draw, lbl + "：", f16, cx1 + 14, mid_y - 30, TEXT_MUTED)
        draw_left(draw, f"{score}/{max_s}", f30, cx1 + 14, mid_y - 6, TEXT_WHITE)

    # Centre overlay circle — sits at intersection of 4 cells
    grid_cx = R_X + R_W // 2
    grid_cy = GRID_TOP + CELL_H + GAP // 2
    CR = 56
    draw.ellipse([grid_cx - CR, grid_cy - CR, grid_cx + CR, grid_cy + CR],
                 fill=BG, outline=BORDER, width=2)
    draw_center(draw, "均分",             f16, grid_cx, grid_cy - 24, TEXT_MUTED)
    draw_center(draw, f"{center_avg}/100", f20, grid_cx, grid_cy + 4,  TEXT_WHITE)

    # ── Footer ────────────────────────────────────────────────────────────────
    LOGO_PATH = Path(__file__).parent.parent / "assets" / "microad-logo.png"
    try:
        logo = Image.open(LOGO_PATH).convert("RGBA")
        logo_h = 112
        ratio  = logo_h / logo.height
        logo   = logo.resize((int(logo.width * ratio), logo_h), Image.LANCZOS)
        img.paste(logo, (W - PAD - logo.width, H - 80), logo)
    except Exception:
        draw.text((W - PAD - 80, H - 34), "MicRoad", font=f14, fill=TEXT_DIM)

    if date_str:
        draw.text((PAD, H - 34), date_str, font=f14, fill=TEXT_DIM)

    img.save(output_path, "PNG", quality=95)
    print(f"✅ Score card saved: {output_path}")
    print(f"   Size: {W}×{H}px (16:9 landscape)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 generate_scorecard.py data.json [output.png]")
        sys.exit(1)

    json_path = sys.argv[1]
    out_path  = sys.argv[2] if len(sys.argv) > 2 else "GEO-SCORE-CARD.png"

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    generate_scorecard(data, out_path)
