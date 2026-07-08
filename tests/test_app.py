import json
import unittest
from unittest.mock import patch
from pathlib import Path
import sys
import tempfile
import shutil

sys.path.insert(0, str(Path(__file__).parent.parent))

MOCK_SCORE_DATA = {
    "brand_name": "TestBrand",
    "url": "https://example.com",
    "date": "2026-04-25",
    "geo_score": 62,
    "title": "GEO 系統診斷：\n數位資產能見度評估",
    "diagnosis_text": "測試診斷文字",
    "dimensions": [
        {"label": "AI 平台準備度",    "score": 72, "reason": "測試"},
        {"label": "內容品質 E-E-A-T", "score": 58, "reason": "測試"},
        {"label": "技術基礎",         "score": 65, "reason": "測試"},
        {"label": "品牌權威度",       "score": 52, "reason": "測試"},
        {"label": "Schema 結構化資料","score": 18, "reason": "測試", "color": "yellow"},
    ],
    "ai_platforms": [
        {"name": "ChatGPT", "score": 60}, {"name": "Google Gemini", "score": 55},
        {"name": "Google AI", "score": 58}, {"name": "Perplexity", "score": 45},
    ],
    "citation_matrix": {
        "top_left":     {"label": "媒體報導",   "score": 18, "max": 40},
        "top_right":    {"label": "內容深度",   "score": 13, "max": 20},
        "bottom_left":  {"label": "社群口碑",   "score": 12, "max": 20},
        "bottom_right": {"label": "實體辨識度", "score": 9,  "max": 20},
        "center_avg": 52,
    },
}


def _make_stub_pngs(job_dir: Path) -> None:
    """Create minimal 1×1 PNG stubs so download routes can serve files."""
    try:
        from PIL import Image
        for name in ["scorecard.png", "analysis.png"]:
            img = Image.new("RGB", (1, 1), (0, 0, 0))
            img.save(str(job_dir / name))
    except ImportError:
        # If PIL not available, create dummy binary files
        for name in ["scorecard.png", "analysis.png"]:
            (job_dir / name).write_bytes(b"dummy png")


class TestRoutes(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _client(self, tmp_dir: Path):
        import app as app_module
        app_module.TMP_DIR = tmp_dir
        app_module.app.config["TESTING"] = True
        return app_module.app.test_client()

    def test_index_returns_200(self):
        # Mock render_template to avoid TemplateNotFound error
        with patch("app.render_template", return_value="<html>Test</html>"):
            client = self._client(Path(self.tmpdir))
            resp = client.get("/")
            self.assertEqual(resp.status_code, 200)

    def test_score_missing_url_returns_400(self):
        client = self._client(Path(self.tmpdir))
        resp = client.post("/score",
                           data=json.dumps({}),
                           content_type="application/json")
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.data)
        self.assertIn("error", data)

    def test_score_empty_body_returns_400(self):
        client = self._client(Path(self.tmpdir))
        resp = client.post("/score",
                           data="",
                           content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_score_success_returns_job_id(self):
        tmp = Path(self.tmpdir)

        def fake_score_url(url):
            return MOCK_SCORE_DATA

        def fake_generate_scorecard(data, path):
            _make_stub_pngs(Path(path).parent)

        def fake_generate_analysis_card(data, path):
            pass  # stubs already created by fake_generate_scorecard

        with patch("app.score_url", side_effect=fake_score_url), \
             patch("app.generate_scorecard", side_effect=fake_generate_scorecard), \
             patch("app.generate_analysis_card", side_effect=fake_generate_analysis_card):
            client = self._client(tmp)
            resp = client.post("/score",
                               data=json.dumps({"url": "https://example.com"}),
                               content_type="application/json")

        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertIn("job_id", data)
        self.assertEqual(data["geo_score"], 62)
        self.assertEqual(data["brand_name"], "TestBrand")

    def test_download_nonexistent_job_returns_404(self):
        client = self._client(Path(self.tmpdir))
        # Use a valid job_id format but non-existent directory
        resp = client.get("/download/0123456789ab/scorecard")
        self.assertEqual(resp.status_code, 404)

    def test_download_invalid_job_id_returns_400(self):
        client = self._client(Path(self.tmpdir))
        resp = client.get("/download/../../../etc/passwd/scorecard")
        # Flask routing may return 404 for this pattern, which is also acceptable
        self.assertIn(resp.status_code, [400, 404])

    def test_download_scorecard_success(self):
        """Test successful scorecard download."""
        tmp = Path(self.tmpdir)

        def fake_score_url(url):
            return MOCK_SCORE_DATA

        def fake_generate_scorecard(data, path):
            _make_stub_pngs(Path(path).parent)

        def fake_generate_analysis_card(data, path):
            pass

        with patch("app.score_url", side_effect=fake_score_url), \
             patch("app.generate_scorecard", side_effect=fake_generate_scorecard), \
             patch("app.generate_analysis_card", side_effect=fake_generate_analysis_card):
            client = self._client(tmp)
            resp = client.post("/score",
                               data=json.dumps({"url": "https://example.com"}),
                               content_type="application/json")

        self.assertEqual(resp.status_code, 200)
        job_id = json.loads(resp.data)["job_id"]

        # Now download the scorecard
        resp = client.get(f"/download/{job_id}/scorecard")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("GEO-SCORE-CARD.png", resp.headers.get("Content-Disposition", ""))

    def test_download_analysis_success(self):
        """Test successful analysis card download."""
        tmp = Path(self.tmpdir)

        def fake_score_url(url):
            return MOCK_SCORE_DATA

        def fake_generate_scorecard(data, path):
            _make_stub_pngs(Path(path).parent)

        def fake_generate_analysis_card(data, path):
            pass

        with patch("app.score_url", side_effect=fake_score_url), \
             patch("app.generate_scorecard", side_effect=fake_generate_scorecard), \
             patch("app.generate_analysis_card", side_effect=fake_generate_analysis_card):
            client = self._client(tmp)
            resp = client.post("/score",
                               data=json.dumps({"url": "https://example.com"}),
                               content_type="application/json")

        self.assertEqual(resp.status_code, 200)
        job_id = json.loads(resp.data)["job_id"]

        # Now download the analysis card
        resp = client.get(f"/download/{job_id}/analysis")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("GEO-ANALYSIS-CARD.png", resp.headers.get("Content-Disposition", ""))


if __name__ == "__main__":
    unittest.main()
