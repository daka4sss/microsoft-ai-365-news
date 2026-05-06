# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Microsoft AI 365** is an automated daily news curation pipeline that fetches RSS feeds from Microsoft and partner sources, classifies and summarizes them in Japanese using Azure OpenAI (GPT-5.4 mini, Responses API), and renders a static GitHub Pages site. It runs daily at 07:00 JST and every 3 hours for differential updates.

## Development Commands

```bash
# Setup
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

# Local auth (no API key — uses DefaultAzureCredential)
az login

# Run full pipeline locally
python -m src.run_all

# Run individual stages
python -m src.fetch_feeds        # Stage 1: RSS fetch → data/raw_articles.json
python -m src.classify_summarize # Stage 2: LLM classify → data/articles.json (+ updates seen_urls)
python -m src.render_site        # Stage 3: Jinja2 render → docs/index.html

# Backfill a date range (skips seen_urls filter; both endpoints inclusive)
START_DATE=2026-04-01 END_DATE=2026-04-30 python -m src.fetch_range
python -m src.classify_summarize
python -m src.render_site
```

The repo has no `.env.example`; create `.env` directly with `AZURE_OPENAI_BASE_URL` and `AZURE_OPENAI_DEPLOYMENT` (see `.env` already in repo for shape — do not commit secrets).

## Authentication

This project uses **Entra ID (keyless) authentication** — no API key is stored anywhere.

**Local development**: Run `az login` once. `DefaultAzureCredential` picks up `AzureCliCredential` automatically.

**GitHub Actions**: Uses OIDC (Workload Identity Federation) via `azure/login@v3`. No `AZURE_CLIENT_SECRET` required.

## Environment Variables

| Variable | Description |
|---|---|
| `AZURE_OPENAI_BASE_URL` | Must end with `/openai/v1/` (validated at startup; trailing slash required for Responses API) |
| `AZURE_OPENAI_DEPLOYMENT` | Deployment name (e.g. `gpt-5-4-mini`) |

`AZURE_OPENAI_API_KEY` is **not used**. Auth is handled by `DefaultAzureCredential` (`azure-identity`).

## Architecture

Three-stage pipeline in `src/`:

```
fetch_feeds.py → classify_summarize.py → render_site.py
```

**`src/config.py`** — Single source of truth: 14 RSS sources (13 Microsoft + 1 OpenAI), 11 categories (9 Microsoft + 2 Partner), category→CSS/color mappings, LLM concurrency/retry parameters, frontpage window (`DAYS_ON_FRONTPAGE = 30`), archive retention (`ARCHIVE_RETENTION_DAYS = 90`), site metadata, and `validate_env()`. `Anthropic` is a category but has no active RSS source — the partner zone renders only when articles exist.

**`src/fetch_feeds.py`** — Parses RSS feeds, strips HTML via BeautifulSoup, deduplicates against `data/seen_urls.json`, writes new articles to `data/raw_articles.json`. Per-source failures don't abort the run. **Important**: `seen_urls.json` is *not* updated here — it is updated by `classify_summarize.py` only for URLs that successfully classified, so failures stay in the retry pool.

**`src/classify_summarize.py`** — Calls Azure OpenAI Responses API with JSON Schema strict mode. 5 concurrent async tasks (`asyncio.Semaphore`), Tenacity retry (only on `RateLimitError`/`APIError`/`APITimeoutError`/`APIConnectionError` — auth/schema 4xx errors do not retry). Reads `raw_articles.json`, merges classified results into `data/articles.json` (URL-deduplicated, persistent), then updates `seen_urls.json`. Logs token usage and approximate cost (`$0.75/M input, $4.50/M output` for GPT-5.4 mini).

**`src/prompts.py`** — JSON Schema (strict mode: all fields required, `additionalProperties: false`) and system/user prompts. Output fields: `category`, `is_partner`, `headline_ja`, `overview` (150–250 chars), `whats_new` (200–400 chars), `key_takeaway` (150–350 chars), `tags` (3–5 keywords). All summaries in Japanese; English proper nouns kept as-is.

**`src/render_site.py`** — Jinja2 template engine. Filters articles to past 30 days for the frontpage (falls back to 3 days if empty), prunes to 90-day retention, splits into Microsoft/OpenAI/Anthropic zones, picks a featured story by category priority (Foundry > Overview > M365 Copilot > Agent 365 > …), writes `docs/index.html`, copies `templates/assets/` → `docs/assets/`, writes `.nojekyll`.

**`src/run_all.py`** — Sequential orchestrator: fetch → classify → render. Exits 0 on success, 1 on failure.

**`src/fetch_range.py`** — Manual backfill tool. Fetches all sources for an inclusive `[START_DATE, END_DATE]` window (internally adds 1 day to end), bypassing `seen_urls.json`. Writes to `raw_articles.json` for subsequent classify → render. Triggered by `manual-update.yml` workflow or via env vars locally.

## Data Files

