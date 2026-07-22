"""Evidence-based implementation of the installed `/geo report` rubrics."""

from __future__ import annotations

import json
import ipaddress
import os
import re
import socket
import time
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from email.utils import parsedate_to_datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import requests


REPORT_SCORING_VERSION = "2026-07-22.2"
USER_AGENT = "Mozilla/5.0 (compatible; GEO-Report-Audit/2.0; +https://microad.tw/)"
REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7",
}
PLACEHOLDERS = {"", "n/a", "na", "none", "null", "暫無", "無", "待補", "-", "--"}

VALID_SCHEMA_TYPES = {
    "Article", "BlogPosting", "BreadcrumbList", "ContactPoint", "Corporation",
    "CreativeWork", "Event", "FAQPage", "HowTo", "ImageObject", "ItemList",
    "LocalBusiness", "NewsArticle", "Offer", "Organization", "Person", "Place",
    "Product", "ProfessionalService", "Question", "Review", "SearchAction",
    "Service", "SoftwareApplication", "VideoObject", "WebPage", "WebSite",
}
DEPRECATED_SCHEMA_TYPES = {"DataFeedItem", "MedicalAudience", "UserComments"}
BUSINESS_SCHEMA_TYPES = {
    "LocalBusiness", "Corporation", "ProfessionalService", "Product", "Service",
    "SoftwareApplication",
}
ARTICLE_SCHEMA_TYPES = {"Article", "BlogPosting", "NewsArticle"}

MEDIA_TIERS = {
    "cna.com.tw": 1, "udn.com": 1, "udn.com.tw": 1,
    "technews.tw": 2, "bnext.com.tw": 2, "ctee.com.tw": 2, "edn.com.tw": 2,
    "cw.com.tw": 2, "businessweekly.com.tw": 2,
    "vogue.com.tw": 3, "elle.com.tw": 3, "popdaily.com.tw": 3, "gq.com.tw": 3,
    "ettoday.net": 4, "ltn.com.tw": 4, "chinatimes.com": 4,
    "tw.news.yahoo.com": 4, "inside.com.tw": 5, "blog.104.com.tw": 5,
}
SOURCE_TIERS = {
    "中央社": 1, "聯合新聞網": 1, "聯合報": 1,
    "科技新報": 2, "數位時代": 2, "工商時報": 2, "經濟日報": 2,
    "天下雜誌": 2, "商業周刊": 2, "VOGUE": 3, "ELLE": 3,
    "POPDAILY": 3, "GQ": 3, "ETTODAY": 4, "自由時報": 4,
    "中時新聞網": 4, "YAHOO奇摩新聞": 4, "INSIDE": 5, "104職場力": 5,
}
SOCIAL_DOMAINS = {
    "ptt.cc": "PTT", "dcard.tw": "Dcard", "threads.net": "Threads",
    "instagram.com": "Instagram", "youtube.com": "YouTube", "youtu.be": "YouTube",
    "facebook.com": "Facebook", "linkedin.com": "LinkedIn",
}


def _clamp(value: float, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, round(value)))


def _host(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _normalize_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [(k, v) for k, v in query if not k.lower().startswith("utm_")]
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    return urllib.parse.urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), path.rstrip("/") or "/",
         urllib.parse.urlencode(query), "")
    )


def validate_public_url(url: str) -> str:
    """Return a normalized public web URL or reject unsafe network targets."""
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError
        if parsed.username or parsed.password:
            raise ValueError
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except (TypeError, ValueError):
        raise ValueError("請輸入可公開連線的 HTTP/HTTPS 公開網址") from None

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValueError("請輸入可公開連線的 HTTP/HTTPS 公開網址")

    try:
        addresses = {ipaddress.ip_address(hostname)}
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(item[4][0])
                for item in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
            }
        except (OSError, ValueError):
            raise ValueError("網址目前無法解析為公開網址") from None

    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("請輸入可公開連線的 HTTP/HTTPS 公開網址")
    return urllib.parse.urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", parsed.query, "")
    )


def _get_public(url: str, timeout: int) -> requests.Response:
    current = validate_public_url(url)
    for _ in range(6):
        response = requests.get(
            current,
            headers=REQUEST_HEADERS,
            timeout=timeout,
            allow_redirects=False,
        )
        if response.status_code not in {301, 302, 303, 307, 308}:
            return response
        location = response.headers.get("location")
        if not location:
            return response
        current = validate_public_url(urllib.parse.urljoin(current, location))
    raise ValueError("網址轉址次數過多")


def _valid_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in PLACEHOLDERS
    if isinstance(value, (list, tuple, dict)):
        return bool(value)
    return True


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    source: str = ""
    snippet: str = ""
    published: str = ""
    category: str = "media"
    owned: bool = False


@dataclass(frozen=True)
class BrandEvidence:
    brand_name: str
    owned_domains: Tuple[str, ...] = ()
    media_hits: Tuple[SearchHit, ...] = ()
    social_hits: Tuple[SearchHit, ...] = ()
    entity_sources: Tuple[str, ...] = ()
    identity_consistent: bool = False
    warnings: Tuple[str, ...] = ()


@dataclass(frozen=True)
class SchemaEvidence:
    nodes: Tuple[Dict[str, Any], ...] = ()
    types: Tuple[str, ...] = ()
    issues: Tuple[str, ...] = ()
    jsonld_blocks: int = 0


@dataclass(frozen=True)
class PageEvidence:
    url: str
    status_code: Optional[int] = None
    title: str = ""
    description: str = ""
    canonical: str = ""
    lang: str = ""
    text: str = ""
    headings: Tuple[str, ...] = ()
    links: Tuple[str, ...] = ()
    external_links: Tuple[str, ...] = ()
    images: int = 0
    images_with_alt: int = 0
    images_with_dimensions: int = 0
    has_viewport: bool = False
    has_author: bool = False
    has_date: bool = False
    schema: SchemaEvidence = field(default_factory=SchemaEvidence)
    response_headers: Tuple[Tuple[str, str], ...] = ()
    elapsed_ms: Optional[int] = None
    byte_size: Optional[int] = None
    raw_html: str = ""

    @property
    def headers(self) -> Dict[str, str]:
        return dict(self.response_headers)


@dataclass(frozen=True)
class ReportSnapshot:
    url: str
    brand_name: str
    pages: Tuple[PageEvidence, ...] = ()
    robots_exists: Optional[bool] = None
    robots_content: str = ""
    crawler_status: Tuple[Tuple[str, str], ...] = ()
    llms_exists: Optional[bool] = None
    sitemap_exists: Optional[bool] = None
    indexnow_exists: Optional[bool] = None
    brand: BrandEvidence = field(default_factory=lambda: BrandEvidence(""))
    warnings: Tuple[str, ...] = ()

    @classmethod
    def empty(cls, url: str, brand_name: str) -> "ReportSnapshot":
        return cls(url=url, brand_name=brand_name, brand=BrandEvidence(brand_name))


