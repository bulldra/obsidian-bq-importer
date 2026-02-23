# Obsidian GitHub GCS Export - 設計書

## 概要

Obsidian Vault の Markdown ファイルを GitHub → GCS → BigQuery へ差分同期するパイプライン。
GitHub Actions をETLハブとし、BigQuery の DML コストと処理負荷を最小化する。

## アーキテクチャ

```
Obsidian ──(plugin)──> GitHub ──(Actions cron)──> GCS + BigQuery
                                                      ↑
                                                  差分sync
```

### 実行フロー

1. GitHub Actions スケジュール実行（1日1回）
2. BigQuery 管理テーブルから前回成功コミットハッシュを取得
3. `git diff --name-status <前回ハッシュ> HEAD` で差分ファイル特定
4. 変更ファイルの Markdown をパース（Frontmatter + Content 分離）
5. GCS へ JSON 形式でアップロード
6. BigQuery へ MERGE 文で UPSERT
7. 成功時にコミットハッシュを更新

## データモデル

### BigQuery テーブル: `obsidian_vault.documents`

| カラム | 型 | 説明 |
|--------|------|------|
| file_path | STRING | 主キー（リポジトリ内の相対パス） |
| frontmatter | JSON | YAML Frontmatter を JSON 変換 |
| content | STRING | 本文（Frontmatter 除去済み） |
| title | STRING | Frontmatter の title またはファイル名 |
| tags | ARRAY<STRING> | Frontmatter の tags |
| updated_at | TIMESTAMP | 最終更新日時 |
| is_deleted | BOOL | 論理削除フラグ |

### BigQuery テーブル: `obsidian_vault.sync_state`

| カラム | 型 | 説明 |
|--------|------|------|
| id | STRING | 固定値 "latest" |
| commit_hash | STRING | 前回成功コミットハッシュ |
| synced_at | TIMESTAMP | 同期日時 |
| files_added | INT64 | 追加ファイル数 |
| files_modified | INT64 | 変更ファイル数 |
| files_deleted | INT64 | 削除ファイル数 |

### GCS バケット構造

```
gs://bulldra-api-storage/obsidian/
  documents.json          # 全ドキュメントのJSONL（Slack検索用キャッシュ）
```

## プロジェクト構成

```
obsidian-github-gcs-export/
├── src/
│   ├── main.py                    # Cloud Run Functions エントリポイント
│   ├── requirements.txt           # pip 用（デプロイ時 uv compile で生成）
│   ├── sync/
│   │   ├── __init__.py
│   │   ├── git_diff.py            # Git差分抽出
│   │   ├── markdown_parser.py     # Markdown パース（Frontmatter分離）
│   │   ├── gcs_exporter.py        # GCS アップロード
│   │   └── bigquery_sync.py       # BigQuery MERGE
│   └── utils/
│       ├── __init__.py
│       └── stored_gcs.py          # GCSキャッシュ（slack-sub-bot互換）
├── .github/
│   └── workflows/
│       └── sync.yml               # GitHub Actions ワークフロー
├── deploy.sh                      # Cloud Run Functions デプロイ
├── Dockerfile                     # コンテナデプロイ用
├── pyproject.toml                 # uv 依存管理
├── docs/
│   ├── plan.md                    # 設計書（本文書）
│   └── todo.md                    # タスク管理
└── CLAUDE.md                      # プロジェクト固有指示
```

## 技術スタック

- **ランタイム**: Python 3.12
- **依存管理**: uv
- **デプロイ**: Google Cloud Run Functions (gen2)
- **トリガー**: GitHub Actions cron → HTTP呼び出し / 直接実行
- **ストレージ**: GCS (`bulldra-api-storage`)
- **DB**: BigQuery (`obsidian_vault` データセット)
- **フレームワーク**: functions-framework

## 主要コンポーネント設計

### 1. GitHub Actions ワークフロー (`sync.yml`)

```yaml
# 1日1回実行 + 手動実行対応
on:
  schedule:
    - cron: '0 0 * * *'  # UTC 00:00 = JST 09:00
  workflow_dispatch:
```

- リポジトリを full checkout（差分取得のため）
- Python + uv セットアップ
- GCP認証（Workload Identity Federation）
- sync スクリプト実行

### 2. Git差分抽出 (`git_diff.py`)

```python
def get_changed_files(last_commit: str, current_commit: str) -> dict:
    """git diff --name-status で差分ファイルを分類"""
    # Returns: {"added": [...], "modified": [...], "deleted": [...]}
```

- `.md` ファイルのみフィルタ
- リネーム（R）は削除+追加として処理

### 3. Markdownパーサー (`markdown_parser.py`)

```python
def parse_markdown(file_path: str, content: str) -> dict:
    """Frontmatter と本文を分離してパース"""
    # Returns: {"file_path": ..., "frontmatter": {...}, "content": ...,
    #           "title": ..., "tags": [...], "updated_at": ...}
```

- `python-frontmatter` ライブラリ使用
- YAML Frontmatter → JSON 変換
- title: Frontmatter > H1 > ファイル名 の優先順位

### 4. GCSエクスポータ (`gcs_exporter.py`)

```python
def export_to_gcs(documents: list[dict], bucket_name: str) -> None:
    """ドキュメントをGCSにJSONLとしてアップロード"""
```

- slack-sub-bot の `StoredGcs` パターンを踏襲
- Slack 側は GCS から読み取り（キャッシュ TTL 付き）

### 5. BigQuery同期 (`bigquery_sync.py`)

```python
def sync_to_bigquery(documents: list[dict], deleted_paths: list[str]) -> None:
    """MERGE文でUPSERT + 論理削除"""
```

- 一時テーブルにデータロード → MERGE で本テーブルに反映
- 削除ファイルは `is_deleted = TRUE` に更新
- 同期成功後に `sync_state` テーブルを更新

### 6. Cloud Run Functions エントリポイント (`main.py`)

```python
@functions_framework.cloud_event
def main(cloud_event):
    """Pub/Sub or HTTP トリガーで同期実行"""
```

- GitHub Actions から直接実行するため HTTP トリガーも対応
- エラー時はロギングしてステータス返却

## Slack連携（slack-sub-bot側の変更）

`AgentXPost` パターンを参考に、Slack bot 側で GCS から Obsidian ドキュメントを取得：

```python
# slack-sub-bot/src/agent/agent_obsidian.py (将来)
gcs = StoredGcs("bulldra-api-storage", "obsidian/documents.json", ttl=timedelta(hours=24))
documents = json.loads(gcs.download_as_string())
```

## 初回同期

初回は `sync_state` が空のため、全ファイルを対象にフルスキャンを実行する。
`git log --reverse --format=%H | head -1` で初回コミットハッシュを取得し、全差分を処理する。

## セキュリティ

- GitHub Token: GitHub Actions の `GITHUB_TOKEN` を使用
- GCP認証: Workload Identity Federation（キーレス）
- BigQuery: サービスアカウントに最小権限付与
- Secrets: GitHub Actions Secrets で管理
