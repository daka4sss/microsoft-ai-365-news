"""
Microsoft AI 365 - LLM Prompts and JSON Schema

Responses API の `text.format` に渡す JSON Schema と、
記事分類・要約用のプロンプトを集約。

【重要】strict=true モードでは:
  - すべてのフィールドが required
  - additionalProperties: false 必須
  - minLength/maxLength/format などは未対応
  → optional は ["string", "null"] で表現
"""
from src.config import ALL_CATEGORIES


# ============================================================
# JSON Schema for structured output (strict mode)
# ============================================================
ARTICLE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "category",
        "is_partner",
        "headline_ja",
        "overview",
        "whats_new",
        "key_takeaway",
        "tags",
    ],
    "properties": {
        "category": {
            "type": "string",
            "enum": ALL_CATEGORIES,
            "description": (
                "記事の最適なカテゴリを11個から1つ選ぶ。"
                "Microsoft 公式発信は9つのMSカテゴリのいずれか。"
                "OpenAI 公式は 'OpenAI'、Anthropic 公式は 'Anthropic'。"
            ),
        },
        "is_partner": {
            "type": "boolean",
            "description": (
                "記事が OpenAI または Anthropic の公式発信である場合のみ true。"
                "Microsoft 発信記事の中で OpenAI/Anthropic に言及があるだけなら false。"
            ),
        },
        "headline_ja": {
            "type": "string",
            "description": (
                "日本語の見出し（30-50文字）。元タイトルが英語なら自然な日本語に翻訳。"
                "技術用語（Foundry, Copilot, Agent等の固有名詞）はカタカナ化せず原文のまま。"
            ),
        },
        "overview": {
            "type": "string",
            "description": (
                "【概要】記事全体が何についてか、背景含めて日本語で150-250文字。"
                "読者がこの記事を読むかどうか判断できる粒度で書く。"
                "発表元、対象製品、文脈（Preview/GA/Update等）を含める。"
            ),
        },
        "whats_new": {
            "type": "string",
            "description": (
                "【What's New / Update】何が新しく追加・変更されたかを日本語で200-400文字。"
                "具体的な機能名、リージョン名、バージョン番号、価格など定量情報を必ず含める。"
                "GA/Preview/Deprecation のステータスを明記。箇条書きでなく文章で。"
            ),
        },
        "key_takeaway": {
            "type": "string",
            "description": (
                "【Key Takeaway】エンタープライズ顧客や開発者にとっての示唆を日本語で150-350文字。"
                "「なぜ重要か」「誰に影響するか」「次に取るべきアクション」を含める。"
                "日本市場での影響、競合製品との比較、既存顧客の移行パスなど実務観点で。"
            ),
        },
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "関連キーワード3-5個。製品名・機能名（例: 'APIM AI Gateway', 'Agent Service', 'Entra Agent ID'）。"
                "一般語（'AI', '更新'など）は避ける。"
            ),
        },
    },
}


# ============================================================
# System prompt - sets persona and high-level rules
# ============================================================
SYSTEM_PROMPT = """あなたは Microsoft AI 技術記事の分類・要約エンジンです。

【あなたの役割】
- Microsoft AI、Azure、Copilot、Foundry、エージェント技術に関する記事を分析
- エンタープライズ顧客（特に日本の金融・公共・製造業）に向けて翻訳・要約
- 技術的な正確性を保ちつつ、日本語として自然な文章を書く

【守るべきルール】
1. すべての要約は日本語で書く
2. 製品名・機能名・サービス名は英語のまま残す（例: Foundry, Agent Service, APIM AI Gateway）
3. 推測や誇張をしない。記事に書かれていない情報は含めない
4. 数値（リージョン名、価格、バージョン）は正確に転記
5. ステータス（GA/Public Preview/Private Preview/Deprecation）を明記
6. JSON Schema に厳密に従う
"""


def build_user_prompt(article: dict) -> str:
    """Build the user message for a single article."""
    return f"""以下の記事を分析し、JSON スキーマに従って出力してください。

【記事メタ情報】
- タイトル: {article['title']}
- ソース: {article['source_name']} ({article['domain']})
- 公開日: {article.get('published', 'unknown')}
- ソース推定カテゴリ: {article.get('source_hint', 'unknown')}
  （※あくまでヒント。記事内容を優先して判定）

【記事本文】
{article.get('content', '')[:6000]}

【出力指示】
1. category: 11カテゴリから1つ選択（記事内容ベースで判定）
2. is_partner: OpenAI/Anthropic公式発信のみ true
3. headline_ja: 日本語見出し30-50文字
4. overview: 概要 150-250文字
5. whats_new: 変更点 200-400文字（最重要）
6. key_takeaway: エンタープライズ示唆 150-350文字
7. tags: 関連キーワード3-5個

合計で500-1000文字の充実した日本語要約を生成してください。"""
