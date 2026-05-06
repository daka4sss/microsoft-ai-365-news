"""
Microsoft AI 365 - RSS Feed Fetcher

設計思想:
- 全RSSソースから新着記事を取得
- seen_urls.json で分類・要約成功済みURLを除外（冪等性担保）
- HTML タグや余計な空白を除去してクリーンな本文を抽出
- 失敗ソースがあっても他のソースは処理を継続（耐障害性）
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import feedparser
from bs4 import BeautifulSoup

from src.config import (
    RSS_SOURCES,
    SEEN_URLS_JSON,
    DATA_DIR,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def load_seen_urls() -> set[str]:
    """既読URL集合をロード。なければ空集合を返す。"""
    if not SEEN_URLS_JSON.exists():
        return set()
    try:
        return set(json.loads(SEEN_URLS_JSON.read_text(encoding="utf-8")))
    except Exception as e:
        logger.warning(f"Failed to load seen_urls.json: {e}. Starting fresh.")
        return set()


def save_seen_urls(urls: set[str]) -> None:
    """既読URL集合を保存。"""
    SEEN_URLS_JSON.parent.mkdir(parents=True, exist_ok=True)
    SEEN_URLS_JSON.write_text(
        json.dumps(sorted(urls), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def clean_html(raw: str) -> str:
    """HTMLタグを除去してプレーンテキストに変換。"""
    if not raw:
        return ""
    soup = BeautifulSoup(raw, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    # Collapse multiple spaces
    return " ".join(text.split())


def parse_published(entry: dict) -> str:
    """RSS entryから公開日時を ISO 形式で取得。"""
    for key in ("published_parsed", "updated_parsed"):
        if entry.get(key):
            try:
                return datetime(*entry[key][:6], tzinfo=timezone.utc).isoformat()
            except Exception:
                continue
    return datetime.now(timezone.utc).isoformat()


def fetch_one_source(source: dict) -> list[dict]:
    """1ソースから記事を取得。失敗時は空リストを返す（処理継続）。"""
    try:
        logger.info(f"Fetching: {source['name']} ({source['url']})")
        parsed = feedparser.parse(source["url"])

        if parsed.bozo and not parsed.entries:
            logger.warning(
                f"  ⚠️  Bozo feed (parse warning) and no entries: {source['name']}"
            )
            return []

        articles = []
        for entry in parsed.entries:
            url = entry.get("link", "").strip()
            if not url:
                continue

            title = clean_html(entry.get("title", "Untitled"))
            content = entry.get("content", [{}])[0].get("value") if entry.get("content") else None
            content = content or entry.get("summary", "") or entry.get("description", "")
            content = clean_html(content)

            articles.append({
                "url": url,
                "title": title,
                "content": content,
                "published": parse_published(entry),
                "source_name": source["name"],
                "domain": source["domain"],
                "source_hint": source["hint"],
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            })

        logger.info(f"  ✓ Found {len(articles)} entries")
        return articles

    except Exception as e:
        logger.error(f"  ❌ Failed to fetch {source['name']}: {e}")
        return []


def main() -> Path:
    """全ソースを取得し、新着のみを抽出して raw_articles.json に保存。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    seen = load_seen_urls()
    logger.info(f"Loaded {len(seen)} seen URLs")

    all_articles = []
    for source in RSS_SOURCES:
        all_articles.extend(fetch_one_source(source))

    # Filter out already-seen URLs
    new_articles = [a for a in all_articles if a["url"] not in seen]
    logger.info(
        f"Total fetched: {len(all_articles)}, "
        f"new: {len(new_articles)}, "
        f"duplicates skipped: {len(all_articles) - len(new_articles)}"
    )

    # Save raw articles for the next pipeline stage
    raw_path = DATA_DIR / "raw_articles.json"
    raw_path.write_text(
        json.dumps(new_articles, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(f"Wrote {len(new_articles)} new articles to {raw_path}")

    logger.info("Deferring seen_urls update until classification succeeds")

    return raw_path


if __name__ == "__main__":
    main()