@dataclass(frozen=True)
class ScoreResult:
    score: int
    maximum: int
    breakdown: Dict[str, Dict[str, Any]]
    reason: str = ""


@dataclass(frozen=True)
class BrandScoreResult:
    score: int
    breakdown: Dict[str, int]
    maximums: Dict[str, int]
    evidence_counts: Dict[str, int]
    source: str = "taiwan_search"
    reason: str = ""
    warnings: Tuple[str, ...] = ()


class _PageParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title = ""
        self.description = ""
        self.canonical = ""
        self.lang = ""
        self.text_parts: List[str] = []
        self.headings: List[str] = []
        self.links: List[str] = []
        self.images = 0
        self.images_with_alt = 0
        self.images_with_dimensions = 0
        self.has_viewport = False
        self.has_author = False
        self.has_date = False
        self.jsonld_raw: List[str] = []
        self._capture: Optional[str] = None
        self._buffer: List[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: Sequence[Tuple[str, Optional[str]]]) -> None:
        values = {k.lower(): (v or "") for k, v in attrs}
        tag = tag.lower()
        if tag == "html":
            self.lang = values.get("lang", "")
        if tag in {"script", "style", "noscript", "svg"}:
            if tag == "script" and values.get("type", "").lower() == "application/ld+json":
                self._capture = "jsonld"
                self._buffer = []
            else:
                self._skip_depth += 1
        elif tag == "title":
            self._capture = "title"
            self._buffer = []
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._capture = "heading"
            self._buffer = []
        elif tag == "meta":
            key = (values.get("name") or values.get("property") or "").lower()
            content = values.get("content", "").strip()
            if key in {"description", "og:description"} and not self.description:
                self.description = content
            if key == "viewport":
                self.has_viewport = True
            if key in {"author", "article:author"} and content:
                self.has_author = True
            if key in {"article:published_time", "article:modified_time", "date"} and content:
                self.has_date = True
        elif tag == "link" and "canonical" in values.get("rel", "").lower():
            self.canonical = urllib.parse.urljoin(self.base_url, values.get("href", ""))
        elif tag == "a" and values.get("href"):
            self.links.append(urllib.parse.urljoin(self.base_url, values["href"]))
        elif tag == "img":
            self.images += 1
            if values.get("alt", "").strip():
                self.images_with_alt += 1
            if values.get("width") and values.get("height"):
                self.images_with_dimensions += 1
        elif tag == "time" and (values.get("datetime") or values.get("date")):
            self.has_date = True

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            if tag == "script" and self._capture == "jsonld":
                self.jsonld_raw.append("".join(self._buffer).strip())
                self._capture = None
                self._buffer = []
            elif self._skip_depth:
                self._skip_depth -= 1
        elif tag == "title" and self._capture == "title":
            self.title = " ".join(self._buffer).strip()
            self._capture = None
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and self._capture == "heading":
            heading = " ".join(self._buffer).strip()
            if heading:
                self.headings.append(heading)
            self._capture = None

    def handle_data(self, data: str) -> None:
        value = re.sub(r"\s+", " ", data).strip()
        if not value:
            return
        if self._capture:
            self._buffer.append(value)
        if not self._skip_depth and self._capture != "jsonld":
            self.text_parts.append(value)


