# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Microsoft AI 365** is an automated daily news curation pipeline that fetches RSS feeds from Microsoft and partner sources, classifies and summarizes them in Japanese using Azure OpenAI, and renders a static GitHub Pages site. It runs daily via GitHub Actions at 07:00 JST.

## Development Commands

```bash
# Setup
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

# Run full pipeline locally
python -m src.run_all

# Run individual stages
python -m src.fetch_feeds        # Stage 1: fetch RSS → data/raw_articles.json
python -m src.classify_summarize # Stage 2: LLM classify → data/articles.json
python -m src.render_site        # Stage 3: Jinja2 render → docs/index.html

# Backfill a specific date range (skips seen_urls filter)
START_DATE=2026-04-01 END_DATE=2026-04-30 python -m src.fetch_range
# Then run classify + render to complete backfill
```

## Authentication

This project uses **Entra ID (keyless) authentication** — no API key is stored anywhere.

**Local development**: Run `az login` once. `DefaultAzureCredential` picks up `AzureCliCredential` automatically.

**GitHub Actions**: Uses OIDC (Workload Identity Federation) via `azure/login@v2`. No `AZURE_CLIENT_SECRET` required.

## Environment Variables

Copy `.env.example` to `.env` and fill in:

| Variable | Description |
|---|---|
| `AZURE_OPENAI_BASE_URL` | Must end with `/openai/v1/` (trailing slash required) |
| `AZURE_OPENAI_DEPLOYMENT` | Deployment name (e.g. `gpt-5-4-mini`) |

`AZURE_OPENAI_API_KEY` is **not used**. Auth is handled by `DefaultAzureCredential` (`azure-identity`).

## Architecture

Three-stage pipeline in `src/`:

```
fetch_feeds.py → classify_summarize.py → render_site.py
```

**`src/config.py`** — Single source of truth for all settings: RSS source list (13 feeds), 11 category definitions, LLM concurrency/retry parameters, site timezone/title, file paths.

**`src/fetch_feeds.py`** — Parses RSS feeds, strips HTML, deduplicates via `data/seen_urls.json`, writes new articles to `data/raw_articles.json`.

**`src/classify_summarize.py`** — Calls Azure OpenAI Responses API with JSON Schema strict mode (5 concurrent async tasks, Tenacity retry). Reads `raw_articles.json`, merges classified results into `data/articles.json` (URL-deduplicated, persistent).

**`src/prompts.py`** — Defines the JSON Schema output structure and system/user prompts. Output fields: `category`, `is_partner`, `headline_ja`, `overview`, `whats_new`, `key_takeaway`, `tags`.

**`src/render_site.py`** — Jinja2 template engine. Filters articles to 24-hour frontpage window (90-day archive), splits into Microsoft/OpenAI/Anthropic zones, picks a featured story by category priority, writes `docs/index.html`.

**`src/run_all.py`** — Sequential orchestrator: fetch → classify → render. Exits 0 on success, 1 on failure.

**`src/fetch_range.py`** — Manual backfill tool. Fetches all sources for a `[START_DATE, END_DATE)` window, bypassing `seen_urls.json`. Writes to `raw_articles.json` for subsequent classify → render. Triggered by `manual-update.yml` workflow or via env vars locally.

## Data Files

| File | Persistence | Purpose |
|---|---|---|
| `data/articles.json` | Permanent | Full article database with LLM-generated fields |
| `data/seen_urls.json` | Permanent | Dedupe set; prevents re-fetching known URLs |
| `data/raw_articles.json` | Temporary | Intermediate; deleted after classify stage |

Each article record includes: `url`, `title`, `content`, `published`, `source_name`, `domain`, and LLM fields (`category`, `is_partner`, `headline_ja`, `overview`, `whats_new`, `key_takeaway`, `tags`, `processed_at`, `model`, `tokens_*`).

## Templates

`templates/index.html` and `templates/partials/` use Jinja2. Edit templates to change site layout without touching the data pipeline. Assets in `templates/assets/` are copied to `docs/assets/` on each render. `docs/` is entirely auto-generated — do not edit it directly.

## CI/CD

Three workflows in `.github/workflows/`:

| Workflow | Trigger | Purpose |
|---|---|---|
| `daily-update.yml` | `0 22 * * *` (UTC) = 07:00 JST + every 3 hours + `workflow_dispatch` + `repository_dispatch` | Full pipeline (`run_all`) + Pages deploy |
| `manual-update.yml` | `workflow_dispatch` (inputs: `start_date`, `end_date`) | Backfill range: `fetch_range` → `classify_summarize` → `render_site` |
| `main.yml` | `workflow_dispatch` | Azure OIDC login smoke test (`az account show`) |

The every-3-hour trigger on `daily-update.yml` is a differential fetch — exits early if no new articles.

**GitHub Secrets required:**

| Secret | Purpose |
|---|---|
| `AZURE_CLIENT_ID` | Service principal App ID (for OIDC) |
| `AZURE_TENANT_ID` | Azure tenant ID (for OIDC) |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID (for OIDC) |
| `AZURE_OPENAI_BASE_URL` | Endpoint ending with `/openai/v1/` |
| `AZURE_OPENAI_DEPLOYMENT` | Deployment name |

Auth flow: `azure/login@v2` (OIDC) → `DefaultAzureCredential` → `get_bearer_token_provider` → `AsyncOpenAI(api_key=token_provider)`.

GitHub Pages must be configured to use **GitHub Actions** as source (not "Deploy from branch").

## Key Implementation Details

- **Entra ID auth**: `DefaultAzureCredential` + `get_bearer_token_provider("https://cognitiveservices.azure.com/.default")` passed as `api_key` to `AsyncOpenAI`. Token refresh is automatic.
- **Responses API**: Uses `client.responses.create()` (not `chat.completions`). The `AZURE_OPENAI_BASE_URL` must end with `/openai/v1/` for this endpoint to resolve correctly.
- **Concurrency**: `LLM_CONCURRENCY = 5` async tasks controlled by `asyncio.Semaphore`. Reduce to 3 if hitting 429 rate limit errors.
- **Retry policy**: Tenacity with exponential backoff (4–60 s), max 4 attempts.
- **Japanese output**: LLM summaries are always in Japanese; English proper nouns (product names, version numbers) are kept in English per prompt instructions.
- **is_partner flag**: `True` only for OpenAI and Anthropic official blog posts; drives separate display zones in the site.
