import json
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from scoring import build_score_data, parse_claude_response


MOCK_CLAUDE_JSON = {
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


class TestParseClaudeResponse(unittest.TestCase):
    def test_parse_valid_json_string(self):
        raw = json.dumps(MOCK_CLAUDE_JSON)
        result = parse_claude_response(raw)
        self.assertEqual(result["brand_name"], "TestBrand")
        self.assertEqual(result["geo_score"], 62)

    def test_parse_json_with_surrounding_text(self):
        raw = "Here is the result:\n" + json.dumps(MOCK_CLAUDE_JSON) + "\nDone."
        result = parse_claude_response(raw)
        self.assertEqual(result["geo_score"], 62)

    def test_parse_missing_json_raises(self):
        with self.assertRaises(ValueError):
            parse_claude_response("No JSON here at all.")


class TestBuildScoreData(unittest.TestCase):
    def test_output_structure(self):
        result = build_score_data("https://example.com", MOCK_CLAUDE_JSON)
        self.assertEqual(result["url"], "https://example.com")
        self.assertIn("date", result)
        self.assertEqual(len(result["dimensions"]), 5)
        self.assertEqual(len(result["ai_platforms"]), 4)
        self.assertIn("citation_matrix", result)

    def test_schema_color_yellow_when_below_40(self):
        result = build_score_data("https://example.com", MOCK_CLAUDE_JSON)
        schema_dim = next(d for d in result["dimensions"] if "Schema" in d["label"])
        self.assertEqual(schema_dim.get("color"), "yellow")

    def test_schema_no_color_when_above_40(self):
        scores = {**MOCK_CLAUDE_JSON, "schema": 55}
        result = build_score_data("https://example.com", scores)
        schema_dim = next(d for d in result["dimensions"] if "Schema" in d["label"])
        self.assertNotIn("color", schema_dim)

    def test_dimensions_have_reason(self):
        result = build_score_data("https://example.com", MOCK_CLAUDE_JSON)
        for dim in result["dimensions"]:
            self.assertIn("reason", dim, f"Missing reason in {dim['label']}")

    def test_citation_matrix_center_avg_equals_brand_authority(self):
        result = build_score_data("https://example.com", MOCK_CLAUDE_JSON)
        self.assertEqual(
            result["citation_matrix"]["center_avg"],
            MOCK_CLAUDE_JSON["brand_authority"]
        )


if __name__ == "__main__":
    unittest.main()