def _flatten_schema(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            yield from _flatten_schema(item)
    elif isinstance(value, dict):
        graph = value.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                yield from _flatten_schema(item)
        node = {k: v for k, v in value.items() if k != "@graph"}
        if node.get("@type"):
            yield node


def _placeholder_issues(value: Any, path: str = "") -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            yield from _placeholder_issues(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _placeholder_issues(child, f"{path}[{index}]")
    elif isinstance(value, str) and value.strip().lower() in PLACEHOLDERS:
        yield f"placeholder_value:{path.split('.')[-1].split('[')[0]}"


def parse_schema_blocks(blocks: Sequence[Any]) -> SchemaEvidence:
    nodes: List[Dict[str, Any]] = []
    types: List[str] = []
    issues: List[str] = []
    for block in blocks:
        for node in _flatten_schema(block):
            nodes.append(node)
            raw_types = node.get("@type", [])
            if isinstance(raw_types, str):
                raw_types = [raw_types]
            for schema_type in raw_types:
                if not isinstance(schema_type, str):
                    issues.append("invalid_type_value")
                    continue
                types.append(schema_type)
                if schema_type not in VALID_SCHEMA_TYPES:
                    canonical = next(
                        (item for item in VALID_SCHEMA_TYPES if item.lower() == schema_type.lower()),
                        None,
                    )
                    if canonical:
                        issues.append(f"invalid_type_case:{schema_type}")
                    else:
                        issues.append(f"unknown_type:{schema_type}")
            issues.extend(_placeholder_issues(node))
    return SchemaEvidence(
        nodes=tuple(nodes),
        types=tuple(types),
        issues=tuple(dict.fromkeys(issues)),
        jsonld_blocks=len(blocks),
    )


def _parse_jsonld(raw_blocks: Sequence[str]) -> SchemaEvidence:
    parsed: List[Any] = []
    issues: List[str] = []
    for raw in raw_blocks:
        try:
            parsed.append(json.loads(raw))
        except Exception:
            issues.append("invalid_json")
    result = parse_schema_blocks(parsed)
    return SchemaEvidence(
        nodes=result.nodes,
        types=result.types,
        issues=tuple(dict.fromkeys(list(result.issues) + issues)),
        jsonld_blocks=len(raw_blocks),
    )


def _page_from_response(url: str, response: requests.Response, elapsed_ms: int) -> PageEvidence:
    parser = _PageParser(url)
    parser.feed(response.text)
    host = _host(url)
    links = tuple(dict.fromkeys(_normalize_url(link) for link in parser.links if link.startswith("http")))
    external = tuple(link for link in links if _host(link) != host)
    text = " ".join(parser.text_parts)
    return PageEvidence(
        url=url,
        status_code=response.status_code,
        title=parser.title,
        description=parser.description,
        canonical=parser.canonical,
        lang=parser.lang,
        text=text,
        headings=tuple(parser.headings),
        links=links,
        external_links=external,
        images=parser.images,
        images_with_alt=parser.images_with_alt,
        images_with_dimensions=parser.images_with_dimensions,
        has_viewport=parser.has_viewport,
        has_author=parser.has_author,
        has_date=parser.has_date,
        schema=_parse_jsonld(parser.jsonld_raw),
        response_headers=tuple((k.lower(), v) for k, v in response.headers.items()),
        elapsed_ms=elapsed_ms,
        byte_size=len(response.content),
        raw_html=response.text,
    )


def _fetch_page(url: str, timeout: int = 15) -> Tuple[Optional[PageEvidence], Optional[str]]:
    try:
        started = time.monotonic()
        response = _get_public(url, timeout)
        elapsed = round((time.monotonic() - started) * 1000)
        return _page_from_response(response.url, response, elapsed), None
    except Exception as exc:
        return None, f"page_fetch_failed:{url}:{type(exc).__name__}"


AI_BOTS = ("GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended", "OAI-SearchBot", "CCBot")


def _parse_robots(content: str) -> Dict[str, str]:
    groups: Dict[str, List[Tuple[str, str]]] = {}
    agents: List[str] = []
    for raw in content.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = [item.strip() for item in line.split(":", 1)]
        if key.lower() == "user-agent":
            agents = [value]
            groups.setdefault(value.lower(), [])
        elif key.lower() in {"allow", "disallow"}:
            for agent in agents:
                groups.setdefault(agent.lower(), []).append((key.lower(), value))
    result: Dict[str, str] = {}
    for bot in AI_BOTS:
        rules = groups.get(bot.lower(), groups.get("*", []))
        if any(kind == "disallow" and value == "/" for kind, value in rules):
            result[bot] = "blocked"
        elif any(kind == "allow" and value == "/" for kind, value in rules):
            result[bot] = "explicitly_allowed"
        elif rules:
            result[bot] = "not_blocked"
        else:
            result[bot] = "not_mentioned"
    return result


def _fetch_text(url: str, timeout: int = 10) -> Tuple[Optional[bool], str, Optional[str]]:
    try:
        response = _get_public(url, timeout)
        if response.status_code == 200:
            return True, response.text, None
        if response.status_code == 404:
            return False, "", None
        return None, "", f"unexpected_status:{url}:{response.status_code}"
    except Exception as exc:
        return None, "", f"fetch_failed:{url}:{type(exc).__name__}"


def _extract_sitemap_urls(content: str, origin: str) -> List[str]:
    try:
        root = ET.fromstring(content)
        values = [node.text.strip() for node in root.findall(".//{*}loc") if node.text]
        return [value for value in values if _host(value) == _host(origin)]
    except Exception:
        return []


def _select_page_urls(home: PageEvidence, sitemap_urls: Sequence[str], limit: int = 10) -> List[str]:
    candidates = list(sitemap_urls) + [link for link in home.links if _host(link) == _host(home.url)]
    ignored = re.compile(r"\.(?:jpg|jpeg|png|gif|webp|svg|pdf|zip|xml)(?:$|\?)", re.I)
    priority = re.compile(r"/(?:about|company|service|product|case|blog|news|contact|關於|服務|案例|文章|聯絡)", re.I)
    unique = []
    for value in candidates:
        normalized = _normalize_url(value)
        if normalized == _normalize_url(home.url) or ignored.search(normalized) or normalized in unique:
            continue
        unique.append(normalized)
    unique.sort(key=lambda value: (0 if priority.search(value) else 1, len(value)))
    return unique[: max(0, limit - 1)]


def _source_tier(hit: SearchHit) -> int:
    host = _host(hit.url)
    path = urllib.parse.urlsplit(hit.url).path.lower()
    if host == "info.technews.tw" or "/search" in path or "/postwrite/" in path:
        return 6
    if host in MEDIA_TIERS:
        return MEDIA_TIERS[host]
    source = hit.source.upper().replace(" ", "")
    for name, tier in SOURCE_TIERS.items():
        if name.upper().replace(" ", "") in source:
            return tier
    return 6


def _parse_published(value: str) -> Optional[date]:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).date()
    except Exception:
        pass
    for fmt in ("%Y-%m-%d", "%d %b %Y"):
        try:
            return datetime.strptime(value[:31], fmt).date()
        except Exception:
            continue
    match = re.search(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})", value)
    if match:
        try:
            return date(*map(int, match.groups()))
        except ValueError:
            return None
    return None


def _dedupe_hits(hits: Sequence[SearchHit]) -> List[SearchHit]:
    result: List[SearchHit] = []
    seen = set()
    for hit in hits:
        title_key = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", hit.title.lower())
        url_key = _normalize_url(hit.url)
        key = (url_key, title_key)
        if key in seen or any(title_key and title_key == item[1] for item in seen):
            continue
        seen.add(key)
        result.append(hit)
    return result


def _google_news_hits(brand: str) -> Tuple[List[SearchHit], Optional[str]]:
    query = urllib.parse.quote(f'"{brand}"')
    url = f"https://news.google.com/rss/search?q={query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    try:
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=12)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        hits = []
        for item in root.findall(".//item")[:30]:
            title = (item.findtext("title") or "").strip()
            source = (item.findtext("source") or "").strip()
            link = (item.findtext("link") or "").strip()
            published = (item.findtext("pubDate") or "").strip()
            if brand.lower() not in title.lower():
                continue
            hits.append(SearchHit(title, link, source, "", published, "media"))
        return hits, None
    except Exception as exc:
        return [], f"google_news_failed:{type(exc).__name__}"


def _looks_owned_social(url: str, title: str, source: str, brand: str) -> bool:
    path = urllib.parse.urlsplit(url).path.strip("/")
    segments = [segment for segment in path.split("/") if segment]
    profile_path = (
        len(segments) <= 1
        or (segments and segments[0] in {"channel", "c", "user", "company"} and len(segments) <= 2)
    )
    brand_tokens = [token.lower() for token in re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]{2,}", brand)]
    identity = f"{title} {source}".lower()
    source_identity = source.lower()
    return any(token in source_identity for token in brand_tokens) or (
        profile_path and any(token in identity for token in brand_tokens)
    )


def _results_to_hits(results: Sequence[Dict[str, Any]], category: str, brand: str) -> List[SearchHit]:
    hits = []
    for item in results:
        title = str(item.get("title") or "")
        snippet = str(item.get("snippet") or item.get("description") or "")
        url = str(item.get("link") or item.get("url") or "")
        if not url or brand.lower() not in f"{title} {snippet}".lower():
            continue
        source = str(item.get("source") or _host(url))
        published = str(item.get("date") or item.get("published") or "")
        owned = bool(re.search(r"官方|official", f"{title} {snippet}", re.I))
        if category == "social":
            owned = owned or _looks_owned_social(url, title, source, brand)
        hits.append(SearchHit(title, url, source, snippet, published, category, owned))
    return hits


def _entity_tokens(brand_name: str) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    chinese = tuple(dict.fromkeys(re.findall(r"[\u4e00-\u9fff]{2,}", brand_name)))
    latin = tuple(dict.fromkeys(token.lower() for token in re.findall(r"[A-Za-z0-9]{3,}", brand_name)))
    return chinese, latin


