# Microsoft AI 365 — Daily Tech Curation

Microsoft AI / Azure / Copilot / Foundry / Agent / Security に関する公式ブログを毎日キュレーションして GitHub Pages で配信するサイト。

- **要約・分類**: Azure OpenAI Responses API + GPT-5.4 mini
- **ソース**: Microsoft 公式 11ソース + OpenAI / Anthropic 公式
- **更新**: GitHub Actions 毎朝 07:00 JST 自動実行
- **コスト**: 約 ¥800 / 月（GPT-5.4 mini, ~30記事/日）

---

## 🏗 アーキテクチャ

```
GitHub Actions (cron: 22:00 UTC = 07:00 JST)
     │
     ▼
┌──────────────────────┐
│ src/fetch_feeds.py   │  RSS 13ソース取得 + 重複除外
└──────────────────────┘
     │ raw_articles.json
     ▼
┌──────────────────────┐
│ src/classify_summarize│  Azure OpenAI Responses API (5並列, リトライ4回)
│   .py                │  → category, overview, whats_new, key_takeaway, tags
└──────────────────────┘
     │ articles.json (永続)
     ▼
┌──────────────────────┐
│ src/render_site.py   │  Jinja2 で docs/index.html 生成
└──────────────────────┘
     │
     ▼
GitHub Pages (Private リポジトリ + Pages 公開)
```

---

## 📋 セットアップ手順

### 1. Azure OpenAI リソース準備

#### 1-1. リソース作成

Azure Portal → 「Azure OpenAI」を検索 → 作成
- **Region**: `East US 2` （最新機能が早い、推奨）
- **Pricing tier**: `Standard S0`
- **Resource name**: 任意（例: `daka1-ai365-eastus2`）

#### 1-2. GPT-5.4 mini デプロイ

リソース作成後、「Go to Azure AI Foundry portal」をクリック → Foundry Portal で:

1. 左メニュー → **Deployments** → **+ Deploy model**
2. Model: **gpt-5.4-mini** (Version: `2026-03-17`)
3. Deployment name: `gpt-5-4-mini` （これが `AZURE_OPENAI_DEPLOYMENT` の値になる）
4. Deployment type: **Standard**
5. Tokens per Minute Rate Limit: **30K** 以上推奨（5並列対応のため）

#### 1-3. 必要な値を取得

リソースの「Keys and Endpoint」ページから:
- **Endpoint**: `https://daka1-ai365-eastus2.openai.azure.com/`
  → 末尾に `openai/v1/` を追加して `AZURE_OPENAI_BASE_URL` にする
  → 最終形: `https://daka1-ai365-eastus2.openai.azure.com/openai/v1/`
- **KEY 1**: API キー（`AZURE_OPENAI_API_KEY`）
- **Deployment name**: 上で命名した値（`AZURE_OPENAI_DEPLOYMENT`）

> ⚠️ **重要**: `AZURE_OPENAI_BASE_URL` は必ず `/openai/v1/` で終わらせること（Responses API の仕様）

### 2. ローカル動作確認（オプション）

```bash
git clone https://github.com/YOUR-USERNAME/microsoft-ai-365.git
cd microsoft-ai-365

python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# .env を編集して 3 つの環境変数を設定

# 全パイプラインを1回実行
python -m src.run_all

# ブラウザで docs/index.html を開いて確認
```

### 3. GitHub リポジトリ作成 & Secrets 登録

#### 3-1. リポジトリ作成
- GitHub で新規リポジトリ作成（名前: `microsoft-ai-365` 推奨）
- Visibility: **Private** （※ Pages を Private で公開するには GitHub Pro / Team / Enterprise が必要）

#### 3-2. コードをプッシュ

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/microsoft-ai-365.git
git push -u origin main
```

#### 3-3. Secrets 登録

リポジトリ **Settings → Secrets and variables → Actions → New repository secret**

| Name | Value |
|---|---|
| `AZURE_OPENAI_API_KEY` | Azure OpenAI の Key 1 |
| `AZURE_OPENAI_BASE_URL` | `https://YOUR-RESOURCE.openai.azure.com/openai/v1/` |
| `AZURE_OPENAI_DEPLOYMENT` | `gpt-5-4-mini` （デプロイ名） |

