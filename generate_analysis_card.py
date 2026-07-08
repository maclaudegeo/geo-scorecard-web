#!/usr/bin/env python3
"""
GEO Analysis Card Generator — 1280x720px landscape
Left panel : brand name + diagnosis text box
Right panel: 5 dimension cards (score + one-line reason)
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
PAD  = 60

BG          = (0,   0,   0)
BG_CELL     = (18,  18,  18)
TEXT_WHITE  = (255, 255, 255)
TEXT_MUTED  = (150, 165, 185)
TEXT_DIM    = (90,  90,  90)
TEAL        = (32,  230, 180)
TEAL_DIM    = (18,  70,  58)
YELLOW      = (255, 210,  55)
YELLOW_DIM  = (80,  62,  14)
BORDER      = (50,  50,  50)


def _load_font(size: int):
    candidates = [
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


def _tw(draw, text: str, font) -> int:
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0]


def _wrap(draw, text: str, font, max_w: int) -> list:
    lines, line = [], ""
    for ch in text:
        test = line + ch
        if _tw(draw, test, font) > max_w and line:
            lines.append(line)
            line = ch
        else:
            line = test
    if line:
        lines.append(line)
    return lines


def generate_analysis_card(data: dict, output_path: str) -> None:
    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    f48 = _load_font(48)
    f22 = _load_font(22)
    f20 = _load_font(20)
    f18 = _load_font(18)
    f16 = _load_font(16)
    f14 = _load_font(14)
    f28 = _load_font(28)

    brand_name     = data.get("brand_name", "")
    diagnosis_text = data.get("diagnosis_text", "")
    dimensions     = data.get("dimensions", [])
    date_str       = data.get("date", "")

    TOP     = PAD
    BOT     = H - PAD - 30
    LEFT_W  = 390
    RIGHT_X = LEFT_W + PAD + 10
    RIGHT_W = W - RIGHT_X - PAD

    # ── LEFT PANEL ────────────────────────────────────────────────────
    draw.text((PAD, TOP), "GEO 檢測報告", font=f22, fill=TEXT_MUTED)

    y = TOP + 44
    # 自動縮小字體讓品牌名稱不超出左欄
    brand_font = f48
    for size in [48, 38, 30, 24]:
        brand_font = _load_font(size)
        if _tw(draw, brand_name, brand_font) <= LEFT_W - PAD:
            break
    # 若還是太長就截斷
    while _tw(draw, brand_name, brand_font) > LEFT_W - PAD and len(brand_name) > 4:
        brand_name = brand_name[:-1]
    draw.text((PAD, y), brand_name, font=brand_font, fill=TEXT_WHITE)
    y += 68

    draw.text((PAD, y), "GEO 系統診斷", font=f22, fill=TEAL)
    y += 34
    draw.text((PAD, y), "五大核心指標剖析", font=f22, fill=TEAL)
    y += 52

    # Diagnosis box
    diag_lines = _wrap(draw, diagnosis_text, f18, LEFT_W - PAD - 28)
    box_h  = len(diag_lines) * 28 + 40
    bx1, by1 = PAD, y
    bx2, by2 = PAD + LEFT_W - PAD, y + box_h
    draw.rounded_rectangle([bx1, by1, bx2, by2], radius=10,
                           fill=TEAL_DIM, outline=TEAL, width=2)
    draw.text((bx1 + 14, by1 + 8), "診斷結論：", font=f16, fill=TEAL)
    dy = by1 + 32
    for line in diag_lines:
        draw.text((bx1 + 14, dy), line, font=f18, fill=TEXT_WHITE)
        dy += 28

    # ── RIGHT PANEL — 5 dimension cards ──────────────────────────────
    CARD_GAP = 10
    CARD_H   = (BOT - TOP - 4 * CARD_GAP) // 5
    cy = TOP

    for dim in dimensions:
        label      = dim.get("label", "")
        score      = int(dim.get("score", 0))
        reason     = dim.get("reason", "")
        is_yellow  = dim.get("color") == "yellow"
        accent     = YELLOW if is_yellow else TEAL
        accent_dim = YELLOW_DIM if is_yellow else TEAL_DIM

        draw.rounded_rectangle(
            [RIGHT_X, cy, RIGHT_X + RIGHT_W, cy + CARD_H],
            radius=10, fill=BG_CELL, outline=BORDER, width=1
        )

        # Score (right-aligned)
        score_str = f"{score}/100"
        sw = _tw(draw, score_str, f28)
        draw.text((RIGHT_X + RIGHT_W - 20 - sw, cy + 12),
                  score_str, font=f28, fill=accent)

        # Label
        draw.text((RIGHT_X + 20, cy + 14), label + "：", font=f20, fill=TEXT_WHITE)

        # Progress bar
        bar_y = cy + 48
        bar_w = RIGHT_W - 40
        draw.rounded_rectangle(
            [RIGHT_X + 20, bar_y, RIGHT_X + 20 + bar_w, bar_y + 5],
            radius=2, fill=accent_dim
        )
        filled = max(int(bar_w * score / 100), 5)
        draw.rounded_rectangle(
            [RIGHT_X + 20, bar_y, RIGHT_X + 20 + filled, bar_y + 5],
            radius=2, fill=accent
        )

        # Reason text
        reason_lines = _wrap(draw, f"（{reason}）", f16, RIGHT_W - 40)
        ry = bar_y + 12
        for line in reason_lines:
            draw.text((RIGHT_X + 20, ry), line, font=f16, fill=TEXT_MUTED)
            ry += 22

        cy += CARD_H + CARD_GAP

    # ── Footer ────────────────────────────────────────────────────────
    LOGO_PATH = Path.home() / ".claude/skills/geo-scorecard/assets/microad-logo.png"
    try:
        logo   = Image.open(LOGO_PATH).convert("RGBA")
        logo_h = 112
        ratio  = logo_h / logo.height
        logo   = logo.resize((int(logo.width * ratio), logo_h), Image.LANCZOS)
        img.paste(logo, (W - PAD - logo.width, H - 80), logo)
    except Exception:
        draw.text((W - PAD - 80, H - 34), "MicRoad", font=f14, fill=TEXT_DIM)

    if date_str:
        draw.text((PAD, H - 34), date_str, font=f14, fill=TEXT_DIM)

    img.save(output_path, "PNG", quality=95)
    print(f"✅ Analysis card saved: {output_path}")
