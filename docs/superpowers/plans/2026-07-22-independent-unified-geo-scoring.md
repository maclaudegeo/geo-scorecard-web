# Independent Unified GEO Scoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Scorecard Web independently calculate the same five GEO dimensions as GEO Dashboard without calling or reading Dashboard results.

**Architecture:** Add self-contained audit and brand-authority modules to Scorecard Web by porting the Dashboard's current production rules exactly. Keep the existing Claude scorecard call for brand identification, diagnosis, reasons, and four estimated platform values, but override all five shared dimension scores and the four brand-matrix values with the independent audit output before calculating the existing Scorecard total.

**Tech Stack:** Python 3, Flask, requests, httpx, Anthropic API, OpenAI API, Gemini API, Firecrawl API, unittest/pytest

---

### Task 1: Port the objective Dashboard audit

**Files:**
- Create: `dashboard_audit.py`
- Create: `tests/test_dashboard_audit.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Write failing parity tests**

Create tests that patch all network boundaries and assert the Dashboard's exact current calculations:

```python
from unittest.mock import MagicMock, patch

from dashboard_audit import run_geo_audit


@patch("dashboard_audit.requests.head")
@patch("dashboard_audit._extract_schema_from_html")
@patch("dashboard_audit._firecrawl_scrape_full")
@patch("dashboard_audit.fetch_llms_txt")
@patch("dashboard_audit.fetch_robots_txt")
def test_run_geo_audit_matches_dashboard_weights(
    robots, llms, scrape, schema, head
):
    robots.return_value = {"exists": True}
    llms.return_value = {"llms_txt": {"exists": True}}
    scrape.return_value = {
        "status_code": 200,
        "title": "Moreson",
        "description": "description",
        "canonical": "https://example.com",
        "h1_tags": ["Moreson"],
        "markdown": "x" * 2501,
        "raw_meta": {"ogTitle": "Moreson"},
    }
    schema.return_value = [{"@type": "Organization", "sameAs": []}]
    head.return_value = MagicMock(headers={
        "strict-transport-security": "x",
        "x-content-type-options": "x",
        "x-frame-options": "x",
    })

    assert run_geo_audit("https://example.com", "Moreson") == {
        "ai_platform": 70,
        "content": 100,
        "technical": 90,
        "brand": 0,
        "schema": 65,
    }
```

This deliberately preserves the Dashboard's current `llms.get("exists")` and `robots.get("allows")` behavior so the two independent services stay equal.

- [ ] **Step 2: Run the test and verify it fails**

Run: `pytest tests/test_dashboard_audit.py -v`

Expected: collection fails with `ModuleNotFoundError: No module named 'dashboard_audit'`.

- [ ] **Step 3: Implement the independent audit module**

Create `dashboard_audit.py` and port the complete implementations of `fetch_robots_txt`, `fetch_llms_txt`, `_firecrawl_scrape_full`, `_extract_schema_from_html`, and `run_geo_audit` exactly from:

- `../geo-visibility-dashboard/fetch_page.py:196-327`
- `../geo-visibility-dashboard/server.py:153-200`
- `../geo-visibility-dashboard/server.py:203-287`

The module reads `FIRECRAWL_API_KEY` from the environment. Preserve Dashboard's empty-metadata fallback when Firecrawl fails and never ask Claude to invent replacement scores.

- [ ] **Step 4: Add runtime dependencies**

Add the dependencies used by the ported Dashboard logic:

```text
httpx>=0.27
python-dotenv>=1.0
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_dashboard_audit.py -v`

Expected: all objective audit parity tests pass.

- [ ] **Step 6: Commit**

```bash
git add dashboard_audit.py tests/test_dashboard_audit.py requirements.txt
git commit -m "feat: port dashboard GEO audit rules"
```

### Task 2: Port Dashboard brand-authority scoring

**Files:**
- Create: `brand_authority.py`
- Create: `tests/test_brand_authority.py`

- [ ] **Step 1: Write failing parser and averaging tests**

```python
from unittest.mock import patch

from brand_authority import _parse_authority_response, score_brand_authority_ai


RAW = """媒體報導：20/40
社群口碑：10/20
內容深度：12/20
實體辨識度：14/20
總分：56/100
媒體報導問題：報導不足
媒體報導建議：增加第三方報導"""


def test_parse_authority_response_matches_dashboard():
    parsed = _parse_authority_response(RAW)
    assert parsed["media"] == 20
    assert parsed["community"] == 10
    assert parsed["content"] == 12
    assert parsed["identity"] == 14
    assert parsed["total"] == 56


@patch("brand_authority._query_claude", return_value=RAW)
@patch("brand_authority._query_gemini", return_value=RAW)
@patch("brand_authority._query_chatgpt", return_value=RAW)
def test_three_platform_average_matches_dashboard(*_):
    result = score_brand_authority_ai("Moreson")
    assert result["avg"] == {
        "media": 20, "community": 10, "content": 12, "identity": 14
    }
    assert result["total"] == 56
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `pytest tests/test_brand_authority.py -v`

Expected: collection fails with `ModuleNotFoundError: No module named 'brand_authority'`.

- [ ] **Step 3: Implement exact model parity**

