"""
Microsoft AI 365 - 中央設定ファイル

このファイルだけを編集すれば、新しいRSSソースの追加・カテゴリの変更・
並列数の調整などが可能。コードの他の箇所は触らずに済む設計。
"""
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# Paths
# ============================================================
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
TEMPLATES_DIR = ROOT / "templates"

ARTICLES_JSON = DATA_DIR / "articles.json"
SEEN_URLS_JSON = DATA_DIR / "seen_urls.json"

# ============================================================
# Categories (11 total: 9 Microsoft + 2 Partner)
# ============================================================
MICROSOFT_CATEGORIES = [
    "Overview",
    "M365 Copilot",
    "Copilot Studio",
    "Foundry",
    "Azure AI Infra",
    "Data & Fabric",
    "Dev Tools",
    "AI Security",
]

PARTNER_CATEGORIES = [
    "OpenAI",
    "Anthropic",
]

ALL_CATEGORIES = MICROSOFT_CATEGORIES + PARTNER_CATEGORIES

# Category → CSS class mapping (matches v3 HTML mockup)
CATEGORY_CSS = {
    "Overview": "cat-overview",
    "M365 Copilot": "cat-m365",
    "Copilot Studio": "cat-studio",
    "Foundry": "cat-foundry",
    "Azure AI Infra": "cat-infra",
    "Data & Fabric": "cat-data",
    "Dev Tools": "cat-dev",
    "AI Security": "cat-security",
    "OpenAI": "cat-openai",
    "Anthropic": "cat-anthropic",
}

# ============================================================
# RSS Feed sources
# Each source is given a "hint" field that helps the LLM
# bias categorization toward the most likely category for that source.
# ============================================================
RSS_SOURCES = [
    # --- Microsoft Official ---
    {
        "name": "Microsoft Source (News)",
        "url": "https://news.microsoft.com/feed/",
        "domain": "news.microsoft.com",
        "hint": "Overview",
    },
    {
        "name": "Official Microsoft Blog",
        "url": "https://blogs.microsoft.com/feed/",
        "domain": "blogs.microsoft.com",
        "hint": "Overview",
    },
    {
        "name": "Microsoft AI Blog",
        "url": "https://blogs.microsoft.com/ai/feed/",
        "domain": "blogs.microsoft.com/ai",
        "hint": "Foundry",
    },
    {
        "name": "Azure Blog",
        "url": "https://azure.microsoft.com/en-us/blog/feed/",
        "domain": "azure.microsoft.com",
        "hint": "Foundry",
    },
    {
        "name": "Microsoft 365 Blog",
        "url": "https://www.microsoft.com/en-us/microsoft-365/blog/feed/",
        "domain": "microsoft.com/microsoft-365",
        "hint": "M365 Copilot",
    },
    {
        "name": "M365 Dev Blog",
        "url": "https://devblogs.microsoft.com/microsoft365dev/feed/",
        "domain": "devblogs.microsoft.com",
        "hint": "M365 Copilot",
    },
    {
        "name": "Power Platform Blog",
        "url": "https://www.microsoft.com/en-us/power-platform/blog/feed/",
        "domain": "powerplatform.microsoft.com",
        "hint": "Copilot Studio",
    },
    {
        "name": "Microsoft Fabric Blog",
        "url": "https://community.fabric.microsoft.com/oxcrx34285/rss/board?board.id=fbc_fabricupdatesblogs",
        "domain": "community.fabric.microsoft.com",
        "hint": "Data & Fabric",
    },
    {
        "name": "Microsoft Security Blog",
        "url": "https://www.microsoft.com/en-us/security/blog/feed/",
        "domain": "microsoft.com/security",
        "hint": "AI Security",
    },
    {
        "name": "GitHub Blog",
        "url": "https://github.blog/feed/",
        "domain": "github.blog",
        "hint": "Dev Tools",
    },
    {
        "name": "Tech Community - Microsoft Foundry",
        "url": "https://techcommunity.microsoft.com/t5/s/gxcuf89792/rss/board?board.id=azure-ai-foundry-blog",
        "domain": "techcommunity.microsoft.com",
        "hint": "Foundry",
    },
    {
        "name": "Tech Community - Azure Integration Services",
        "url": "https://techcommunity.microsoft.com/t5/s/gxcuf89792/rss/board?board.id=IntegrationsonAzureBlog",
        "domain": "techcommunity.microsoft.com",
        "hint": "Azure Integration Services",
    },
    {
        "name": "Microsoft Foundry Dev Blog",
        "url": "https://devblogs.microsoft.com/foundry/feed/",
        "domain": "devblogs.microsoft.com/foundry",
        "hint": "Foundry",
    },
    # --- Partner Official ---
    {
        "name": "OpenAI News",
        "url": "https://openai.com/news/rss.xml",
        "domain": "openai.com",
        "hint": "OpenAI",
    },
]