def _filter_entity_hits(hits: Sequence[SearchHit], brand_name: str) -> List[SearchHit]:
    chinese, latin = _entity_tokens(brand_name)
    filtered = []
    for hit in hits:
        text = f"{hit.title} {hit.snippet} {hit.source}"
        lower = text.lower()
        if chinese:
            matches = any(token in text for token in chinese)
        else:
            matches = any(token in lower for token in latin)
        if matches:
            filtered.append(hit)
    return filtered


def _search_api_hits(brand: str) -> Tuple[List[SearchHit], List[SearchHit], List[str]]:
    media: List[SearchHit] = []
    social: List[SearchHit] = []
    warnings: List[str] = []
    media_sites = " OR ".join(f"site:{domain}" for domain in MEDIA_TIERS)
    social_sites = " OR ".join(f"site:{domain}" for domain in SOCIAL_DOMAINS)
    queries = ((f'"{brand}" ({media_sites})', "media"), (f'"{brand}" ({social_sites})', "social"))

    serp_key = os.getenv("SERPAPI_KEY", "")
    bycrawl_key = os.getenv("BYCRAWL_API_KEY", "")
    if serp_key:
        for query, category in queries:
            try:
                response = requests.get(
                    "https://serpapi.com/search",
                    params={"q": query, "api_key": serp_key, "engine": "google", "gl": "tw", "hl": "zh-tw", "num": 20},
                    timeout=15,
                )
                hits = _results_to_hits(response.json().get("organic_results", []), category, brand)
                (media if category == "media" else social).extend(hits)
            except Exception as exc:
                warnings.append(f"serpapi_{category}_failed:{type(exc).__name__}")
    elif bycrawl_key:
        for query, category in queries:
            try:
                response = requests.get(
                    "https://api.bycrawl.com/google/search",
                    params={"q": query, "gl": "tw", "hl": "zh-tw", "num": 20},
                    headers={"x-api-key": bycrawl_key},
                    timeout=15,
                )
                payload = response.json()
                hits = _results_to_hits(payload.get("organic") or payload.get("organic_results") or [], category, brand)
                (media if category == "media" else social).extend(hits)
            except Exception as exc:
                warnings.append(f"bycrawl_{category}_failed:{type(exc).__name__}")
    else:
        warnings.append("social_search_unavailable")
    return media, social, warnings


