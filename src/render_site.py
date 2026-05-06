"""
Microsoft AI 365 - Site Renderer

articles.json から Jinja2 テンプレートを使って静的HTMLを生成。

【設計のポイント】
1. データ層(articles.json) と表示層(templates/) を完全分離
2. デザイン変更時はテンプレートのみ編集（データ取得は触らない）
3. 日付別アーカイブも生成（過去のスナップショットへリンク可能）
4. カテゴリ集計、トレンド、ソース別カウントを動的計算
"""
import json
import logging
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.config import (
    ARTICLES_JSON,
    DOCS_DIR,
    TEMPLATES_DIR,
    ALL_CATEGORIES,
    MICROSOFT_CATEGORIES,
    PARTNER_CATEGORIES,
    CATEGORY_CSS,
    SITE_TITLE,
    SITE_TAGLINE,
    SITE_AUTHOR,
    SITE_TIMEZONE,
    DAYS_ON_FRONTPAGE,
    ARCHIVE_RETENTION_DAYS,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

JST = ZoneInfo(SITE_TIMEZONE)


# ============================================================
# Helpers
# ============================================================
def parse_iso(s: str) -> datetime:
    """ISO 8601 文字列を datetime に変換（fallback 付き）。"""
    if not s:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def relative_time(dt: datetime, now: datetime) -> str:
    """'2h ago' のような相対時刻表現。"""
    delta = now - dt
    if delta.days > 7:
        return dt.astimezone(JST).strftime("%b %d")
    if delta.days >= 1:
        return f"{delta.days}d ago"
    hours = delta.seconds // 3600
    if hours >= 1:
        return f"{hours}h ago"
    minutes = max(1, delta.seconds // 60)
    return f"{minutes}m ago"


def category_dot(category: str) -> str:
    """カテゴリ別の色（CSS の cat-dot で使用）。"""
    colors = {
        "Microsoft Overview": "#605e5c",
        "M365 Copilot": "#b8004e",
        "Copilot Studio": "#5c2d91",
        "Microsoft Foundry": "#0078d4",
        "Azure AI Infra": "#00a4ef",
        "Data & Fabric": "#0b6b4f",
        "Dev Tools": "#2d2d2d",
        "AI Security": "#a4262c",
        "OpenAI": "#10a37f",
        "Anthropic": "#cc785c",
    }
    return colors.get(category, "#605e5c")


# ============================================================
# Aggregations
# ============================================================
def split_by_zone(articles: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """記事を Microsoft / OpenAI / Anthropic の3ゾーンに分割。"""
    ms = [a for a in articles if a.get("category") in MICROSOFT_CATEGORIES]
    openai = [a for a in articles if a.get("category") == "OpenAI"]
    anthropic = [a for a in articles if a.get("category") == "Anthropic"]
    return ms, openai, anthropic


def category_counts(articles: list[dict]) -> dict[str, int]:
    """カテゴリ別の記事数。"""
    counts = Counter(a.get("category") for a in articles)
    return {c: counts.get(c, 0) for c in ALL_CATEGORIES}


def tags_by_category(articles: list[dict], top_per_cat: int = 5) -> list[dict]:
    """各タグの主出現カテゴリーを判定し、カテゴリー別に頻度降順で集約。

    戻り値の構造:
        [
            {"category": "Microsoft Foundry",
             "tags": [{"name": "Foundry", "count": 12}, ...]},
            ...
        ]
    """
    tag_cat_counts: dict[str, Counter] = defaultdict(Counter)
    for art in articles:
        cat = art.get("category", "")
        if not cat:
            continue
        for tag in art.get("tags", []):
            tag_cat_counts[tag][cat] += 1

    primary: dict[str, tuple[str, int]] = {}
    for tag, cat_counts in tag_cat_counts.items():
        top_cat, _ = cat_counts.most_common(1)[0]
        primary[tag] = (top_cat, sum(cat_counts.values()))

    groups: dict[str, list[dict]] = defaultdict(list)
    for tag, (cat, total) in primary.items():
        groups[cat].append({"name": tag, "count": total})

    result = []
    for cat in ALL_CATEGORIES:
        if cat not in groups:
            continue
        sorted_tags = sorted(groups[cat], key=lambda t: (-t["count"], t["name"]))
        result.append({
            "category": cat,
            "tags": sorted_tags[:top_per_cat],
        })
    return result


def source_counts(articles: list[dict]) -> list[dict]:
    """ソース別の記事数（多い順）。"""
    counter = Counter(a.get("domain") for a in articles)
    return [
        {"domain": domain, "count": count}
        for domain, count in counter.most_common()
    ]


def filter_by_date_range(articles: list[dict], days: int) -> list[dict]:
    """過去N日以内の記事のみ抽出。"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return [a for a in articles if parse_iso(a.get("published", "")) >= cutoff]


def pick_featured(articles: list[dict]) -> dict | None:
    """最高スコア記事を Featured に。スコアフィールドがないので published 日と category 重要度で代用。"""
    if not articles:
        return None
    # Microsoft Foundry > Microsoft Overview > その他 の順で優先
    priority = {
        "Microsoft Foundry": 100,
        "Microsoft Overview": 90,
        "M365 Copilot": 80,
        "Copilot Studio": 70,
        "Azure AI Infra": 65,
        "Data & Fabric": 60,
        "Dev Tools": 55,
        "AI Security": 50,
        "OpenAI": 40,
        "Anthropic": 40,
    }

    def featured_score(a: dict) -> tuple[int, str]:
        return (priority.get(a.get("category", ""), 0), a.get("published", ""))

    return max(articles, key=featured_score)


# ============================================================
# Rendering
# ============================================================
def make_env() -> Environment:
    """Jinja2 環境セットアップ。"""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    # Custom filters for templates
    env.filters["category_css"] = lambda c: CATEGORY_CSS.get(c, "cat-overview")
    env.filters["category_dot"] = category_dot
    return env


def build_context(articles_all: list[dict]) -> dict:
    """テンプレートに渡すコンテキストを構築。"""
    now = datetime.now(timezone.utc)

    # Today's stories: 過去24時間
    todays = filter_by_date_range(articles_all, DAYS_ON_FRONTPAGE)
    if not todays:
        # 24時間以内に記事がなければ過去3日分にフォールバック
        todays = filter_by_date_range(articles_all, 3)

    ms, openai, anthropic = split_by_zone(todays)

    # Add display fields (relative time)
    for art in todays:
        art["_published_dt"] = parse_iso(art.get("published", ""))
        art["_relative_time"] = relative_time(art["_published_dt"], now)

    featured = pick_featured(ms) or pick_featured(todays)

    # Sort each zone by published desc
    ms.sort(key=lambda a: a.get("published", ""), reverse=True)
    openai.sort(key=lambda a: a.get("published", ""), reverse=True)
    anthropic.sort(key=lambda a: a.get("published", ""), reverse=True)

    # Microsoft stories excluding the featured one
    ms_non_featured = [a for a in ms if a is not featured]

    return {
        "site_title": SITE_TITLE,
        "site_tagline": SITE_TAGLINE,
        "site_author": SITE_AUTHOR,
        "now_jst": now.astimezone(JST),
        "today_str": now.astimezone(JST).strftime("%a, %b %d, %Y"),
        "update_time_jst": now.astimezone(JST).strftime("%H:%M JST"),
        "featured": featured,
        "ms_articles": ms_non_featured,
        "openai_articles": openai,
        "anthropic_articles": anthropic,
        "total_today": len(todays),
        "total_ms": len(ms),
        "total_openai": len(openai),
        "total_anthropic": len(anthropic),
        "total_all_time": len(articles_all),
        "total_this_month": len(filter_by_date_range(articles_all, 30)),
        "category_counts": category_counts(todays),
        "ms_categories": MICROSOFT_CATEGORIES,
        "partner_categories": PARTNER_CATEGORIES,
        "all_categories": ALL_CATEGORIES,
        "tag_groups": tags_by_category(todays, top_per_cat=5),
        "sources": source_counts(todays)[:12],
        "n_sources": len(source_counts(todays)),
    }


def render_index(env: Environment, context: dict) -> None:
    """index.html を生成。"""
    template = env.get_template("index.html")
    html = template.render(**context)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    out = DOCS_DIR / "index.html"
    out.write_text(html, encoding="utf-8")
    logger.info(f"📄 Rendered {out} ({len(html):,} chars)")


def copy_assets() -> None:
    """static アセット（CSS/JS）をコピー。templates/assets/ があれば docs/assets/ に。"""
    src_assets = TEMPLATES_DIR / "assets"
    if src_assets.exists():
        dst = DOCS_DIR / "assets"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src_assets, dst)
        logger.info(f"📦 Copied assets to {dst}")


def write_nojekyll() -> None:
    """GitHub Pages の Jekyll 処理を無効化（_ で始まるファイルが消えるのを防ぐ）。"""
    (DOCS_DIR / ".nojekyll").touch()


# ============================================================
# Main
# ============================================================
def main() -> None:
    if not ARTICLES_JSON.exists():
        logger.error(f"No articles.json found at {ARTICLES_JSON}")
        return

    articles = json.loads(ARTICLES_JSON.read_text(encoding="utf-8"))
    logger.info(f"Loaded {len(articles)} articles from {ARTICLES_JSON}")

    # Prune very old articles
    articles = filter_by_date_range(articles, ARCHIVE_RETENTION_DAYS)
    logger.info(f"After {ARCHIVE_RETENTION_DAYS}-day retention: {len(articles)} articles")

    context = build_context(articles)
    logger.info(
        f"Context: featured={'yes' if context['featured'] else 'none'} | "
        f"MS={context['total_ms']} OpenAI={context['total_openai']} Anthropic={context['total_anthropic']}"
    )

    env = make_env()
    render_index(env, context)
    copy_assets()
    write_nojekyll()
    logger.info("✅ Site rendering complete")


if __name__ == "__main__":
    main()
