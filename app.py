import os
import re
import sys
import uuid
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_file, abort

# Add geo-scorecard generator to path
SCORECARD_DIR = Path.home() / ".claude/skills/geo-scorecard/scripts"
sys.path.insert(0, str(SCORECARD_DIR))
from generate_scorecard import generate_scorecard

from scoring import score_url
from generate_analysis_card import generate_analysis_card

app = Flask(__name__)
TMP_DIR = Path(__file__).parent / "tmp"
TMP_DIR.mkdir(exist_ok=True)


def cleanup_old_jobs(max_age_hours: int = 24) -> None:
    cutoff = datetime.now() - timedelta(hours=max_age_hours)
    try:
        for job_dir in TMP_DIR.iterdir():
            if not job_dir.is_dir():
                continue
            try:
                mtime = datetime.fromtimestamp(job_dir.stat().st_mtime)
                if mtime < cutoff:
                    shutil.rmtree(job_dir)
            except Exception as exc:
                app.logger.warning("Failed to clean %s: %s", job_dir, exc)
    except Exception as exc:
        app.logger.error("Cleanup scan failed: %s", exc)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/score", methods=["POST"])
def score():
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    job_id = uuid.uuid4().hex[:12]
    job_dir = TMP_DIR / job_id
    job_dir.mkdir()

    try:
        score_data = score_url(url)
        generate_scorecard(score_data, str(job_dir / "scorecard.png"))
        generate_analysis_card(score_data, str(job_dir / "analysis.png"))
        return jsonify({
            "job_id":     job_id,
            "geo_score":  score_data["geo_score"],
            "brand_name": score_data["brand_name"],
        })
    except Exception as exc:
        app.logger.error("Job %s failed: %s", job_id, exc, exc_info=True)
        shutil.rmtree(job_dir, ignore_errors=True)
        return jsonify({"error": "評分處理失敗，請稍後再試"}), 500


@app.route("/download/<job_id>/scorecard")
def download_scorecard(job_id: str):
    if not re.match(r'^[a-f0-9]{12}$', job_id):
        abort(400)
    path = TMP_DIR / job_id / "scorecard.png"
    if not path.exists():
        abort(404)
    return send_file(path, as_attachment=True, download_name="GEO-SCORE-CARD.png")


@app.route("/download/<job_id>/analysis")
def download_analysis(job_id: str):
    if not re.match(r'^[a-f0-9]{12}$', job_id):
        abort(400)
    path = TMP_DIR / job_id / "analysis.png"
    if not path.exists():
        abort(404)
    return send_file(path, as_attachment=True, download_name="GEO-ANALYSIS-CARD.png")


if __name__ == "__main__":
    cleanup_old_jobs()
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=False, port=port)
