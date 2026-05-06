"""
Microsoft AI 365 - Date Range Fetcher

指定した日付範囲の記事を全ソースから再取得し、既存の重複エントリを削除して
raw_articles.json に書き出す。その後、classify_summarize → render_site を
実行することで手動でサイトを更新できる。

使い方:
  START_DATE=2026-04-01 END_DATE=2026-04-30 python -m src.fetch_range
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.config import RSS_SOURCES, DATA_DIR, ARTICLES_JSON
from src.fetch_feeds import fetch_one_source, load_seen_urls, save_seen_urls

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def main(start_date: str, end_date: str) -> Path:
    """
    [start_date, end_date] の範囲（両端含む）の記事を取得し、
    articles.json から旧エントリを削除した上で raw_articles.json に書き出す。
    """
    start = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
    end   = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc) + timedelta(days=1)

    logger.info(f"Date range: {start_date} ~ {end_date} ({start.isoformat()} ~ {end.isoformat()})")

    # 1. 全ソースから全件取得（seen_urls フィルタなし・範囲外も含めて取得してから絞る）
    all_articles: list[dict] = []
    for source in RSS_SOURCES:
        all_articles.extend(fetch_one_source(source))
    logger.info(f"Total fetched across all sources: {len(all_articles)}")

    # 2. 公開日が [start, end) に収まる記事のみに絞る
    ranged = [
        a for a in all_articles
        if start <= parse_iso(a["published"]) < end
    ]
    logger.info(f"Articles in date range: {len(ranged)}")

    if not ranged:
        logger.warning("No articles found in the specified date range.")
        raw_path = DATA_DIR / "raw_articles.json"
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        raw_path.write_text("[]", encoding="utf-8")
        return raw_path

    # 3. URL で重複排除（複数ソースが同じ記事を配信するケース対策）
    by_url = {a["url"]: a for a in ranged}
    ranged = list(by_url.values())
    ranged_urls = {a["url"] for a in ranged}
    logger.info(f"After URL dedup: {len(ranged)} unique articles")

    # 4. articles.json から同 URL の旧エントリを削除（古い方を消して再分類）
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    existing: list[dict] = []
    if ARTICLES_JSON.exists():
        try:
            existing = json.loads(ARTICLES_JSON.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed to load articles.json: {e}. Treating as empty.")

    removed_count = sum(1 for a in existing if a["url"] in ranged_urls)
    cleaned = [a for a in existing if a["url"] not in ranged_urls]

    ARTICLES_JSON.write_text(
        json.dumps(cleaned, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(f"Removed {removed_count} old entries from articles.json ({len(cleaned)} remaining)")

    # 5. raw_articles.json に書き出し（classify_summarize が読む）
    raw_path = DATA_DIR / "raw_articles.json"
    raw_path.write_text(
        json.dumps(ranged, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(f"Wrote {len(ranged)} articles to {raw_path}")

    # 6. seen_urls を更新（日次バッチがこれらを再取得しないよう）
    seen = load_seen_urls()
    before = len(seen)
    seen.update(ranged_urls)
    save_seen_urls(seen)
    logger.info(f"Updated seen_urls: {before} → {len(seen)} URLs")

    return raw_path


if __name__ == "__main__":
    start = os.environ.get("START_DATE") or (sys.argv[1] if len(sys.argv) > 1 else None)
    end   = os.environ.get("END_DATE")   or (sys.argv[2] if len(sys.argv) > 2 else None)

    if not start or not end:
        print("Usage: START_DATE=YYYY-MM-DD END_DATE=YYYY-MM-DD python -m src.fetch_range")
        sys.exit(1)

    main(start, end)
