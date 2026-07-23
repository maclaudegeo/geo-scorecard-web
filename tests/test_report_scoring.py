from unittest.mock import Mock, patch

import pytest

from report_scoring import (
    BrandEvidence,
    PageEvidence,
    ReportSnapshot,
    ScoreResult,
    SchemaEvidence,
    SearchHit,
    parse_schema_blocks,
    score_brand_authority,
    score_content,
    score_platforms,
    score_schema,
    score_technical,
    validate_public_url,
    _detect_brand,
)


def test_schema_flattens_graph_and_flags_invalid_values():
    evidence = parse_schema_blocks([
        {
            "@graph": [
                {"@type": "localBusiness", "address": "暫無"},
                {
                    "@type": "WebSite",
                    "potentialAction": {"@type": "SearchAction"},
                },
            ]
        }
    ])

    assert evidence.types == ("localBusiness", "WebSite")
    assert "invalid_type_case:localBusiness" in evidence.issues
    assert "placeholder_value:address" in evidence.issues


def test_schema_scores_nodes_with_multiple_types():
    schema = parse_schema_blocks([
        {
            "@type": ["Organization", "WebSite"],
            "name": "MicroAd Taiwan",
            "url": "https://microad.tw/",
            "potentialAction": {"@type": "SearchAction"},
        }
    ])

    result = score_schema(schema)

    assert result.breakdown["organization_person"]["points"] == 15
    assert result.breakdown["website_searchaction"]["points"] == 5


def test_schema_rubric_does_not_treat_invalid_localbusiness_as_valid():
    schema = parse_schema_blocks([
        {"@type": "localBusiness", "address": "暫無", "sameAs": ["https://example.com"]},
        {"@type": "WebSite", "potentialAction": {"@type": "SearchAction"}},
    ])
    result = score_schema(schema)

    assert result.maximum == 100
    assert result.score < 40
    assert result.breakdown["business_type"]["points"] == 0
    assert result.breakdown["website_searchaction"]["points"] == 5


def test_taiwan_brand_authority_deduplicates_and_ignores_owned_social():
    evidence = BrandEvidence(
        brand_name="Moreson",
        owned_domains=("moreson.com.tw",),
        media_hits=(
            SearchHit(
                title="Moreson 深度專訪",
                url="https://www.cna.com.tw/news/a/1",
                source="中央社",
                snippet="專訪品牌團隊並分析市場數據與實際案例。",
                published="2026-06-01",
                category="media",
            ),
            SearchHit(
                title="Moreson 深度專訪",
                url="https://www.cna.com.tw/news/a/1?utm_source=x",
                source="中央社",
                snippet="同一篇轉載。",
                published="2026-06-01",
                category="media",
            ),
        ),
        social_hits=(
            SearchHit(
                title="Moreson 官方 Instagram",
                url="https://instagram.com/moreson",
                source="Instagram",
                snippet="官方帳號",
                published="",
                category="social",
                owned=True,
            ),
            SearchHit(
                title="使用 Moreson 的心得",
                url="https://www.dcard.tw/f/marketing/p/1",
                source="Dcard",
                snippet="實際使用心得與比較。",
                published="2026-05-01",
                category="social",
            ),
        ),
        entity_sources=("website", "schema", "media"),
        identity_consistent=True,
        warnings=(),
    )

    result = score_brand_authority(evidence)

    assert result.source == "taiwan_search"
    assert result.maximums == {
        "media": 40,
        "content_depth": 20,
        "social": 20,
        "entity": 20,
    }
    assert result.evidence_counts["media"] == 1
    assert result.evidence_counts["third_party_social"] == 1
    assert result.breakdown["content_depth"] == 0
    assert result.score == sum(result.breakdown.values())


def test_brand_content_depth_requires_site_content_not_media_headlines():
    page = PageEvidence(
        url="https://example.com/case-study",
        status_code=200,
        title="實際案例研究",
        text=("本案例說明研究方法、執行流程與具體成效 35%。" * 40),
        raw_html="<h1>實際案例研究</h1>",
    )
    evidence = BrandEvidence(
        brand_name="Example",
        media_hits=(SearchHit("Example 深度專訪", "https://cna.com.tw/a/1"),),
    )
    snapshot = ReportSnapshot(
        url="https://example.com/",
        brand_name="Example",
        pages=(page,),
        brand=evidence,
    )

    assert score_brand_authority(evidence, snapshot).breakdown["content_depth"] > 0


def test_brand_detection_ignores_antibot_page_title_and_uses_domain():
    page = PageEvidence(
        url="https://tw.iherb.com/",
        status_code=403,
        title="Just a moment...",
        text="Performing security verification",
        raw_html="<title>Just a moment...</title>",
    )

    assert _detect_brand(page, "tw.iherb.com") == "iherb"


def test_brand_detection_extracts_domain_brand_from_long_marketing_title():
    page = PageEvidence(
        url="https://tw.iherb.com/",
        status_code=200,
        title="iHerb 台灣官方網站｜保健食品與天然產品線上購物",
        text="iHerb 提供健康養生商品。",
        raw_html="<title>iHerb 台灣官方網站</title>",
    )

    assert _detect_brand(page, "tw.iherb.com") == "iHerb"


