import os
import re
import json
from datetime import date
from urllib.parse import urlparse

import requests
import anthropic


SCORING_PROMPT = """\
你是 GEO（Generative Engine Optimization）評分專家。根據以下網頁內容，對網站進行快速評分。

目標網址：{url}

HTML 內容（前 8000 字元）：
{html}

robots.txt：
{robots}

請評分以下維度，以 JSON 格式回傳。所有分數必須是整數，不得為空。

評分規則：
- ai_citability (0-100)：有無 llms.txt、AI crawler 是否被允許、內容是否有清晰可引用的事實
- content_eeat (0-100)：有無作者資訊、內容深度與原創性、有無引用來源
- technical (0-100)：HTTPS、meta description、canonical、heading structure
- schema (0-100)：HTML 中有無 JSON-LD / microdata，schema 類型與完整度
- chatgpt_score (0-100)：ChatGPT 引用可能性
- gemini_score (0-100)：Google Gemini 引用可能性
- google_ai_score (0-100)：Google AI Overviews 適配度
- perplexity_score (0-100)：Perplexity 引用可能性
- media_coverage (0-40)：根據你訓練資料中的知識，評估這個品牌在台灣主流媒體（聯合報、中時、自由時報、商業週刊、天下、遠見、數位時代等）的曝光量與報導頻率。媒體記錄豐富給高分，幾乎無台灣媒體報導給低分。不要看頁面上有無提及，而是你自己對這個品牌的認知。
- content_depth (0-20)：頁面內容是否有深度（長文/研究/數據）
- social_presence (0-20)：是否有用戶評論、UGC 跡象、真實社群互動。僅有社群帳號連結不算分，需要有實際互動或評論內容。
- entity_recognition (0-20)：品牌名稱、地址、聯絡資訊、知識圖譜信號

注意：brand_authority 由系統自動計算（= media_coverage + content_depth + social_presence + entity_recognition），請勿回傳此欄位。

另外需要：
- brand_name：從 URL 或頁面推斷的品牌名稱
- diagnosis_text：一句話整體診斷（繁體中文，20-40 字）
- 各維度的 reason：一句評分依據（繁體中文，15-30 字）

只回傳 JSON，不要其他文字：
{{
  "brand_name": "...",
  "diagnosis_text": "...",
  "ai_citability": <整數>, "ai_citability_reason": "...",
  "content_eeat": <整數>,  "content_eeat_reason": "...",
  "technical": <整數>,     "technical_reason": "...",
  "schema": <整數>,        "schema_reason": "...",
  "chatgpt_score": <整數>, "gemini_score": <整數>,
  "google_ai_score": <整數>, "perplexity_score": <整數>,
  "media_coverage": <整數>, "content_depth": <整數>,
  "social_presence": <整數>, "entity_recognition": <整數>,
  "brand_authority_reason": "..."
}}
"""


def _fetch_page(url: str) -> tuple[str, str]:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; GEO-Scorer/1.0)"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        html = resp.text[:8000]
    except Exception as exc:
        html = f"[fetch error: {exc}]"

    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        robots_resp = requests.get(robots_url, headers=headers, timeout=10)
        robots = robots_resp.text[:2000]
    except Exception:
        robots = "[robots.txt not found]"

    return html, robots


def parse_claude_response(raw: str) -> dict:
    """Extract and parse JSON from Claude's text response."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON found in Claude response: {raw[:200]}")
    return json.loads(match.group())


def build_score_data(url: str, scores: dict) -> dict:
    """Transform raw scores dict into the canonical scorecard data format."""
    # brand_authority = 四個子項加總（正確邏輯，與本地版一致）
    brand_authority = (
        int(scores["media_coverage"]) +
        int(scores["content_depth"]) +
        int(scores["social_presence"]) +
        int(scores["entity_recognition"])
    )

    # geo_score 用正確的 brand_authority 重算
    geo_score = round(
        int(scores["ai_citability"]) * 0.25 +
        int(scores["content_eeat"])  * 0.25 +
        int(scores["technical"])     * 0.20 +
        brand_authority              * 0.20 +
        int(scores["schema"])        * 0.10
    )

    schema_score = int(scores["schema"])
    schema_dim = {
        "label": "Schema 結構化資料",
        "score": schema_score,
        "reason": scores["schema_reason"],
    }
    if schema_score < 40:
        schema_dim["color"] = "yellow"

    return {
        "brand_name":     scores["brand_name"],
        "url":            url,
        "date":           date.today().strftime("%Y-%m-%d"),
        "geo_score":      geo_score,
        "title":          "GEO 系統診斷：\n數位資產能見度評估",
        "diagnosis_text": scores["diagnosis_text"],
        "dimensions": [
            {"label": "AI 平台準備度",    "score": int(scores["ai_citability"]), "reason": scores["ai_citability_reason"]},
            {"label": "內容品質 E-E-A-T", "score": int(scores["content_eeat"]),  "reason": scores["content_eeat_reason"]},
            {"label": "技術基礎",         "score": int(scores["technical"]),      "reason": scores["technical_reason"]},
            {"label": "品牌權威度",       "score": brand_authority,               "reason": scores["brand_authority_reason"]},
            schema_dim,
        ],
        "ai_platforms": [
            {"name": "ChatGPT",       "score": int(scores["chatgpt_score"])},
            {"name": "Google Gemini", "score": int(scores["gemini_score"])},
            {"name": "Google AI",     "score": int(scores["google_ai_score"])},
            {"name": "Perplexity",    "score": int(scores["perplexity_score"])},
        ],
        "citation_matrix": {
            "top_left":     {"label": "媒體報導",   "score": int(scores["media_coverage"]),     "max": 40},
            "top_right":    {"label": "內容深度",   "score": int(scores["content_depth"]),      "max": 20},
            "bottom_left":  {"label": "社群口碑",   "score": int(scores["social_presence"]),    "max": 20},
            "bottom_right": {"label": "實體辨識度", "score": int(scores["entity_recognition"]), "max": 20},
            "center_avg":   brand_authority,
        },
    }


def score_url(url: str) -> dict:
    """Main entry point: fetch URL, call Claude, return structured scorecard data."""
    html, robots = _fetch_page(url)

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt = SCORING_PROMPT.format(url=url, html=html, robots=robots)

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    scores = parse_claude_response(raw)
    return build_score_data(url, scores)
