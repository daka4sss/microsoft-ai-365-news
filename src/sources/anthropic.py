"""
Microsoft AI 365 - Anthropic Custom Collector

Anthropic は公式 RSS を提供していないため、sitemap.xml + 個別記事ページの
Open Graph メタタグから情報を取得する独立した collector。

設計思想:
- 既存 RSS と同じ dict 形式を返す → 下流 (classify_summarize, render_site) は無変更
- Anthropic 固有のロジックはこの 1 ファイルに完全集約
- 将来 RSS 復活 / API 提供 / DOM 仕様変更が起きても、このファイルだけ差し替え
- エラーは握り潰してパイプライン継続 (既存 fetch_feeds.fetch_one_source と同思想)

Public API:
    fetch_recent(lookback_days=None) -> list[dict]   # 差分用 (fetch_feeds から)
    fetch_range(start, end) -> list[dict]            # バックフィル用 (fetch_range から)
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from src.config import ANTHROPIC_CONFIG

logger = logging.getLogger(__name__)

SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"


# ============================================================
# Sitemap parsing
# ============================================================
def _get_sitemap_entries() -> list[dict]:
    """sitemap.xml をパースし [{loc, lastmod}, ...] を返す。"""
    url = ANTHROPIC_CONFIG["sitemap_url"]
    timeout = ANTHROPIC_CONFIG.get("sitemap_timeout", 30)
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": DEFAULT_UA})
    resp.raise_for_status()
    root = ET.fromstring(resp.content)

    entries: list[dict] = []
    for url_elem in root.iter(f"{SITEMAP_NS}url"):
        loc_elem = url_elem.find(f"{SITEMAP_NS}loc")
        if loc_elem is None or not loc_elem.text:
            continue
        lastmod_elem = url_elem.find(f"{SITEMAP_NS}lastmod")
        lastmod = lastmod_elem.text if lastmod_elem is not None and lastmod_elem.text else None
        entries.append({"loc": loc_elem.text.strip(), "lastmod": lastmod})
    return entries


# ============================================================
# Filters
# ============================================================
def _filter_by_prefix(entries: list[dict]) -> list[dict]:
    """path_prefixes (/news/, /engineering/) に一致するもののみ通過。"""
    prefixes: list[str] = ANTHROPIC_CONFIG["path_prefixes"]
    out: list[dict] = []
    for e in entries:
        path = urlparse(e["loc"]).path
        # Skip the index pages themselves (/news, /news/, /engineering, /engineering/)
        if any(path.startswith(p) and len(path) > len(p) for p in prefixes):
            out.append(e)
    return out


def _parse_lastmod(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _filter_by_lookback(entries: list[dict], days: int) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    for e in entries:
        dt = _parse_lastmod(e.get("lastmod"))
        if dt and dt >= cutoff:
            out.append(e)
    return out


def _filter_by_range(
    entries: list[dict], start: datetime, end: datetime
) -> list[dict]:
    """[start, end) の半開区間で抽出 (既存 fetch_range と同じ規約)。"""
    out = []
    for e in entries:
        dt = _parse_lastmod(e.get("lastmod"))
        if dt and start <= dt < end:
            out.append(e)
    return out


# ============================================================
# Per-article metadata extraction (OG tags)
# ============================================================
# og:description が汎用の会社説明文を返すページがあるため、それを検出して
# 本文抽出にフォールバックさせる。完全一致ではなく前方一致でチェック。
_GENERIC_DESCRIPTION_PREFIX = "Anthropic is an AI safety and research company"

# LLM に渡す本文の最大文字数 (既存 config.MAX_CONTENT_CHARS に合わせる)。
_MAX_BODY_CHARS = 6000


def _extract_metadata(url: str) -> dict | None:
    """
    個別ページから タイトル + 本文 を抽出。失敗時は None。

    抽出戦略:
    - title: og:title を優先、無ければ <title> タグ
    - content: <article> タグ → <main> タグ → og:description の優先順
      (og:description はページによって汎用の会社説明文が入るため
       実本文の方を優先。LLM 要約の品質を担保)
    """
    timeout = ANTHROPIC_CONFIG.get("request_timeout", 15)
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": DEFAULT_UA})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")

        # --- title ---
        og_title = soup.find("meta", property="og:title")
        title = (og_title.get("content") if og_title else None) or _fallback_title(soup)
        if not title:
            logger.warning(f"  ⚠️  No title for {url}")
            return None

        # --- content (本文優先、og:description フォールバック) ---
        body = _extract_body(soup)
        if not body:
            og_desc = soup.find("meta", property="og:description")
            body = (og_desc.get("content") if og_desc else "") or ""
            if body.startswith(_GENERIC_DESCRIPTION_PREFIX):
                # 汎用の会社説明しか取れなかった場合: せめてタイトルだけは渡す
                body = ""

        return {
            "title": title.strip(),
            "description": body.strip()[:_MAX_BODY_CHARS],
        }
    except Exception as e:
        logger.warning(f"  ⚠️  Failed to fetch metadata for {url}: {type(e).__name__}: {e}")
        return None


def _extract_body(soup: BeautifulSoup) -> str:
    """<article> または <main> から本文テキストを抽出。空文字なら空文字。"""
    for tag_name in ("article", "main"):
        tag = soup.find(tag_name)
        if tag:
            text = tag.get_text(separator=" ", strip=True)
            text = " ".join(text.split())  # 余計な空白除去
            if len(text) >= 200:  # ナビ要素だけ拾った場合の防御
                return text
    return ""


def _fallback_title(soup: BeautifulSoup) -> str:
    """og:title が無い場合の <title> タグ fallback。"""
    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        return title_tag.string.strip()
    return ""


# ============================================================
# Mapping to common article dict format (matches RSS pipeline output)
# ============================================================
def _to_article_dict(entry: dict, meta: dict) -> dict:
    """既存 RSS と完全一致した dict 形式に変換。"""
    path = urlparse(entry["loc"]).path
    is_engineering = path.startswith("/engineering/")

    return {
        "url": entry["loc"],
        "title": meta["title"],
        "content": meta["description"],
        "published": entry["lastmod"] or datetime.now(timezone.utc).isoformat(),
        "source_name": "Anthropic Engineering" if is_engineering else "Anthropic News",
        # path 込みで分離 → render_site.source_counts (domain ベース) で別カウント表示
        "domain": "anthropic.com/engineering" if is_engineering else "anthropic.com/news",
        "source_hint": "Anthropic",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


# ============================================================
# Parallel article fetching
# ============================================================
def _fetch_articles(filtered_entries: list[dict]) -> list[dict]:
    """並列で個別ページからメタタグ取得し、article dict のリストを返す。"""
    if not filtered_entries:
        return []

    max_workers = ANTHROPIC_CONFIG.get("fetch_concurrency", 3)
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        metas = list(ex.map(lambda e: _extract_metadata(e["loc"]), filtered_entries))

    articles: list[dict] = []
    for entry, meta in zip(filtered_entries, metas):
        if meta is None:
            continue
        articles.append(_to_article_dict(entry, meta))
    return articles


# ============================================================
# Public API
# ============================================================
def fetch_recent(lookback_days: int | None = None) -> list[dict]:
    """
    差分用: 過去 N 日に lastmod が更新された Anthropic 記事を取得。
    seen_urls フィルタは呼び出し元 (fetch_feeds) に任せる。
    """
    if not ANTHROPIC_CONFIG.get("enabled", False):
        logger.info("Anthropic collector is disabled (ANTHROPIC_CONFIG['enabled']=False)")
        return []

    days = lookback_days or ANTHROPIC_CONFIG["lookback_days"]
    try:
        logger.info(f"Fetching Anthropic sitemap ({ANTHROPIC_CONFIG['sitemap_url']})")
        all_entries = _get_sitemap_entries()
        prefixed = _filter_by_prefix(all_entries)
        recent = _filter_by_lookback(prefixed, days)
        logger.info(
            f"Anthropic: {len(all_entries)} sitemap entries → "
            f"{len(prefixed)} matched prefix → "
            f"{len(recent)} within {days}d lookback"
        )
        articles = _fetch_articles(recent)
        logger.info(f"  ✓ Fetched {len(articles)} Anthropic articles")
        return articles
    except Exception as e:
        logger.error(f"❌ Anthropic fetch_recent failed: {type(e).__name__}: {e}")
        return []


def fetch_range(start: datetime, end: datetime) -> list[dict]:
    """
    バックフィル用: [start, end) の半開区間で Anthropic 記事を取得。
    seen_urls 無視 (既存 fetch_range と同じ規約)。
    """
    if not ANTHROPIC_CONFIG.get("enabled", False):
        logger.info("Anthropic collector is disabled")
        return []

    try:
        logger.info(
            f"Fetching Anthropic sitemap for range "
            f"{start.isoformat()} ~ {end.isoformat()}"
        )
        all_entries = _get_sitemap_entries()
        prefixed = _filter_by_prefix(all_entries)
        in_range = _filter_by_range(prefixed, start, end)
        logger.info(
            f"Anthropic: {len(all_entries)} sitemap entries → "
            f"{len(prefixed)} matched prefix → "
            f"{len(in_range)} in range"
        )
        articles = _fetch_articles(in_range)
        logger.info(f"  ✓ Fetched {len(articles)} Anthropic articles in range")
        return articles
    except Exception as e:
        logger.error(f"❌ Anthropic fetch_range failed: {type(e).__name__}: {e}")
        return []
