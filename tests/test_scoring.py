import unittest
from unittest.mock import patch
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from scoring import build_score_data, score_url


MOCK_REPORT_SCORES = {
    "brand_name": "TestBrand",
    "geo_score": 62,
    "diagnosis_text": "技術基礎穩定但 AI 識別度不足",
    "ai_citability": 72,
    "ai_citability_reason": "有 llms.txt，AI crawler 未封鎖",
    "content_eeat": 58,
    "content_eeat_reason": "有作者資訊，但缺乏引用來源",
    "technical": 65,
    "technical_reason": "HTTPS 完整，缺 canonical 標記",
    "brand_authority": 52,
    "brand_authority_reason": "媒體曝光少，社群口碑薄弱",
    "schema": 18,
    "schema_reason": "缺 Organization schema",
    "chatgpt_score": 60,
    "gemini_score": 55,
    "google_ai_score": 58,
    "perplexity_score": 45,
    "media_coverage": 18,
    "content_depth": 13,
    "social_presence": 12,
    "entity_recognition": 9,
}


class TestBuildScoreData(unittest.TestCase):
    def test_output_structure(self):
        result = build_score_data("https://example.com", MOCK_REPORT_SCORES)
        self.assertEqual(result["url"], "https://example.com")
        self.assertIn("date", result)
        self.assertEqual(len(result["dimensions"]), 5)
        self.assertEqual(len(result["ai_platforms"]), 4)
        self.assertIn("citation_matrix", result)

    def test_schema_color_yellow_when_below_40(self):
        result = build_score_data("https://example.com", MOCK_REPORT_SCORES)
        schema_dim = next(d for d in result["dimensions"] if "Schema" in d["label"])
        self.assertEqual(schema_dim.get("color"), "yellow")

    def test_schema_no_color_when_above_40(self):
        scores = {**MOCK_REPORT_SCORES, "schema": 55}
        result = build_score_data("https://example.com", scores)
        schema_dim = next(d for d in result["dimensions"] if "Schema" in d["label"])
        self.assertNotIn("color", schema_dim)

    def test_dimensions_have_reason(self):
        result = build_score_data("https://example.com", MOCK_REPORT_SCORES)
        for dim in result["dimensions"]:
            self.assertIn("reason", dim, f"Missing reason in {dim['label']}")

    def test_citation_matrix_center_avg_equals_brand_authority(self):
        result = build_score_data("https://example.com", MOCK_REPORT_SCORES)
        self.assertEqual(
            result["citation_matrix"]["center_avg"],
            MOCK_REPORT_SCORES["brand_authority"]
        )

    def test_geo_score_uses_report_weights(self):
        result = build_score_data("https://example.com", MOCK_REPORT_SCORES)
        self.assertEqual(result["geo_score"], 56)


class TestScoreUrl(unittest.TestCase):
    @patch("scoring.run_report_audit")
    def test_score_url_uses_report_engine_without_claude_totals(self, audit):
        audit.return_value = {
            "brand_name": "TestBrand",
            "scores": {
                "ai_platform": 61,
                "content": 52,
                "technical": 63,
                "schema": 24,
                "brand": 31,
            },
            "reasons": {
                "ai_platform": "五平台實測",
                "content": "E-E-A-T 檢核",
                "technical": "八類技術檢核",
                "schema": "Schema 12 項檢核",
                "brand": "台灣搜尋實測",
            },
            "platform_scores": {
                "chatgpt": 60,
                "gemini": 55,
                "google_ai": 58,
                "perplexity": 45,
                "bing_copilot": 42,
            },
            "brand_matrix": {
                "media": 12,
                "content_depth": 6,
                "social": 4,
                "entity": 9,
            },
            "warnings": [],
        }

        result = score_url("https://example.com")

        dimensions = {item["label"]: item["score"] for item in result["dimensions"]}
        self.assertEqual(dimensions, {
            "AI 平台準備度": 61,
            "內容品質 E-E-A-T": 52,
            "技術基礎": 63,
            "品牌權威度": 31,
            "Schema 結構化資料": 24,
        })
        audit.assert_called_once_with("https://example.com")


if __name__ == "__main__":
    unittest.main()