### 4. GitHub Pages 有効化

リポジトリ **Settings → Pages**:
- Source: **GitHub Actions**

> ※ 古い「Deploy from a branch」ではなく、新しい「GitHub Actions」を選択。ワークフローが Pages へのデプロイまで自動で行います。

### 5. 初回実行

リポジトリ **Actions タブ** → 「Daily Update」ワークフロー → **Run workflow** ボタン

実行後、`https://YOUR-USERNAME.github.io/microsoft-ai-365/` でサイトが表示されることを確認。

以降は毎朝 07:00 JST に自動実行されます。

---

## 🛠 設定変更

すべての設定は `src/config.py` に集約されています。

### RSS ソース追加・削除

`src/config.py` の `RSS_SOURCES` を編集:
```python
{
    "name": "新ソース名",
    "url": "https://example.com/feed/",
    "domain": "example.com",
    "hint": "Microsoft Foundry",  # LLM への分類ヒント
}
```

### カテゴリ追加・変更

`MICROSOFT_CATEGORIES` または `PARTNER_CATEGORIES` に追加。
変更後は `CATEGORY_CSS` と `category_dot()`（`render_site.py`）も更新。

### 並列数・リトライ設定

```python
LLM_CONCURRENCY = 5         # 並列数（TPM に応じて調整）
LLM_MAX_ATTEMPTS = 4        # リトライ含む最大試行回数
LLM_RETRY_WAIT_MIN = 4      # 初回待機秒数
LLM_RETRY_WAIT_MAX = 60     # 最大待機秒数
```

### デザイン変更

`templates/index.html` および `templates/partials/*.html` を編集。
スタイルは `templates/assets/style.css`。
データ取得スクリプトは触らずに見た目だけ変更可能。

---

## 💰 コスト試算

GPT-5.4 mini: $0.75/M input, $4.50/M output

| 項目 | 計算 | 月額 |
|---|---|---|
| Input | 30記事 × 2,500 tokens × 30日 = 2.25M | $1.69 |
| Output | 30記事 × 800 tokens × 30日 = 720K | $3.24 |
| **合計** | | **約 $5 / 月（¥750）** |

GitHub Actions: Private リポジトリ Free プランで月 2,000分まで無料（実際の使用は月 ~150分）。

---

## 🔍 トラブルシュート

### `AZURE_OPENAI_BASE_URL must end with '/openai/v1/'`
→ Endpoint のコピペで末尾の `/openai/v1/` を忘れている。

### `404 Not Found` from Azure OpenAI
→ `AZURE_OPENAI_DEPLOYMENT` の値が Foundry Portal で作成したデプロイ名と一致していない。

### `429 Too Many Requests`
→ TPM 制限超過。Azure ポータルで Tokens per Minute Rate Limit を上げる（30K → 60K など）か、`LLM_CONCURRENCY` を下げる。

### Pages にデプロイされない
→ Settings → Pages の Source が「GitHub Actions」になっているか確認。
→ Settings → Actions → Workflow permissions が「Read and write permissions」になっているか確認。

---

## 📂 プロジェクト構造

```
microsoft-ai-365/
├── .github/workflows/daily-update.yml   # GitHub Actions
├── src/
│   ├── config.py                        # 全設定（RSS, カテゴリ, 並列数）
│   ├── prompts.py                       # JSON Schema + プロンプト
│   ├── fetch_feeds.py                   # RSS 取得
│   ├── classify_summarize.py            # Azure OpenAI 呼び出し
│   ├── render_site.py                   # Jinja2 HTML 生成
│   └── run_all.py                       # パイプライン全体
├── templates/
│   ├── index.html
│   ├── partials/                        # header, featured, story, sidebar, footer
│   └── assets/                          # style.css, app.js
├── data/
│   ├── articles.json                    # 全記事の永続データ
│   └── seen_urls.json                   # 重複検出用
├── docs/                                # GitHub Pages 公開先（自動生成）
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## 📝 ライセンス

Personal project. Use freely.

---

Curated by **@daka1** | Powered by Azure OpenAI Responses API + GitHub Actions
