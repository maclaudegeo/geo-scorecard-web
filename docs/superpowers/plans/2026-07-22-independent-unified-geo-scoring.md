# /report Unified GEO Scoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make both GEO websites independently calculate the same five `/report` scores, while keeping Dashboard's real AI visibility analysis and adding evidence-based Taiwan brand authority.

**Architecture:** Add the same framework-independent `report_scoring.py` module to both repositories. It builds one evidence snapshot, applies explicit `/report` rubrics, performs Taiwan brand searches, and returns a versioned score payload; each web app only maps that payload into its existing response and output formats.

**Tech Stack:** Python 3, Flask/FastAPI, requests, httpx, lxml, pytest, Firecrawl, SerpAPI/byCrawl with Google News RSS fallback

---

## File Map

- `geo-visibility-dashboard/report_scoring.py`: canonical `/report` evidence collection and scoring engine.
- `geo-visibility-dashboard/tests/test_report_scoring.py`: rubric, parser, fallback, and total-weight tests.
- `geo-visibility-dashboard/server.py`: replace simplified shared scores with the report engine; preserve real AI visibility.
- `geo-visibility-dashboard/scorer.py`: use scaled `/report` weights plus AI visibility.
- `scorecard-web/report_scoring.py`: independently deployable identical scoring engine.
- `scorecard-web/scoring.py`: map report scores and platform details into existing card data.
- `scorecard-web/tests/test_report_scoring.py`: same rubric contract tests.
- `scorecard-web/tests/test_scoring.py`: orchestration and `/report` total tests.
- `scorecard-web/tests/test_moreson_parity.py`: compare both independent engines on the acceptance URL.

### Task 1: Lock the evidence contract and edge cases

**Files:**
- Create: `geo-visibility-dashboard/tests/test_report_scoring.py`
- Create: `scorecard-web/tests/test_report_scoring.py`

- [ ] **Step 1: Write failing snapshot tests**

Cover URL normalization, robots statuses, nested `llms_txt.exists`, JSON-LD lists and `@graph`, case-sensitive valid Schema types, invalid values such as `address: "暫無"`, internal-page selection capped at 10, and network failure represented as `unknown` rather than a guessed pass.

```python
def test_schema_evidence_flattens_graph_and_flags_invalid_type_case():
    evidence = parse_schema_blocks([
        {"@graph": [
            {"@type": "localBusiness", "address": "暫無"},
            {"@type": "WebSite", "potentialAction": {"@type": "SearchAction"}},
        ]}
    ])
    assert evidence.types == ("localBusiness", "WebSite")
    assert "invalid_type_case:localBusiness" in evidence.issues
    assert "placeholder_value:address" in evidence.issues
```

- [ ] **Step 2: Run tests and verify RED**

Run in each repository: `pytest tests/test_report_scoring.py -v`

Expected: import fails because `report_scoring` does not exist.

- [ ] **Step 3: Implement immutable evidence models and parsers**

Create dataclasses for `PageEvidence`, `SchemaEvidence`, `BrandEvidence`, and `ReportSnapshot`. Add pure parsers for robots.txt, llms.txt, HTML metadata, links, headings, JSON-LD, security headers, and timing data. Every unknown field must remain `None`/`unknown`; never convert an exception into a positive score.

- [ ] **Step 4: Run both parser suites and verify GREEN**

Run: `pytest tests/test_report_scoring.py -v`

Expected: all snapshot/parser tests pass in both repositories.

### Task 2: Implement the four website-based `/report` rubrics

**Files:**
- Modify: both `report_scoring.py`
- Modify: both `tests/test_report_scoring.py`

- [ ] **Step 1: Write failing rubric tests**

Use fixed snapshots to assert every category maximum and a sparse Moreson-like case. Tests must verify:

```python
assert score_content(snapshot).breakdown.keys() == {
    "experience", "expertise", "authoritativeness", "trustworthiness",
}
assert score_technical(snapshot).maxima == {
    "crawlability": 15, "indexability": 12, "security": 10,
    "url_structure": 8, "mobile": 10, "core_web_vitals": 15,
    "ssr": 15, "page_speed": 15,
}
assert score_schema(snapshot).maximum == 100
assert set(score_platforms(snapshot).platforms) == {
    "google_ai", "chatgpt", "perplexity", "gemini", "bing_copilot",
}
```

- [ ] **Step 2: Verify rubric tests fail for missing scorers**

Run: `pytest tests/test_report_scoring.py -v`

- [ ] **Step 3: Implement explicit criterion scoring**

Implement each table from the installed `/report` source skills. Every awarded point includes `criterion`, `points`, `max_points`, and `evidence`; no function accepts a model-generated total. Platform readiness is the rounded average of five platform scores. Content applies the four 25-point E-E-A-T tables and topical-authority modifier. Technical uses the exact eight maxima. Schema uses the exact 12 criteria and validates type names and required properties.

- [ ] **Step 4: Verify all rubric totals and caps**

Run both test suites and confirm scores remain integers between 0 and 100 and equal the sum of their breakdowns.

### Task 3: Implement evidence-based Taiwan brand authority

**Files:**
- Modify: both `report_scoring.py`
- Modify: both `tests/test_report_scoring.py`

- [ ] **Step 1: Write failing Taiwan-search tests**

Patch the search boundaries with duplicated press releases, independent Tier 1/Tier 2 articles, stale coverage, official social accounts, and third-party PTT/Dcard/Threads mentions. Assert exact-match brand filtering, URL deduplication, recency, source tiering, and that official posts do not count as third-party community evidence.