| File | Persistence | Purpose |
|---|---|---|
| `data/articles.json` | Permanent (committed) | Full article database with LLM-generated fields; source of truth for rendering |
| `data/seen_urls.json` | Permanent (committed) | Dedupe set of *successfully classified* URLs |
| `data/raw_articles.json` | Temporary (gitignored) | Intermediate handoff between fetch and classify stages; overwritten each run |

Each persisted article record contains: `url`, `title`, `content`, `published`, `source_name`, `domain`, `source_hint`, `fetched_at`, plus LLM fields (`category`, `is_partner`, `headline_ja`, `overview`, `whats_new`, `key_takeaway`, `tags`, `processed_at`, `model`, `tokens_input/output/total`).

## Templates

`templates/` is the source of all UI; `docs/` is entirely auto-generated and **must not be edited directly**. Layout:

- `templates/index.html` — main page; includes header, optional featured, Today's Stories grid, partner zones (OpenAI / Anthropic), sidebar, footer
- `templates/partials/` — `header.html` (brand + category nav), `featured.html`, `story.html` (collapsible 概要 / What's New / Key Takeaway), `sidebar.html` (categories, trending tags, sources, newsletter CTA), `footer.html`
- `templates/assets/style.css` — all styles (light/dark theme via `data-theme`)
- `templates/assets/app.js` — theme toggle, category filter (persisted in `localStorage`), unread-article tracking with "mark all read" button

Custom Jinja filters: `category_css` and `category_dot` (defined in `render_site.make_env`).

## CI/CD

Three workflows in `.github/workflows/`:

| Workflow | Trigger | Purpose |
|---|---|---|
| `daily-update.yml` | `0 22 * * *` UTC (07:00 JST) + `0 */3 * * *` (3-hour diff) + `workflow_dispatch` + `repository_dispatch` (`rss-updated`) | Full pipeline (`run_all`) → commit `data/`+`docs/` → Pages deploy |
| `manual-update.yml` | `workflow_dispatch` (inputs: `start_date`, `end_date`) | Backfill range: `fetch_range` → `classify_summarize` → `render_site` → Pages deploy |
| `main.yml` | `workflow_dispatch` | Azure OIDC login smoke test (`az account show`) |

The 3-hour cron is a differential fetch — exits cheaply if no new articles (no LLM calls). Both update workflows share `concurrency.group: daily-update` to prevent overlapping runs. The `repository_dispatch` trigger lets external services (IFTTT/Zapier/etc.) signal new content via the GitHub API.

Workflow stack: `actions/checkout@v6`, `actions/setup-python@v6` (Python 3.11), `azure/login@v3`, `actions/configure-pages@v5`, `actions/upload-pages-artifact@v3`, `actions/deploy-pages@v4` (Node.js 24-compatible versions).

**GitHub Secrets required:**

| Secret | Purpose |
|---|---|
| `AZURE_CLIENT_ID` | Service principal App ID (for OIDC) |
| `AZURE_TENANT_ID` | Azure tenant ID (for OIDC) |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID (for OIDC) |
| `AZURE_OPENAI_BASE_URL` | Endpoint ending with `/openai/v1/` |
| `AZURE_OPENAI_DEPLOYMENT` | Deployment name |

Auth flow: `azure/login@v3` (OIDC) → `DefaultAzureCredential` → `get_bearer_token_provider("https://cognitiveservices.azure.com/.default")` → wrapped as async callable → passed as `api_key` to `AsyncOpenAI`. Token refresh is automatic.

GitHub Pages must be configured to use **GitHub Actions** as source (not "Deploy from branch").

## Key Implementation Details

- **Responses API, not Chat Completions**: `client.responses.create()` is used. Structured output goes in `text.format` (not `response_format`). The base URL must end with `/openai/v1/` for the Responses endpoint to resolve.
- **JSON Schema strict mode constraints**: all fields required, `additionalProperties: false`, no `minLength`/`maxLength`/`format`. Optional fields are expressed as `["type", "null"]`.
- **Concurrency**: `LLM_CONCURRENCY = 5`. Drop to 3 if hitting 429s; or raise `Tokens per Minute` in Azure portal.
- **Retry policy**: Tenacity exponential backoff, 4–60 s, max 4 attempts (1 initial + 3 retries). Auth/schema errors do not retry. Partial failures don't abort the batch (`process_one` returns `None` on error and is filtered out).
- **Content truncation**: article body is truncated to `MAX_CONTENT_CHARS = 6000` before being sent to the LLM.
- **`is_partner` flag**: `True` only for OpenAI/Anthropic *official* posts (drives separate site zones); a Microsoft post mentioning OpenAI is still `False`.
- **Featured selection**: `pick_featured` ranks by category priority (Microsoft Foundry highest, partners lowest) then `published` desc; the featured article is excluded from the Microsoft grid below it.
- **Source hints**: each RSS source has a `hint` field passed to the LLM as a soft bias toward a likely category (the model still decides based on content).