# ============================================================
# Anthropic Custom Collector
# ============================================================
# Anthropic は公式 RSS を提供していないため、sitemap.xml + 個別記事ページの
# OG メタタグから情報を取得する独立 collector を src/sources/anthropic.py に実装。
# enabled=False に切り替えるだけで完全無効化できる (RSS パイプラインへの影響ゼロ)。
ANTHROPIC_CONFIG = {
    "enabled": True,
    "sitemap_url": "https://www.anthropic.com/sitemap.xml",
    "path_prefixes": ["/news/", "/engineering/"],  # News と Engineering 両方対象
    "lookback_days": 15,                            # 差分実行時の過去N日窓
    "fetch_concurrency": 3,                         # 個別ページ並列取得数
    "request_timeout": 15,                          # 個別記事ページ用タイムアウト(秒)
    "sitemap_timeout": 30,                          # sitemap.xml 用タイムアウト(秒)
}

# ============================================================
# Runtime settings
# ============================================================

# How many days back to keep on the front page
DAYS_ON_FRONTPAGE = 30

# How many days of articles to keep total (older are pruned)
ARCHIVE_RETENTION_DAYS = 90

# Concurrency for Azure OpenAI calls
LLM_CONCURRENCY = 5

# Retry policy
LLM_MAX_ATTEMPTS = 4              # initial + 3 retries
LLM_RETRY_WAIT_MIN = 4            # seconds
LLM_RETRY_WAIT_MAX = 60           # seconds
LLM_TIMEOUT = 60                  # per-request timeout

# Article body truncation before sending to LLM (saves tokens)
MAX_CONTENT_CHARS = 6000

# LLM output cap (allows ~500-1000 char Japanese summary across 3 sections)
MAX_OUTPUT_TOKENS = 1500

# Site metadata
SITE_TITLE = "Microsoft News"
SITE_TAGLINE = "Daily Tech Curation"
SITE_AUTHOR = "@daka1"
SITE_TIMEZONE = "Asia/Tokyo"

# ============================================================
# Azure OpenAI - Responses API
# Pulled from environment variables (set via GitHub Secrets)
# ============================================================
AZURE_OPENAI_BASE_URL = os.environ.get("AZURE_OPENAI_BASE_URL", "")
AZURE_OPENAI_DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-5-4-mini")


def validate_env() -> None:
    """Fail fast if required env vars are missing."""
    missing = []
    if not AZURE_OPENAI_BASE_URL:
        missing.append("AZURE_OPENAI_BASE_URL")
    if not AZURE_OPENAI_DEPLOYMENT:
        missing.append("AZURE_OPENAI_DEPLOYMENT")
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            f"See .env.example for setup."
        )
    if not AZURE_OPENAI_BASE_URL.endswith("/openai/v1/"):
        raise RuntimeError(
            f"AZURE_OPENAI_BASE_URL must end with '/openai/v1/'. "
            f"Got: {AZURE_OPENAI_BASE_URL}"
        )