Port `AUTHORITY_PROMPT`, `_parse_authority_response`, `_query_chatgpt`, `_query_gemini`, `_query_claude`, and `score_brand_authority_ai` from `../geo-visibility-dashboard/geo_audit.py:192-390`. Preserve the exact models (`gpt-4o`, `gemini-2.5-flash`, `claude-haiku-4-5`), ChatGPT temperature `0.3`, parsing expressions, failed-platform exclusion, rounded dimension averages, and rounded total.

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_brand_authority.py -v`

Expected: all parser and averaging tests pass.

- [ ] **Step 5: Commit**

```bash
git add brand_authority.py tests/test_brand_authority.py
git commit -m "feat: port dashboard brand authority scoring"
```

### Task 3: Make Scorecard use authoritative shared-dimension scores

**Files:**
- Modify: `scoring.py`
- Modify: `tests/test_scoring.py`

- [ ] **Step 1: Write a failing orchestration test**

Patch `_fetch_page`, the Anthropic response, `run_geo_audit`, and `score_brand_authority_ai`. Assert that `score_url()` ignores Claude's five dimension guesses and returns the independent Dashboard-equivalent values:

```python
@patch("scoring.score_brand_authority_ai")
@patch("scoring.run_geo_audit")
@patch("scoring.anthropic.Anthropic")
@patch("scoring._fetch_page", return_value=("<html></html>", ""))
def test_score_url_uses_dashboard_dimensions(fetch, anthropic_client, audit, authority):
    anthropic_client.return_value.messages.create.return_value.content[0].text = json.dumps(MOCK_CLAUDE_JSON)
    audit.return_value = {
        "ai_platform": 70, "content": 80, "technical": 75,
        "brand": 0, "schema": 55,
    }
    authority.return_value = {
        "total": 56,
        "avg": {"media": 20, "content": 12, "community": 10, "identity": 14},
        "platforms": {},
    }

    result = score_url("https://example.com")
    dimensions = {item["label"]: item["score"] for item in result["dimensions"]}
    assert dimensions == {
        "AI 平台準備度": 70,
        "內容品質 E-E-A-T": 80,
        "技術基礎": 75,
        "品牌權威度": 56,
        "Schema 結構化資料": 55,
    }
    assert result["geo_score"] == 69
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `pytest tests/test_scoring.py::TestScoreUrl::test_score_url_uses_dashboard_dimensions -v`

Expected: the returned dimensions still contain Claude's guessed values.

- [ ] **Step 3: Override only authoritative score fields**

After parsing the Claude response, independently run both Dashboard-equivalent modules and replace the shared values:

```python
audit = run_geo_audit(url, scores["brand_name"])
authority = score_brand_authority_ai(scores["brand_name"])
avg = authority["avg"]

scores.update({
    "ai_citability": audit["ai_platform"],
    "content_eeat": audit["content"],
    "technical": audit["technical"],
    "schema": audit["schema"],
    "media_coverage": avg["media"],
    "content_depth": avg["content"],
    "social_presence": avg["community"],
    "entity_recognition": avg["identity"],
})
```

Retain Claude's brand name, diagnosis, reason text, and four Scorecard-only platform estimates. `build_score_data()` continues to sum the four brand matrix values and use the existing 25/25/20/20/10 total formula.

- [ ] **Step 4: Run the Scorecard tests**

Run: `pytest tests/test_scoring.py tests/test_app.py tests/test_analysis_card.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add scoring.py tests/test_scoring.py
git commit -m "feat: align scorecard with dashboard scoring"
```

### Task 4: Verify Moreson independently

**Files:**
- Create: `tests/test_moreson_parity.py`
- Modify: `.env.example`

- [ ] **Step 1: Document required independent credentials**

Add these names without values to `.env.example`:

```text
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GEMINI_API_KEY=
FIRECRAWL_API_KEY=
```

- [ ] **Step 2: Add a parity harness**

The integration test imports Dashboard `run_geo_audit` from its sibling checkout and Scorecard `run_geo_audit`, runs both against the same URL, and compares all objective fields:

```python
TARGET_URL = "https://www.moreson.com.tw/moreson/"

assert scorecard_result["ai_platform"] == dashboard_result["ai_platform"]
assert scorecard_result["content"] == dashboard_result["content"]
assert scorecard_result["technical"] == dashboard_result["technical"]
assert scorecard_result["schema"] == dashboard_result["schema"]
```

Mark the test `integration` and skip it unless `FIRECRAWL_API_KEY` is set, so normal Render builds do not spend API quota.

- [ ] **Step 3: Run the live parity test**

Run: `pytest tests/test_moreson_parity.py -v -m integration`

Expected: the four objective dimensions match exactly.

- [ ] **Step 4: Run a complete live Scorecard generation**

Run `score_url("https://www.moreson.com.tw/moreson/")`, generate both PNG files in a temporary directory, and verify both files are non-empty. Record the five scores and weighted total in the command output.

- [ ] **Step 5: Run the complete test suite**

Run: `pytest -v`

Expected: all non-integration tests pass; live integration passes when credentials are loaded.

- [ ] **Step 6: Commit**

```bash
git add .env.example tests/test_moreson_parity.py
git commit -m "test: verify independent Moreson scoring parity"
```
