"""
Microsoft AI 365 - LLM Classifier & Summarizer

Azure OpenAI Responses API (GPT-5.4 mini) を使い、各記事を:
- 11カテゴリのいずれかに分類
- Overview / What's New / Key Takeaway の3セクションで日本語要約
- タグ抽出

【設計のポイント】
1. Responses API (`client.responses.create`) を使用
   - Chat Completions と異なり base_url は `/openai/v1/` で終わる必要あり
   - 構造化出力は `text.format` で指定（`response_format` ではない）
2. JSON Schema strict mode で出力を100%構造化
3. 5並列処理で処理時間を短縮
4. Tenacity で 429/timeout を自動リトライ（最大4試行）
5. 1記事失敗しても全体は継続（return_exceptions=True）
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from openai import AsyncOpenAI, RateLimitError, APIError, APITimeoutError, APIConnectionError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    AsyncRetrying,
)

from src.config import (
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_BASE_URL,
    AZURE_OPENAI_DEPLOYMENT,
    LLM_CONCURRENCY,
    LLM_MAX_ATTEMPTS,
    LLM_RETRY_WAIT_MIN,
    LLM_RETRY_WAIT_MAX,
    LLM_TIMEOUT,
    MAX_OUTPUT_TOKENS,
    DATA_DIR,
    ARTICLES_JSON,
    validate_env,
)
from src.prompts import ARTICLE_SCHEMA, SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# ============================================================
# Async client setup
# ============================================================
def make_client() -> AsyncOpenAI:
    """
    Azure OpenAI Responses API用クライアントを生成。

    重要: AzureOpenAI クラスではなく OpenAI 互換の AsyncOpenAI を使う。
    base_url は必ず `/openai/v1/` で終わる。
    """
    validate_env()
    return AsyncOpenAI(
        api_key=AZURE_OPENAI_API_KEY,
        base_url=AZURE_OPENAI_BASE_URL,
        timeout=LLM_TIMEOUT,
        max_retries=0,  # We handle retries ourselves via tenacity
    )


# ============================================================
# Single article processor
# ============================================================
async def call_responses_api(client: AsyncOpenAI, article: dict) -> dict:
    """
    1記事を Responses API で処理。

    リトライポリシー:
    - 対象: RateLimitError, APIError, APITimeoutError, APIConnectionError のみ
    - 試行回数: 最大4回（初回 + 3リトライ）
    - 待機: 指数バックオフ 4-60秒
    - 認証エラー(401)・スキーマエラー(400)はリトライしない
    """
    retryer = AsyncRetrying(
        retry=retry_if_exception_type(
            (RateLimitError, APIError, APITimeoutError, APIConnectionError)
        ),
        stop=stop_after_attempt(LLM_MAX_ATTEMPTS),
        wait=wait_exponential(
            multiplier=2,
            min=LLM_RETRY_WAIT_MIN,
            max=LLM_RETRY_WAIT_MAX,
        ),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )

    async for attempt in retryer:
        with attempt:
            response = await client.responses.create(
                model=AZURE_OPENAI_DEPLOYMENT,
                input=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_prompt(article)},
                ],
                # Responses API specific: structured output goes in `text.format`
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "ArticleAnalysis",
                        "schema": ARTICLE_SCHEMA,
                        "strict": True,
                    }
                },
                max_output_tokens=MAX_OUTPUT_TOKENS,
            )
            return response


def merge_result(article: dict, response) -> dict:
    """API レスポンスを記事dictにマージ。"""
    parsed = json.loads(response.output_text)
    return {
        **article,
        **parsed,
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "model": AZURE_OPENAI_DEPLOYMENT,
        "tokens_input": response.usage.input_tokens,
        "tokens_output": response.usage.output_tokens,
        "tokens_total": response.usage.total_tokens,
    }


async def process_one(
    client: AsyncOpenAI,
    semaphore: asyncio.Semaphore,
    article: dict,
    idx: int,
    total: int,
) -> dict | None:
    """1記事処理（セマフォで並列数制御）。失敗時はNoneを返す。"""
    async with semaphore:
        title_short = article["title"][:60]
        try:
            response = await call_responses_api(client, article)
            result = merge_result(article, response)
            logger.info(
                f"[{idx}/{total}] ✓ {result['category']:20s} | "
                f"{result['tokens_total']:5d}tok | {title_short}"
            )
            return result
        except Exception as e:
            logger.error(f"[{idx}/{total}] ❌ FAILED: {title_short} | {type(e).__name__}: {e}")
            return None


# ============================================================
# Main pipeline
# ============================================================
async def run() -> Path:
    """新着記事を全て処理し、articles.json に追記保存。"""
    raw_path = DATA_DIR / "raw_articles.json"
    if not raw_path.exists():
        logger.warning(f"No raw articles found at {raw_path}. Run fetch_feeds.py first.")
        return ARTICLES_JSON

    new_articles = json.loads(raw_path.read_text(encoding="utf-8"))
    logger.info(f"Loaded {len(new_articles)} new articles to process")

    if not new_articles:
        logger.info("Nothing to process.")
        return ARTICLES_JSON

    # Concurrency control
    semaphore = asyncio.Semaphore(LLM_CONCURRENCY)
    logger.info(
        f"Starting LLM processing | concurrency={LLM_CONCURRENCY} | "
        f"max_attempts={LLM_MAX_ATTEMPTS} | model={AZURE_OPENAI_DEPLOYMENT}"
    )

    client = make_client()
    try:
        total = len(new_articles)
        tasks = [
            process_one(client, semaphore, article, i + 1, total)
            for i, article in enumerate(new_articles)
        ]
        results = await asyncio.gather(*tasks)
    finally:
        await client.close()

    # Filter out failures
    succeeded = [r for r in results if r is not None]
    failed_count = len(results) - len(succeeded)

    logger.info(f"📊 Results: {len(succeeded)} succeeded, {failed_count} failed")

    if succeeded:
        total_tokens = sum(r["tokens_total"] for r in succeeded)
        # GPT-5.4 mini pricing: $0.75/M input, $4.50/M output
        total_input = sum(r["tokens_input"] for r in succeeded)
        total_output = sum(r["tokens_output"] for r in succeeded)
        cost_usd = (total_input * 0.75 + total_output * 4.50) / 1_000_000
        logger.info(
            f"💰 Token usage: {total_tokens:,} total | "
            f"in={total_input:,} out={total_output:,} | "
            f"~${cost_usd:.4f}"
        )

    # Append to articles.json (the source of truth for rendering)
    existing = []
    if ARTICLES_JSON.exists():
        try:
            existing = json.loads(ARTICLES_JSON.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed to load existing articles.json: {e}. Starting fresh.")

    # Merge: deduplicate by URL (newer overrides older)
    by_url = {a["url"]: a for a in existing}
    for r in succeeded:
        by_url[r["url"]] = r
    merged = sorted(by_url.values(), key=lambda x: x.get("published", ""), reverse=True)

    ARTICLES_JSON.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(f"💾 Saved {len(merged)} total articles to {ARTICLES_JSON}")

    return ARTICLES_JSON


def main() -> Path:
    return asyncio.run(run())


if __name__ == "__main__":
    main()