def test_brand_detection_reads_organization_with_multiple_types():
    page = PageEvidence(
        url="https://microad.tw/",
        status_code=200,
        title="",
        text="",
        raw_html="",
        schema=parse_schema_blocks([
            {"@type": ["Organization", "Corporation"], "name": "MicroAd Taiwan"}
        ]),
    )

    assert _detect_brand(page, "microad.tw") == "MicroAd Taiwan"


def test_snapshot_keeps_unknown_network_signals_unknown():
    snapshot = ReportSnapshot.empty("https://example.com", "Example")

    assert snapshot.robots_exists is None
    assert snapshot.llms_exists is None
    assert snapshot.pages == ()


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/admin",
    "http://169.254.169.254/latest/meta-data/",
    "http://[::1]/",
    "file:///etc/passwd",
    "https://user:password@example.com/",
])
def test_public_url_validation_rejects_private_or_unsafe_targets(url):
    with pytest.raises(ValueError, match="公開網址"):
        validate_public_url(url)


@patch("report_scoring.socket.getaddrinfo")
def test_public_url_validation_accepts_public_https(dns):
    dns.return_value = [(2, 1, 6, "", ("8.8.8.8", 443))]

    assert validate_public_url("https://example.com/path") == "https://example.com/path"
    assert validate_public_url("https://example.com/path/") == "https://example.com/path/"


def test_report_rubrics_expose_the_installed_category_maxima():
    page = PageEvidence(
        url="https://example.com/",
        status_code=200,
        title="Example",
        description="Example description",
        canonical="https://example.com/",
        lang="zh-TW",
        text="我們實測方法與案例，成效提升 35%。聯絡信箱 hello@example.com。",
        headings=("Example", "常見問題"),
        links=("https://example.com/about",),
        external_links=("https://www.cna.com.tw/news/a/1",),
        has_viewport=True,
        schema=SchemaEvidence(),
        response_headers=(("strict-transport-security", "max-age=31536000"),),
        elapsed_ms=500,
        byte_size=200_000,
        raw_html='<meta name="viewport" content="width=device-width"><h1>Example</h1>',
    )
    snapshot = ReportSnapshot(
        url="https://example.com/",
        brand_name="Example",
        pages=(page,),
        robots_exists=True,
        crawler_status=(("GPTBot", "not_blocked"),),
        sitemap_exists=True,
        brand=BrandEvidence("Example"),
    )
    content = score_content(snapshot)
    technical = score_technical(snapshot)
    schema = score_schema(SchemaEvidence())
    platforms = score_platforms(snapshot, content, schema, technical)

    assert set(content.breakdown) == {
        "experience", "expertise", "authoritativeness", "trustworthiness",
    }
    assert {key: value["max_points"] for key, value in technical.breakdown.items()} == {
        "crawlability": 15,
        "indexability": 12,
        "security": 10,
        "url_structure": 8,
        "mobile": 10,
        "core_web_vitals": 15,
        "ssr": 15,
        "page_speed": 15,
    }
    assert set(platforms["platforms"]) == {
        "google_ai", "chatgpt", "perplexity", "gemini", "bing_copilot",
    }


def test_generic_marketing_words_do_not_create_high_eeat_score():
    page = PageEvidence(
        url="https://example.com/",
        status_code=200,
        text=("我們是專家顧問，提供案例、方法、成果與客戶評價 99%。例如專業服務。" * 80),
        external_links=("https://example.org/source",),
        images=20,
        raw_html="<h1>專業服務</h1>",
    )
    snapshot = ReportSnapshot(
        url="https://example.com/",
        brand_name="Example",
        pages=(page,),
        brand=BrandEvidence("Example"),
    )

    assert score_content(snapshot).score <= 30


def test_author_credentials_must_exist_on_the_same_authored_page():
    authored = PageEvidence(
        url="https://example.com/article",
        status_code=200,
        text="一般文章內容" * 300,
        has_author=True,
        raw_html="<article><p>一般文章內容</p></article>",
    )
    unrelated = PageEvidence(
        url="https://example.com/product",
        status_code=200,
        text="產品通過品質認證",
        raw_html="<p>產品通過品質認證</p>",
    )
    snapshot = ReportSnapshot(
        url="https://example.com/",
        brand_name="Example",
        pages=(authored, unrelated),
        brand=BrandEvidence("Example"),
    )

    result = score_content(snapshot)

    assert "credentials=False" in result.breakdown["expertise"]["evidence"]


def test_technical_score_does_not_assume_unmeasured_checks_pass():
    page = PageEvidence(
        url="https://example.com/",
        status_code=200,
        title="Example",
        description="Description",
        lang="zh-TW",
        text="可讀內容" * 400,
        links=("https://example.com/a", "https://example.com/b", "https://example.com/c"),
        has_viewport=True,
        elapsed_ms=500,
        byte_size=100_000,
        raw_html="<style>@media(max-width:600px){}</style><h1>Example</h1>",
    )
    snapshot = ReportSnapshot(
        url="https://example.com/",
        brand_name="Example",
        pages=(page,),
        robots_exists=False,
        sitemap_exists=False,
        brand=BrandEvidence("Example"),
    )

    assert score_technical(snapshot).score <= 45


def test_platform_readiness_does_not_inherit_other_category_scores():
    snapshot = ReportSnapshot.empty("https://example.com/", "Example")
    perfect = ScoreResult(100, 100, {})

    result = score_platforms(snapshot, perfect, perfect, perfect)

    assert result["score"] == 0
    assert set(result["platforms"].values()) == {0}
