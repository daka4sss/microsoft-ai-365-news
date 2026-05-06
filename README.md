# Microsoft AI 365 — Daily Tech Curation

Microsoft AI / Azure / Copilot / Foundry / Agent / Security に関する公式ブログを毎日キュレーションして GitHub Pages で配信するサイト。

- **要約・分類**: Azure OpenAI Responses API + GPT-5.4 mini
- **ソース**: Microsoft 公式 11ソース + OpenAI / Anthropic 公式
- **更新**: GitHub Actions 毎朝 07:00 JST 自動実行
- **認証**: Entra ID キーレス認証（OIDC / DefaultAzureCredential）
- **コスト**: 約 ¥800 / 月（GPT-5.4 mini, ~30記事/日）

---

## 🏗 アーキテクチャ

```
GitHub Actions (cron: 22:00 UTC = 07:00 JST)
     │  azure/login@v2 (OIDC)
     ▼
┌──────────────────────┐
│ src/fetch_feeds.py   │  RSS 13ソース取得 + 重複除外
└──────────────────────┘
     │ raw_articles.json
     ▼
┌──────────────────────┐
│ src/classify_summarize│  Azure OpenAI Responses API (5並列, リトライ4回)
│   .py                │  DefaultAzureCredential で Entra ID 認証
│                      │  → category, overview, whats_new, key_takeaway, tags
└──────────────────────┘
     │ articles.json (永続)
     ▼
┌──────────────────────┐
│ src/render_site.py   │  Jinja2 で docs/index.html 生成
└──────────────────────┘
     │
     ▼
GitHub Pages
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

リソース作成後、「Go to Azure AI Foundry portal」→ Deployments → **+ Deploy model**
1. Model: **gpt-5.4-mini** (Version: `2026-03-17`)
2. Deployment name: `gpt-5-4-mini`（これが `AZURE_OPENAI_DEPLOYMENT` の値）
3. Deployment type: **Standard**
4. Tokens per Minute Rate Limit: **30K** 以上推奨

#### 1-3. エンドポイントを確認

リソースの「Keys and Endpoint」ページから **Endpoint** をコピー:
```
https://daka1-ai365-eastus2.openai.azure.com/
```
末尾に `openai/v1/` を追加したものが `AZURE_OPENAI_BASE_URL`:
```
https://daka1-ai365-eastus2.openai.azure.com/openai/v1/
```

> ⚠️ **重要**: `AZURE_OPENAI_BASE_URL` は必ず `/openai/v1/` で終わらせること（Responses API の仕様）  
> API キーは**使用しません**。Entra ID 認証のため不要です。

---

### 2. Entra ID 認証セットアップ

#### 2-1. サービスプリンシパル作成

```bash
az login
az account list --output table
az account set --subscription "<SUB_ID>"

# SP 作成（ロールなし）
az ad sp create-for-rbac --display-name "ms-ai-365-news-sp"
```

出力の `appId` / `password` / `tenant` をメモ（`password` はこの1回のみ表示）。

#### 2-2. RBAC ロール付与

```bash
az role assignment create \
  --role "Cognitive Services OpenAI User" \
  --assignee "<appId>" \
  --scope "/subscriptions/<SUB_ID>/resourceGroups/<RG>"
```

> ロール反映まで最大5分かかります。

#### 2-3. OIDC Federated Credential 設定（GitHub Actions 用）

Azure Portal → Microsoft Entra ID → **App registrations** → `ms-ai-365-news-sp` → **Certificates & secrets** → **Federated credentials** → **Add credential**:

| 項目 | 値 |
|---|---|
| Federated credential scenario | **GitHub Actions deploying Azure resources** |
| Organization | `YOUR-GITHUB-USERNAME` |
| Repository | `microsoft-ai-365-news` |
| Entity type | **Branch** |
| Branch | `main` |
| Name | `ms-ai-365-github-oidc` |

---

### 3. GitHub リポジトリ作成 & Secrets 登録

#### 3-1. リポジトリ作成・コードプッシュ

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/microsoft-ai-365-news.git
git push -u origin main
```

#### 3-2. Secrets 登録

**Settings → Secrets and variables → Actions → New repository secret**

| Name | Value |
|---|---|
| `AZURE_CLIENT_ID` | SP の `appId` |
| `AZURE_TENANT_ID` | SP の `tenant` |
| `AZURE_SUBSCRIPTION_ID` | Azure サブスクリプション ID |
| `AZURE_OPENAI_BASE_URL` | `https://YOUR-RESOURCE.openai.azure.com/openai/v1/` |
| `AZURE_OPENAI_DEPLOYMENT` | `gpt-5-4-mini` |

> `AZURE_CLIENT_SECRET` は**不要**です（OIDC のためシークレットなし）。

---

### 4. GitHub Pages 有効化

**Settings → Pages → Source: GitHub Actions**

> 古い「Deploy from a branch」ではなく「GitHub Actions」を選択。

---

### 5. ローカル動作確認

```bash
git clone https://github.com/YOUR-USERNAME/microsoft-ai-365-news.git
cd microsoft-ai-365-news

python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # macOS/Linux

pip install -r requirements.txt

# Entra ID: az login 済みなら API キー不要
az login

cp .env.example .env
# AZURE_OPENAI_BASE_URL と AZURE_OPENAI_DEPLOYMENT を設定（APIキーは不要）

python -m src.run_all
# → docs/index.html をブラウザで確認
```

---

### 6. 初回実行

**Actions タブ** → 「Daily Update」→ **Run workflow**

`https://YOUR-USERNAME.github.io/microsoft-ai-365-news/` でサイトが表示されることを確認。以降は毎朝 07:00 JST に自動実行。

---

## 🛠 設定変更

すべての設定は `src/config.py` に集約されています。

### RSS ソース追加・削除

`RSS_SOURCES` リストを編集:
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
スタイルは `templates/assets/style.css`。`docs/` は自動生成のため直接編集しないこと。

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

### `401 Principal does not have access`
→ `Cognitive Services OpenAI User` ロールが未付与、またはロール反映待ち（最大5分）。  
→ `Owner` / `Contributor` では推論アクセスは付与されない。

### `DefaultAzureCredentialError`（ローカル）
→ `az login` が必要。`az account show` でログイン状態を確認。

### `404 Not Found` from Azure OpenAI
→ `AZURE_OPENAI_DEPLOYMENT` の値が Foundry Portal で作成したデプロイ名と一致していない。

### `429 Too Many Requests`
→ TPM 制限超過。Azure ポータルで Rate Limit を上げる（30K → 60K）か `LLM_CONCURRENCY` を下げる。

### OIDC 認証失敗（GitHub Actions）
→ Federated Credential の Organization / Repository / Branch が正確に一致しているか確認。

### Pages にデプロイされない
→ Settings → Pages の Source が「GitHub Actions」になっているか確認。  
→ Settings → Actions → Workflow permissions が「Read and write permissions」になっているか確認。

---

## 📂 プロジェクト構造

```
microsoft-ai-365-news/
├── .github/workflows/daily-update.yml   # GitHub Actions（OIDC 認証）
├── src/
│   ├── config.py                        # 全設定（RSS, カテゴリ, 並列数）
│   ├── prompts.py                       # JSON Schema + プロンプト
│   ├── fetch_feeds.py                   # RSS 取得
│   ├── classify_summarize.py            # Azure OpenAI 呼び出し（Entra ID 認証）
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

Curated by **@daka1** | Powered by Azure OpenAI Responses API + GitHub Actions + Entra ID