def collect_brand_evidence(
    brand_name: str,
    aliases: Sequence[str],
    owned_domains: Sequence[str],
    schema: SchemaEvidence,
) -> BrandEvidence:
    media: List[SearchHit] = []
    social: List[SearchHit] = []
    warnings: List[str] = []
    for brand in tuple(dict.fromkeys([brand_name, *aliases])):
        if not brand.strip():
            continue
        news, warning = _google_news_hits(brand)
        media.extend(news)
        if warning:
            warnings.append(warning)
        api_media, api_social, api_warnings = _search_api_hits(brand)
        media.extend(api_media)
        social.extend(api_social)
        warnings.extend(api_warnings)

    media = _filter_entity_hits(media, brand_name)
    social = _filter_entity_hits(social, brand_name)
    owned_roots = {
        (_host(hit.url), urllib.parse.urlsplit(hit.url).path.strip("/").split("/")[0])
        for hit in social
        if hit.owned and urllib.parse.urlsplit(hit.url).path.strip("/")
    }
    social = [
        replace(hit, owned=True)
        if (_host(hit.url), urllib.parse.urlsplit(hit.url).path.strip("/").split("/")[0]) in owned_roots
        else hit
        for hit in social
    ]
    sources = ["website"]
    valid_types = {item for item in schema.types if item in VALID_SCHEMA_TYPES}
    if valid_types.intersection({"Organization", "Corporation", "LocalBusiness", "ProfessionalService"}):
        sources.append("schema")
    if media:
        sources.append("media")
    if any(not hit.owned for hit in social):
        sources.append("social")
    return BrandEvidence(
        brand_name=brand_name,
        owned_domains=tuple(owned_domains),
        media_hits=tuple(_dedupe_hits(media)),
        social_hits=tuple(_dedupe_hits(social)),
        entity_sources=tuple(sources),
        identity_consistent=bool(brand_name and len(sources) >= 2),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def collect_report_snapshot(url: str, brand_name: str = "", aliases: Sequence[str] = ()) -> ReportSnapshot:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    url = validate_public_url(url)
    origin_parts = urllib.parse.urlsplit(url)
    origin = f"{origin_parts.scheme}://{origin_parts.netloc}"
    warnings: List[str] = []

    home, warning = _fetch_page(url)
    if warning:
        warnings.append(warning)
    pages: List[PageEvidence] = [home] if home else []

    robots_exists, robots_content, warning = _fetch_text(origin + "/robots.txt")
    if warning:
        warnings.append(warning)
    llms_exists, _, warning = _fetch_text(origin + "/llms.txt")
    if warning:
        warnings.append(warning)
    sitemap_exists, sitemap_content, warning = _fetch_text(origin + "/sitemap.xml")
    if warning:
        warnings.append(warning)
    indexnow_exists, _, _ = _fetch_text(origin + "/.well-known/indexnow-key.txt", timeout=5)

    if home:
        sitemap_urls = _extract_sitemap_urls(sitemap_content, origin) if sitemap_exists else []
        for page_url in _select_page_urls(home, sitemap_urls):
            page, page_warning = _fetch_page(page_url)
            if page:
                pages.append(page)
            if page_warning:
                warnings.append(page_warning)

    page_brand = _detect_brand(home, origin_parts.netloc)
    supplied_brand = _clean_brand_name(brand_name)
    supplied_matches = bool(
        supplied_brand
        and home
        and supplied_brand.lower() in f"{home.title} {home.text[:5000]}".lower()
    )
    detected_brand = supplied_brand if supplied_matches else page_brand
    page_text = f"{home.title} {home.text[:10000]}".lower() if home else ""
    verified_aliases = [alias for alias in aliases if alias.strip() and alias.lower() in page_text]
    combined_schema = parse_schema_blocks([node for page in pages for node in page.schema.nodes])
    brand = collect_brand_evidence(detected_brand, verified_aliases, (_host(origin),), combined_schema)
    warnings.extend(brand.warnings)
    return ReportSnapshot(
        url=url,
        brand_name=detected_brand,
        pages=tuple(pages),
        robots_exists=robots_exists,
        robots_content=robots_content,
        crawler_status=tuple(_parse_robots(robots_content).items()) if robots_exists else (),
        llms_exists=llms_exists,
        sitemap_exists=sitemap_exists,
        indexnow_exists=indexnow_exists,
        brand=brand,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def _detect_brand(home: Optional[PageEvidence], hostname: str) -> str:
    if home:
        for node in home.schema.nodes:
            schema_type = str(node.get("@type", "")).lower()
            if schema_type in {"organization", "corporation", "localbusiness", "website"} and _valid_value(node.get("name")):
                return _clean_brand_name(str(node["name"]))
        if home.title:
            return _clean_brand_name(home.title)
    return hostname.lower().removeprefix("www.").split(".")[0].title()


def _clean_brand_name(value: str) -> str:
    return re.split(r"[|｜–—]", value.strip())[0].strip()


def _criterion(points: int, maximum: int, evidence: str) -> Dict[str, Any]:
    return {"points": min(points, maximum), "max_points": maximum, "evidence": evidence}


def score_schema(schema: SchemaEvidence) -> ScoreResult:
    types = set(schema.types)
    valid_types = {item for item in types if item in VALID_SCHEMA_TYPES}
    invalid = bool(schema.issues)
    org_nodes = [node for node in schema.nodes if node.get("@type") in {"Organization", "Person", "Corporation"}]
    org_complete = any(_valid_value(node.get("name")) and _valid_value(node.get("url")) for node in org_nodes)
    org_basic = any(_valid_value(node.get("name")) for node in org_nodes)
    same_as = []
    owned_hosts = {
        _host(str(node.get(key, "")))
        for node in schema.nodes
        for key in ("url", "@id")
        if str(node.get(key, "")).startswith("http")
    }
    identity_hosts = set(SOCIAL_DOMAINS).union({"wikipedia.org", "wikidata.org", "crunchbase.com"})
    for node in schema.nodes:
        values = node.get("sameAs", [])
        if isinstance(values, str):
            values = [values]
        same_as.extend(
            value for value in values
            if isinstance(value, str)
            and value.startswith("http")
            and _host(value) not in owned_hosts
            and any(_host(value) == domain or _host(value).endswith("." + domain) for domain in identity_hosts)
        )
    articles = [node for node in schema.nodes if node.get("@type") in ARTICLE_SCHEMA_TYPES]
    article_author = any(_valid_value(node.get("author")) for node in articles)
    business_nodes = [node for node in schema.nodes if node.get("@type") in BUSINESS_SCHEMA_TYPES]
    business_complete = any(_valid_value(node.get("name")) and any(_valid_value(node.get(key)) for key in ("address", "offers", "provider", "description")) for node in business_nodes)
    website_action = any(node.get("@type") == "WebSite" and "SearchAction" in str(node.get("potentialAction", "")) for node in schema.nodes)
    has_breadcrumb = "BreadcrumbList" in valid_types
    has_speakable = any(_valid_value(node.get("speakable")) for node in articles)
    has_knows = any(isinstance(node.get("knowsAbout"), list) and len(node["knowsAbout"]) >= 3 for node in org_nodes)
    deprecated = bool(types.intersection(DEPRECATED_SCHEMA_TYPES))

    breakdown = {
        "organization_person": _criterion(15 if org_complete else 10 if org_basic else 0, 15, f"nodes={len(org_nodes)}"),
        "same_as": _criterion(min(15, len(set(same_as)) * 3), 15, f"valid_links={len(set(same_as))}"),
        "article_author": _criterion(10 if article_author else 5 if articles else 0, 10, f"articles={len(articles)}"),
        "business_type": _criterion(10 if business_complete else 5 if business_nodes else 0, 10, f"valid_nodes={len(business_nodes)}"),
        "website_searchaction": _criterion(5 if website_action else 0, 5, str(website_action)),
        "breadcrumb": _criterion(5 if has_breadcrumb else 0, 5, str(has_breadcrumb)),
        "jsonld": _criterion(5 if schema.jsonld_blocks or schema.nodes else 0, 5, f"blocks={schema.jsonld_blocks}"),
        "server_rendered": _criterion(10 if schema.nodes else 0, 10, f"nodes={len(schema.nodes)}"),
        "speakable": _criterion(5 if has_speakable else 0, 5, str(has_speakable)),
        "valid_schema": _criterion(
            10 if valid_types and not invalid else
            5 if valid_types and invalid and all(issue.startswith("unknown_type") for issue in schema.issues) else
            0,
            10,
            ",".join(schema.issues) or "valid",
        ),
        "knows_about": _criterion(5 if has_knows else 0, 5, str(has_knows)),
        "no_deprecated": _criterion(5 if valid_types and not deprecated else 0, 5, str(not deprecated)),
    }
    total = sum(item["points"] for item in breakdown.values())
    return ScoreResult(total, 100, breakdown, f"偵測 {len(schema.nodes)} 個 Schema 節點，發現 {len(schema.issues)} 個資料問題")


def score_brand_authority(
    evidence: BrandEvidence,
    snapshot: Optional[ReportSnapshot] = None,
) -> BrandScoreResult:
    media = _dedupe_hits(evidence.media_hits)
    social = _dedupe_hits(evidence.social_hits)
    today = datetime.now(timezone.utc).date()
    tier_points = {1: 10, 2: 8, 3: 6, 4: 4, 5: 3, 6: 2}
    media_score = 0
    for hit in media:
        points = tier_points[_source_tier(hit)]
        published = _parse_published(hit.published)
        if published and (today - published).days > 365:
            points = max(1, points // 2)
        media_score += points
    media_score = min(40, media_score)

    # /report 的內容深度評估品牌自己的論述內容，不重複拿媒體標題加分。
    depth_score = 0
    if snapshot:
        depth_terms = re.compile(r"專訪|研究|調查|數據|案例|白皮書|報告|方法|成效", re.I)
        commercial = re.compile(r"購物車|立即購買|優惠|折扣|商品規格|product|cart|shop", re.I)
        for page in snapshot.pages:
            identity = f"{page.url} {page.title} {' '.join(page.headings)}"
            if depth_terms.search(identity) and not commercial.search(identity) and len(page.text) >= 500:
                depth_score += 4 if re.search(r"\d+(?:\.\d+)?%|\d+[萬億]|研究方法|執行流程", page.text) else 2
    depth_score = min(20, depth_score)

    third_party = [hit for hit in social if not hit.owned]
    social_weights = {"PTT": 5, "Dcard": 5, "Threads": 4, "YouTube": 3, "Instagram": 2, "Facebook": 2, "LinkedIn": 1}
    social_score = 0
    for hit in third_party:
        platform = next((name for domain, name in SOCIAL_DOMAINS.items() if domain in _host(hit.url)), hit.source)
        social_score += social_weights.get(platform, 1)
    social_score = min(20, social_score)

    source_set = set(evidence.entity_sources)
    entity_score = 0
    entity_score += 5 if "website" in source_set else 0
    entity_score += 5 if "schema" in source_set else 0
    entity_score += 5 if "media" in source_set else 0
    entity_score += 3 if "social" in source_set else 0
    entity_score += 2 if evidence.identity_consistent else 0
    entity_score = min(20, entity_score)
    breakdown = {
        "media": media_score,
        "content_depth": depth_score,
        "social": social_score,
        "entity": entity_score,
    }
    return BrandScoreResult(
        score=sum(breakdown.values()),
        breakdown=breakdown,
        maximums={"media": 40, "content_depth": 20, "social": 20, "entity": 20},
        evidence_counts={"media": len(media), "third_party_social": len(third_party)},
        reason=f"台灣媒體 {len(media)} 篇、第三方社群 {len(third_party)} 筆；未取得資料不補猜",
        warnings=evidence.warnings,
    )


def _all_text(snapshot: ReportSnapshot) -> str:
    return " ".join(page.text for page in snapshot.pages)


def _all_schema(snapshot: ReportSnapshot) -> SchemaEvidence:
    return parse_schema_blocks([node for page in snapshot.pages for node in page.schema.nodes])


def _content_units(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]", text))


def score_content(snapshot: ReportSnapshot) -> ScoreResult:
    text = _all_text(snapshot)
    lower = text.lower()
    pages = snapshot.pages
    external_links = sum(len(page.external_links) for page in pages)
    words = _content_units(text)
    has_numbers = bool(re.search(r"\d+(?:\.\d+)?%|\d+[萬億]|\d{2,}", text))
    first_person = bool(re.search(r"我們|本團隊|實測|親自|we tested|we implemented", lower))
    case_pages = [page for page in pages if re.search(r"案例|case.study|成效|成果", f"{page.url} {page.title} {' '.join(page.headings)}", re.I) and len(page.text) >= 500]
    research_pages = [page for page in pages if re.search(r"研究|調查|白皮書|research|survey", f"{page.url} {page.title} {' '.join(page.headings)}", re.I) and len(page.text) >= 500]
    method_pages = [page for page in pages if re.search(r"方法|流程|步驟|methodology|how.we", f"{page.title} {' '.join(page.headings)}", re.I) and len(page.headings) >= 2]
    author_pages = [page for page in pages if page.has_author]
    credentials = any(
        re.search(r"證照|認證|博士|碩士|顧問|\d+年經驗|certified|ph\.?d", page.text, re.I)
        for page in author_pages
    )
    awards = bool(re.search(r"獲獎|獎項|award|認證", lower))
    speaker = bool(re.search(r"講師|演講|論壇|研討會|speaker|conference", lower))
    reviews = bool(re.search(r"客戶評價|使用者評價|testimonial|review", lower))
    has_phone = bool(re.search(r"(?:\+?886[-\s]?)?0?\d{1,2}[-\s]\d{6,8}", text, re.I))
    has_email = bool(re.search(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", text, re.I))
    has_address = bool(re.search(r"(?:台灣|臺灣|台北|臺北|新北|桃園|台中|臺中|台南|臺南|高雄|地址).{0,35}(?:路|街|巷|號|樓)", text))
    privacy = any(re.search(r"privacy|隱私", f"{page.text} {' '.join(page.links)}", re.I) for page in pages)
    terms = any(re.search(r"terms|服務條款|使用條款", f"{page.text} {' '.join(page.links)}", re.I) for page in pages)
    disclosure = bool(re.search(r"利益揭露|贊助|廣告合作|affiliate|sponsor", lower))
    media_count = len(_dedupe_hits(snapshot.brand.media_hits))

    cited_data = has_numbers and bool(re.search(r"根據|資料來源|研究指出|according to|source", lower)) and external_links > 0
    authentic_evidence = any(re.search(r"實拍|截圖|檢驗報告|測試畫面|screenshot", page.raw_html, re.I) for page in pages)
    specific_first_person = first_person and bool(case_pages or method_pages) and has_numbers
    experience = min(25,
        (5 if specific_first_person else 3 if first_person else 0)
        + (5 if research_pages and cited_data else 3 if research_pages else 0)
        + (4 if case_pages and has_numbers else 2 if case_pages else 0)
        + (3 if authentic_evidence else 0)
        + (4 if case_pages and len(case_pages) >= 2 else 2 if case_pages else 0)
        + (4 if method_pages and any(re.search(r"<ol\b", page.raw_html, re.I) for page in method_pages) else 2 if method_pages else 0)
    )
    deepest = max((_content_units(page.text) for page in pages), default=0)
    technical_depth = 5 if deepest >= 2000 and external_links >= 2 else 3 if deepest >= 1000 and any(len(page.headings) >= 2 for page in pages) else 0
    author_detail = 4 if credentials and any(re.search(r"author|作者|團隊|team", link, re.I) for page in pages for link in page.links) else 2 if author_pages else 0
    expertise = min(25,
        (5 if credentials else 0)
        + technical_depth
        + (4 if method_pages and any(re.search(r"<ol\b", page.raw_html, re.I) for page in method_pages) else 2 if method_pages else 0)
        + (4 if cited_data and external_links >= 2 else 2 if cited_data else 0)
        + (3 if technical_depth else 0)
        + author_detail
    )
    quoted_media = any(re.search(r"專訪|受訪|表示|指出|觀點", f"{hit.title} {hit.snippet}") for hit in snapshot.brand.media_hits)
    respected_media = any(_source_tier(hit) <= 2 for hit in snapshot.brand.media_hits)
    authority = min(25,
        (5 if media_count >= 3 else 3 if media_count else 0)
        + (4 if quoted_media else 2 if media_count else 0)
        + (3 if awards else 0)
        + (3 if speaker else 0)
        + (4 if respected_media else 2 if media_count else 0)
        + (3 if len(case_pages) + len(research_pages) >= 5 else 1 if len(case_pages) + len(research_pages) >= 2 else 0)
        + (3 if any("wikipedia.org" in link for page in pages for link in page.external_links) else 0)
    )
    contact_points = 4 if has_phone and has_email and has_address else 2 if has_phone or has_email else 0
    source_domains = {_host(link) for page in pages for link in page.external_links}
    accuracy_points = 4 if cited_data and len(source_domains) >= 3 else 2 if cited_data else 0
    third_party_reviews = any(not hit.owned for hit in snapshot.brand.social_hits)
    trust = min(25,
        contact_points
        + (2 if privacy else 0)
        + (1 if terms else 0)
        + (2 if pages and snapshot.url.startswith("https://") else 0)
        + (3 if any(re.search(r"editorial|編輯政策|更正", page.text, re.I) for page in pages) else 0)
        + (3 if disclosure else 0)
        + (3 if third_party_reviews else 1 if reviews else 0)
        + accuracy_points
    )
    depth_pages = len(case_pages) + len(research_pages) + len(method_pages)
    modifier = 10 if depth_pages >= 10 else 5 if depth_pages >= 5 else 0 if depth_pages >= 2 else -5
    breakdown = {
        "experience": _criterion(experience, 25, f"first_person={specific_first_person},case_pages={len(case_pages)},research_pages={len(research_pages)}"),
        "expertise": _criterion(expertise, 25, f"credentials={credentials},words={words},sources={external_links}"),
        "authoritativeness": _criterion(authority, 25, f"media={media_count},pages={len(pages)}"),
        "trustworthiness": _criterion(trust, 25, f"full_contact={contact_points == 4},privacy={privacy},terms={terms}"),
    }
    total = _clamp(sum(item["points"] for item in breakdown.values()) + modifier)
    return ScoreResult(total, 100, breakdown, f"E-E-A-T 四項逐項計分，主題覆蓋修正 {modifier:+d}")


def _crawler(snapshot: ReportSnapshot, name: str) -> str:
    return dict(snapshot.crawler_status).get(name, "unknown")


def score_technical(snapshot: ReportSnapshot) -> ScoreResult:
    home = snapshot.pages[0] if snapshot.pages else None
    pages = snapshot.pages
    robots_blocked = any(status == "blocked" for _, status in snapshot.crawler_status)
    crawler_known = bool(snapshot.crawler_status) or snapshot.robots_exists is False
    crawler_points = 5 if crawler_known and not robots_blocked else 3 if crawler_known else 0
    noindex = bool(home and re.search(r"<meta[^>]+(?:name=[\"']robots[\"'][^>]+content=[\"'][^\"']*noindex|content=[\"'][^\"']*noindex[^\"']*[\"'][^>]+name=[\"']robots)", home.raw_html, re.I))
    headers = home.headers if home else {}
    compression = headers.get("content-encoding", "") in {"gzip", "br", "deflate"}
    mobile = bool(home and home.has_viewport)
    raw_text = len(home.text) if home else 0
    link_count = len(home.links) if home else 0
    elapsed = home.elapsed_ms if home else None
    weight = home.byte_size if home else None
    image_ratio = (home.images_with_alt / home.images) if home and home.images else 0
    dimension_ratio = (home.images_with_dimensions / home.images) if home and home.images else 0
    urls = [page.url for page in pages]

    crawl = (3 if snapshot.robots_exists else 0) + crawler_points + (3 if snapshot.sitemap_exists else 0) + (2 if len(pages) >= 3 else 0) + (2 if home and not noindex else 0)
    canonical_ok = bool(pages) and all(page.canonical and _normalize_url(page.canonical) == _normalize_url(page.url) for page in pages)
    indexability = 3 if canonical_ok else 0
    security = (4 if snapshot.url.startswith("https://") else 0) + (2 if "strict-transport-security" in headers else 0) + (1 if "x-content-type-options" in headers else 0) + (1 if "x-frame-options" in headers else 0) + (1 if "referrer-policy" in headers else 0) + (1 if "content-security-policy" in headers else 0)
    clean_urls = bool(urls) and all(len(urllib.parse.urlsplit(url).path) <= 100 and "_" not in urllib.parse.urlsplit(url).path and not urllib.parse.urlsplit(url).query for url in urls)
    logical_hierarchy = len(urls) >= 2 and all(len([part for part in urllib.parse.urlsplit(url).path.split("/") if part]) <= 3 for url in urls)
    url_score = (2 if clean_urls else 0) + (2 if logical_hierarchy else 0)
    responsive = bool(home and re.search(r"@media\s*\(|responsive", home.raw_html, re.I))
    tap_targets = bool(home and re.search(r"min-(?:width|height)\s*:\s*(?:4[8-9]|[5-9]\d)px", home.raw_html, re.I))
    legible_fonts = bool(home and re.search(r"font-size\s*:\s*(?:1[6-9]|[2-9]\d)px", home.raw_html, re.I))
    mobile_score = (3 if mobile else 0) + (3 if responsive else 0) + (2 if tap_targets else 0) + (2 if legible_fonts else 0)
    lcp_estimate = bool(elapsed is not None and elapsed < 800 and weight is not None and weight < 2_000_000)
    cwv = (5 if lcp_estimate else 0) + (5 if dimension_ratio >= 0.8 else 0)
    ssr = (8 if raw_text >= 300 else 4 if raw_text >= 100 else 0) + (4 if home and (home.title or home.schema.nodes) else 0) + (3 if link_count >= 3 else 0)
    optimized_images = bool(home and home.images and image_ratio >= 0.8 and dimension_ratio >= 0.8 and re.search(r"\.(?:webp|avif)(?:[?\"'])", home.raw_html, re.I))
    speed = (3 if elapsed is not None and elapsed < 800 else 1 if elapsed is not None and elapsed < 1500 else 0) + (2 if weight is not None and weight < 2_000_000 else 0) + (3 if optimized_images else 0) + (2 if compression else 0) + (2 if "cache-control" in headers else 0) + (1 if any(key in headers for key in ("cf-ray", "x-cache", "x-served-by")) else 0)
    values = {
        "crawlability": (crawl, 15), "indexability": (indexability, 12),
        "security": (security, 10), "url_structure": (url_score, 8),
        "mobile": (mobile_score, 10), "core_web_vitals": (cwv, 15),
        "ssr": (ssr, 15), "page_speed": (speed, 15),
    }
    breakdown = {key: _criterion(points, maximum, f"measured={points}/{maximum}") for key, (points, maximum) in values.items()}
    total = sum(item["points"] for item in breakdown.values())
    return ScoreResult(total, 100, breakdown, "依 /report 八類技術檢核加總")


def score_platforms(snapshot: ReportSnapshot, content: ScoreResult, schema: ScoreResult, technical: ScoreResult) -> Dict[str, Any]:
    pages = snapshot.pages
    if not pages:
        platforms = {name: 0 for name in ("google_ai", "chatgpt", "perplexity", "gemini", "bing_copilot")}
        return {"score": 0, "platforms": platforms, "reason": "未取得可驗證頁面，所有 /report 平台檢核為 0"}

    all_urls = [link for page in pages for link in page.external_links]
    all_urls.extend(hit.url for hit in snapshot.brand.social_hits)
    social_hits = [hit for hit in snapshot.brand.social_hits if not hit.owned]
    media_hits = _dedupe_hits(snapshot.brand.media_hits)
    html = " ".join(page.raw_html for page in pages)
    text = _all_text(snapshot)
    question_headings = sum(len(re.findall(r"<h[2-3][^>]*>[^<]*(?:[?？]|如何|什麼|為何|FAQ)", page.raw_html, re.I)) for page in pages)
    direct_answers = sum(len(re.findall(r"</h[2-3]>\s*<p[^>]*>[^<]{35,}", page.raw_html, re.I)) for page in pages)
    faq_points = 10 if question_headings >= 5 else 5 if question_headings else 0
    cited_stats = sum(1 for page in pages if re.search(r"\d+(?:\.\d+)?%|\d+[萬億]", page.text) and page.external_links)
    hierarchy_ok = any(re.search(r"<h1\b", page.raw_html, re.I) and re.search(r"<h2\b", page.raw_html, re.I) for page in pages)
    google_ai = min(100,
        min(10, question_headings * 2)
        + min(15, direct_answers * 3)
        + (10 if re.search(r"<table\b", html, re.I) else 0)
        + (10 if re.search(r"<(?:ol|ul)\b", html, re.I) else 0)
        + faq_points
        + min(10, cited_stats * 2)
        + (3 if any(page.has_date for page in pages) else 0)
        + (5 if any(page.has_author and re.search(r"證照|博士|碩士|認證|\d+年經驗", page.text) for page in pages) else 3 if any(page.has_author for page in pages) else 0)
        + (5 if hierarchy_ok else 0)
    )

    wikipedia = any("wikipedia.org" in _host(url) for url in all_urls)
    wikidata = any("wikidata.org" in _host(url) for url in all_urls)
    youtube = any("youtube.com" in _host(url) or "youtu.be" in _host(url) for url in all_urls)
    reddit = [hit for hit in social_hits if "reddit.com" in _host(hit.url)]
    authoritative_categories = len({_source_tier(hit) for hit in media_hits if _source_tier(hit) <= 5})
    entity_sources = set(snapshot.brand.entity_sources)
    deepest = max((_content_units(page.text) for page in pages), default=0)
    chatgpt = (
        (20 if wikipedia else 0)
        + (10 if wikidata else 0)
        + (10 if len(reddit) >= 3 else 5 if reddit else 0)
        + (10 if youtube and any("youtube.com/watch" in hit.url for hit in snapshot.brand.social_hits) else 5 if youtube else 0)
        + min(15, authoritative_categories * 3)
        + (10 if len(entity_sources) >= 3 and snapshot.brand.identity_consistent else 5 if len(entity_sources) >= 2 else 0)
        + (10 if deepest >= 2000 else 5 if deepest >= 800 else 0)
    )

    community_platforms = {_host(hit.url) for hit in social_hits if any(domain in _host(hit.url) for domain in ("ptt.cc", "dcard.tw", "news.ycombinator.com", "stackoverflow.com", "quora.com"))}
    original_research = any(re.search(r"研究|調查|白皮書|案例", f"{page.title} {' '.join(page.headings)}", re.I) and re.search(r"\d+(?:\.\d+)?%|\d+[萬億]", page.text) for page in pages)
    quotable = sum(1 for page in pages for paragraph in re.findall(r"<p[^>]*>(.*?)</p>", page.raw_html, re.I | re.S) if len(re.sub(r"<[^>]+>", "", paragraph)) >= 80)
    source_domains = {_host(link) for page in pages for link in page.external_links}
    perplexity = (
        (20 if len(reddit) >= 3 else 10 if reddit else 0)
        + (10 if len(community_platforms) >= 2 else 5 if community_platforms else 0)
        + (10 if any(page.has_date for page in pages) else 0)
        + (15 if original_research else 0)
        + (10 if youtube and any("youtube.com/watch" in url for url in all_urls) else 5 if youtube else 0)
        + min(10, quotable * 2)
        + (10 if len(source_domains) >= 3 else 5 if source_domains else 0)
        + (10 if len(social_hits) >= 3 else 5 if social_hits else 0)
        + (5 if wikipedia or wikidata else 0)
    )

    has_maps = any(re.search(r"google\.com/maps|maps\.app\.goo\.gl", url, re.I) for url in all_urls)
    optimized_images = bool(pages[0].images and pages[0].images_with_alt / pages[0].images >= 0.8 and pages[0].images_with_dimensions / pages[0].images >= 0.8)
    google_ecosystem = sum((youtube, has_maps, bool(media_hits)))
    gemini = (
        (5 if has_maps else 0)
        + (10 if youtube else 0)
        + (15 if schema.score >= 70 else 10 if schema.score >= 40 else 5 if schema.score > 0 else 0)
        + (10 if google_ecosystem >= 3 else 5 if google_ecosystem else 0)
        + (10 if optimized_images else 5 if pages[0].images else 0)
        + (10 if content.score >= 70 else 5 if content.score >= 35 else 0)
        + (5 if youtube and pages[0].images and pages[0].text else 3 if pages[0].images else 0)
    )

    linkedin = any("linkedin.com" in _host(url) for url in all_urls)
    descriptions = sum(bool(page.description) for page in pages)
    meta_points = 10 if descriptions == len(pages) else 5 if descriptions else 0
    elapsed = pages[0].elapsed_ms
    bing = (
        (5 if snapshot.sitemap_exists else 0)
        + (15 if snapshot.indexnow_exists else 0)
        + (5 if linkedin else 0)
        + meta_points
        + (10 if len(social_hits) >= 3 else 5 if social_hits else 0)
        + (10 if elapsed is not None and elapsed < 2000 else 5 if elapsed is not None and elapsed < 4000 else 0)
    )
    platforms = {
        "google_ai": _clamp(google_ai), "chatgpt": _clamp(chatgpt), "perplexity": _clamp(perplexity),
        "gemini": _clamp(gemini), "bing_copilot": _clamp(bing),
    }
    return {"score": round(sum(platforms.values()) / len(platforms)), "platforms": platforms, "reason": "依 /report 五平台逐項實證計分；查不到的訊號為 0"}


def run_report_audit(url: str, brand_name: str = "", aliases: Sequence[str] = ()) -> Dict[str, Any]:
    snapshot = collect_report_snapshot(url, brand_name, aliases)
    schema_evidence = _all_schema(snapshot)
    schema = score_schema(schema_evidence)
    brand = score_brand_authority(snapshot.brand, snapshot)
    content = score_content(snapshot)
    technical = score_technical(snapshot)
    platform = score_platforms(snapshot, content, schema, technical)
    return {
        "scoring_version": REPORT_SCORING_VERSION,
        "brand_name": snapshot.brand_name,
        "scores": {
            "ai_platform": platform["score"],
            "content": content.score,
            "technical": technical.score,
            "schema": schema.score,
            "brand": brand.score,
        },
        "reasons": {
            "ai_platform": platform["reason"],
            "content": content.reason,
            "technical": technical.reason,
            "schema": schema.reason,
            "brand": brand.reason,
        },
        "platform_scores": platform["platforms"],
        "brand_matrix": brand.breakdown,
        "breakdowns": {
            "content": content.breakdown,
            "technical": technical.breakdown,
            "schema": schema.breakdown,
        },
        "brand_evidence": {
            "media": [hit.__dict__ for hit in _dedupe_hits(snapshot.brand.media_hits)],
            "social": [hit.__dict__ for hit in _dedupe_hits(snapshot.brand.social_hits)],
            "counts": brand.evidence_counts,
        },
        "warnings": list(dict.fromkeys([*snapshot.warnings, *brand.warnings])),
    }
