import unittest
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from generate_analysis_card import generate_analysis_card

FIXTURE = {
    "brand_name": "TestBrand",
    "url": "https://example.com",
    "date": "2026-04-25",
    "geo_score": 62,
    "diagnosis_text": "技術基礎穩定但 AI 識別度不足，需建立結構化資料",
    "dimensions": [
        {"label": "AI 平台準備度",    "score": 72, "reason": "有 llms.txt，AI crawler 未封鎖"},
        {"label": "內容品質 E-E-A-T", "score": 58, "reason": "有作者資訊，但缺乏引用來源"},
        {"label": "技術基礎",         "score": 65, "reason": "HTTPS 完整，缺 canonical 標記"},
        {"label": "品牌權威度",       "score": 52, "reason": "媒體曝光少，社群口碑薄弱"},
        {"label": "Schema 結構化資料","score": 18, "reason": "缺 Organization schema", "color": "yellow"},
    ],
    "ai_platforms": [
        {"name": "ChatGPT",       "score": 60},
        {"name": "Google Gemini", "score": 55},
        {"name": "Google AI",     "score": 58},
        {"name": "Perplexity",    "score": 45},
    ],
    "citation_matrix": {
        "top_left":     {"label": "媒體報導",   "score": 18, "max": 40},
        "top_right":    {"label": "內容深度",   "score": 13, "max": 20},
        "bottom_left":  {"label": "社群口碑",   "score": 12, "max": 20},
        "bottom_right": {"label": "實體辨識度", "score": 9,  "max": 20},
        "center_avg": 52,
    },
}


class TestGenerateAnalysisCard(unittest.TestCase):
    def test_creates_png_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = str(Path(tmpdir) / "analysis.png")
            generate_analysis_card(FIXTURE, out)
            self.assertTrue(Path(out).exists())

    def test_output_is_correct_size(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmpdir:
            out = str(Path(tmpdir) / "analysis.png")
            generate_analysis_card(FIXTURE, out)
            img = Image.open(out)
            self.assertEqual(img.size, (1280, 720))

    def test_works_with_long_diagnosis_text(self):
        data = {**FIXTURE, "diagnosis_text": "這是一段很長的診斷文字，" * 5}
        with tempfile.TemporaryDirectory() as tmpdir:
            out = str(Path(tmpdir) / "analysis.png")
            generate_analysis_card(data, out)
            self.assertTrue(Path(out).exists())


if __name__ == "__main__":
    unittest.main()
