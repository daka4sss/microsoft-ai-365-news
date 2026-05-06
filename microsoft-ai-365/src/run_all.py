"""
Microsoft AI 365 - Pipeline Orchestrator

3段階パイプラインを順次実行:
1. fetch_feeds.py     : RSS取得・重複除外
2. classify_summarize : Azure OpenAI で分類・要約
3. render_site        : Jinja2 で HTML 生成

ローカル実行・GitHub Actions の両方で利用可能。
"""
import logging
import sys

from src.fetch_feeds import main as fetch_main
from src.classify_summarize import main as classify_main
from src.render_site import main as render_main

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def main() -> int:
    """Run the full pipeline. Returns exit code."""
    try:
        logger.info("=" * 60)
        logger.info("STEP 1/3 — Fetching RSS feeds")
        logger.info("=" * 60)
        fetch_main()

        logger.info("=" * 60)
        logger.info("STEP 2/3 — Classifying & summarizing with Azure OpenAI")
        logger.info("=" * 60)
        classify_main()

        logger.info("=" * 60)
        logger.info("STEP 3/3 — Rendering site")
        logger.info("=" * 60)
        render_main()

        logger.info("✅ Pipeline complete")
        return 0
    except Exception as e:
        logger.exception(f"❌ Pipeline failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