```python
def test_brand_score_uses_one_evidence_set_and_never_model_memory():
    result = score_brand_authority(TAIWAN_EVIDENCE)
    assert result.maximums == {
        "media": 40, "content_depth": 20,
        "social": 20, "entity": 20,
    }
    assert result.score == sum(result.breakdown.values())
    assert result.source == "taiwan_search"
```

- [ ] **Step 2: Verify tests fail before search/scoring exists**

Run: `pytest tests/test_report_scoring.py -k brand -v`

- [ ] **Step 3: Add Taiwan evidence collection**

Query Google News RSS with `hl=zh-TW&gl=TW`, query configured SerpAPI/byCrawl with `gl=tw&hl=zh-tw`, and search the approved Taiwan media and social domains. Search all detected aliases. Normalize URLs, group syndicated copies, distinguish owned/official domains, and retain title, snippet, source, date, and query provenance.

- [ ] **Step 4: Add strict 40/20/20/20 scoring**

Media uses independent article count, tier, recency, and syndicated-content penalties. Content depth uses evidence from external article titles/snippets/pages. Social uses only third-party discussion/engagement evidence. Entity compares brand identity across website, Schema, media, and third-party profiles. Missing search services score only from available evidence and return warnings; they never invoke an LLM fallback.

- [ ] **Step 5: Run brand and failure-path tests**

Expected: deterministic results and explicit `data_incomplete` warnings when a source is unavailable.

### Task 4: Integrate Dashboard without changing real AI visibility

**Files:**
- Modify: `geo-visibility-dashboard/server.py`
- Modify: `geo-visibility-dashboard/scorer.py`
- Test: `geo-visibility-dashboard/tests/test_server_scoring.py`

- [ ] **Step 1: Write failing integration tests**

Patch `run_report_audit` and `_run_engine_analysis`. Assert Dashboard uses report values for `ai_platform`, `content`, `technical`, `schema`, and `brand`, while `visibility_score`, engine responses, SOV, and citations remain untouched.

- [ ] **Step 2: Replace only the simplified shared audit**

Call `run_report_audit(url, brand_name, aliases)` once per job and map its five scores into the existing `geo_scores` keys. Remove the three-AI brand total from the scoring path, but leave unrelated report-generation text code intact.

- [ ] **Step 3: Correct Dashboard weights**

Update `calculate_final_score` to use `20/20/20/16/12/12` for real visibility, platform, content, technical, schema, and brand. Add a test that recomputes the returned total from displayed values.

- [ ] **Step 4: Run Dashboard tests**

Run: `pytest -v`

Expected: report integration passes and existing AI visibility behavior remains green.

### Task 5: Integrate Scorecard Web and remove guessed dimension totals

**Files:**
- Modify: `scorecard-web/scoring.py`
- Modify: `scorecard-web/requirements.txt`
- Modify: `scorecard-web/tests/test_scoring.py`
- Delete: `scorecard-web/dashboard_audit.py`
- Delete: `scorecard-web/tests/test_dashboard_audit.py`

- [ ] **Step 1: Write failing Scorecard orchestration tests**

Assert `score_url()` gets all five dimensions and four visible platform cards from `run_report_audit`, does not ask Claude for dimension scores, and does not call real AI visibility endpoints.

- [ ] **Step 2: Replace the free-form Claude scoring prompt**

Use the report engine for scores and evidence-derived reasons. Preserve brand name, existing response structure, PNG fields, routes, and filenames. Remove the Anthropic runtime dependency if no remaining Scorecard path needs it.

- [ ] **Step 3: Correct Scorecard weights**

Change the total to `/report` order: platform 25%, content 25%, technical 20%, schema 15%, brand 15%. Keep the visual row order unchanged.

- [ ] **Step 4: Run all Scorecard tests and image generation tests**

Run: `pytest -v`

Expected: all endpoint, scoring, scorecard PNG, and analysis PNG tests pass.

### Task 6: Cross-repository parity and live Moreson acceptance

**Files:**
- Create: `scorecard-web/tests/test_moreson_parity.py`
- Modify: both `.env.example`/deployment environment documentation as needed

- [ ] **Step 1: Add algorithm-version parity test**

Both modules expose the same `REPORT_SCORING_VERSION`. Load each independently and assert identical version, category maxima, and fixed-fixture outputs.

- [ ] **Step 2: Run the live Moreson audit once in each repository**

Target: `https://www.moreson.com.tw/moreson/`. Capture the five common scores, breakdowns, evidence URLs, warnings, and totals. Assert the five common raw scores are identical.

- [ ] **Step 3: Verify output artifacts**

Generate Dashboard response/PDF and both Scorecard PNGs. Confirm non-empty files and that displayed scores equal API payload scores.

- [ ] **Step 4: Run full QA and review**

Run all tests, inspect secrets/logging, network timeout behavior, SSRF protections, malformed HTML/JSON-LD handling, duplicate search results, and failure fallbacks. Fix every critical or warning finding, then rerun all tests.

### Task 7: Deploy and smoke test both public services

**Files:**
- Modify deployment files only if required by dependencies or start commands.

- [ ] **Step 1: Commit each repository's tested changes**

Keep Dashboard and Scorecard commits separate. Do not include local `.env`, API logs, temporary cards, or unrelated dirty files.

- [ ] **Step 2: Push and deploy both Render services**

Confirm the required search credentials are configured independently for both services. Do not add a Claude key to Scorecard unless another retained feature requires it.

- [ ] **Step 3: Public smoke tests**

Open both public URLs, run Moreson, verify five shared scores match, verify Dashboard AI visibility still runs, and download all expected artifacts.

- [ ] **Step 4: Record final URLs and evidence**

Return the two working URLs, five Moreson common scores, both final totals, deployment revisions, and verification results.
