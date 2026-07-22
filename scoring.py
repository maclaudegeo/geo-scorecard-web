from datetime import date

from report_scoring import run_report_audit


def build_score_data(url: str, scores: dict) -> dict:
    """Transform raw scores dict into the canonical scorecard data format."""
    # brand_authority = 四個子項加總（正確邏輯，與本地版一致）
    brand_authority = (
        int(scores["media_coverage"]) +
        int(scores["content_depth"]) +
        int(scores["social_presence"]) +
        int(scores["entity_recognition"])
    )

    # /geo report 官方權重：平台 25、內容 25、技術 20、Schema 15、品牌 15。
    geo_score = round(
        int(scores["ai_citability"]) * 0.25 +
        int(scores["content_eeat"])  * 0.25 +
        int(scores["technical"])     * 0.20 +
        int(scores["schema"])        * 0.15 +
        brand_authority              * 0.15
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
    """Fetch real evidence and calculate the installed `/geo report` rubrics."""
    audit = run_report_audit(url)
    shared = audit["scores"]
    reasons = audit["reasons"]
    platforms = audit["platform_scores"]
    matrix = audit["brand_matrix"]
    weakest_key = min(shared, key=shared.get)
    labels = {
        "ai_platform": "AI 平台準備度",
        "content": "內容品質 E-E-A-T",
        "technical": "技術基礎",
        "schema": "Schema 結構化資料",
        "brand": "品牌權威度",
    }
    scores = {
        "brand_name": audit["brand_name"],
        "diagnosis_text": f"目前主要缺口為{labels[weakest_key]}（{shared[weakest_key]} 分）",
        "ai_citability": shared["ai_platform"],
        "ai_citability_reason": reasons["ai_platform"],
        "content_eeat": shared["content"],
        "content_eeat_reason": reasons["content"],
        "technical": shared["technical"],
        "technical_reason": reasons["technical"],
        "schema": shared["schema"],
        "schema_reason": reasons["schema"],
        "brand_authority_reason": reasons["brand"],
        "chatgpt_score": platforms["chatgpt"],
        "gemini_score": platforms["gemini"],
        "google_ai_score": platforms["google_ai"],
        "perplexity_score": platforms["perplexity"],
        "media_coverage": matrix["media"],
        "content_depth": matrix["content_depth"],
        "social_presence": matrix["social"],
        "entity_recognition": matrix["entity"],
    }
    return build_score_data(url, scores)
