# Microsoft AI 365 — Daily Tech Curation

Microsoft AI / Azure / Copilot / Foundry / Agent / Security に関する公式ブログを毎日キュレーションして GitHub Pages で配信するサイト。

- **要約・分類**: Azure OpenAI Responses API + GPT-5.4 mini
- **ソース**: Microsoft 公式 13ソース + OpenAI 公式（Anthropic はカテゴリ枠のみ）
- **更新**: GitHub Actions 毎朝 07:00 JST + 3時間ごと差分取得 + 外部 webhook (`repository_dispatch`) 対応
- **認証**: Entra ID キーレス認証（OIDC / DefaultAzureCredential）
- **コスト**: 約 ¥800 / 月（GPT-5.4 mini, ~30記事/日）

---

## 🏗 アーキテクチャ

```
GitHub Actions
  ├─ daily-update.yml: 22:00 UTC (07:00 JST) + 3時間ごと差分 + repository_dispatch
  └─ manual-update.yml: 手動で日付範囲を指定したバックフィル
     │  azure/login@v3 (OIDC)
     ▼
┌──────────────────────┐
│ src/fetch_feeds.py   │  RSS 14ソース取得 + 重複除外（通常フロー）
│ src/fetch_range.py   │  日付範囲指定バックフィル（手動フロー）
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

### データファイルの役割

| File | Purpose | 永続化 |
|---|---|---|
| `data/raw_articles.json` | RSS から取得した新着・手動範囲指定の記事を、LLM 処理前に一時保存 | gitignore（毎回上書き） |
| `data/articles.json` | LLM 分類・要約に成功した記事の永続データ。サイト生成の source of truth | コミット |
| `data/seen_urls.json` | LLM 分類・要約に成功済みの URL 一覧。次回以降の重複除外に使用 | コミット |

`seen_urls.json` は RSS 取得直後には更新せず、`classify_summarize.py` で成功した記事だけを反映します。LLM 認証エラーや一部記事の処理失敗が起きても、失敗 URL は次回以降の再処理候補として残ります。

### RSS ソース一覧（`src/config.py` の `RSS_SOURCES`）

| 区分 | ソース | ヒント |
|---|---|---|
| Microsoft | Microsoft Source (News) | Microsoft Overview |
| Microsoft | Official Microsoft Blog | Microsoft Overview |
| Microsoft | Microsoft AI Blog | Microsoft Foundry |
| Microsoft | Azure Blog | Microsoft Foundry |
| Microsoft | Microsoft 365 Blog | M365 Copilot |
| Microsoft | M365 Dev Blog | M365 Copilot |
| Microsoft | Power Platform Blog | Copilot Studio |
| Microsoft | Microsoft Fabric Blog | Data & Fabric |
| Microsoft | Microsoft Security Blog | AI Security |
| Microsoft | GitHub Blog | Dev Tools |
| Microsoft | Tech Community — Microsoft Foundry | Microsoft Foundry |
| Microsoft | Tech Community — Azure Integration Services | Azure Integration Services |
| Microsoft | Microsoft Foundry Dev Blog | Microsoft Foundry |
| Partner | OpenAI News | OpenAI |

> Anthropic は分類カテゴリとして用意されていますが、現在 RSS フィードは登録していません。サイトの Anthropic ゾーンは記事がある時のみ表示されます。

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

# .env を作成（APIキーは不要、以下2つだけ）
cat > .env <<'EOF'
AZURE_OPENAI_BASE_URL=https://YOUR-RESOURCE.openai.azure.com/openai/v1/
AZURE_OPENAI_DEPLOYMENT=gpt-5-4-mini
EOF

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

### フロントページ・アーカイブの保持期間

```python
DAYS_ON_FRONTPAGE = 30        # フロントページに表示する直近日数（記事ゼロなら3日にフォールバック）
ARCHIVE_RETENTION_DAYS = 90   # articles.json の保持期間（これより古い記事は render 時に剪定）
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

### LLM 処理が途中で失敗した記事を再処理したい
→ `data/raw_articles.json` が残っている場合は `python -m src.classify_summarize` を再実行する。  
→ `seen_urls.json` は成功済み URL のみ進むため、失敗した URL は通常の次回取得または Manual Range Update で再処理できる。

### 特定日付の記事を遡って取得・再処理したい
→ 範囲は `[START_DATE, END_DATE]` の両端を含む。  
→ ローカル: `START_DATE=2026-04-01 END_DATE=2026-04-30 python -m src.fetch_range` → `python -m src.classify_summarize` → `python -m src.render_site`  
→ GitHub Actions: Actions タブ → 「Manual Range Update」→ Run workflow で `start_date` / `end_date` を入力。

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
├── .github/workflows/
│   ├── daily-update.yml                 # メイン自動更新（07:00 JST + 3h差分 + repository_dispatch）
│   ├── manual-update.yml                # 手動バックフィル（日付範囲指定）
│   └── main.yml                         # Azure OIDC ログイン確認用
├── src/
│   ├── config.py                        # 全設定（RSS 14ソース, 11カテゴリ, 並列数, 保持期間）
│   ├── prompts.py                       # JSON Schema + プロンプト
│   ├── fetch_feeds.py                   # RSS 取得（通常フロー）
│   ├── fetch_range.py                   # 日付範囲指定バックフィル（両端含む）
│   ├── classify_summarize.py            # Azure OpenAI 呼び出し（Entra ID 認証）
│   ├── render_site.py                   # Jinja2 HTML 生成
│   └── run_all.py                       # パイプライン全体
├── templates/
│   ├── index.html
│   ├── partials/                        # header, featured, story, sidebar, footer
│   └── assets/                          # style.css, app.js（テーマ切替・カテゴリフィルタ・既読管理）
├── data/
│   ├── articles.json                    # 全記事の永続データ
│   └── seen_urls.json                   # 重複検出用
├── docs/                                # GitHub Pages 公開先（自動生成・直接編集禁止）
├── requirements.txt
├── .gitignore
└── README.md
```

---

## 📝 ライセンス

Personal project. Use freely.

---

Curated by **@daka1** | Powered by Azure OpenAI Responses API + GitHub Actions + Entra ID
