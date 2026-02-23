# タスク管理

## Phase 1: プロジェクト基盤

- [x] pyproject.toml 作成（uv依存管理、slack-sub-bot パターン準拠）
- [x] CLAUDE.md 作成（プロジェクト固有指示）
- [x] ディレクトリ構成作成（src/sync/, src/utils/）

## Phase 2: コア実装

- [x] markdown_parser.py - Frontmatter/本文分離パーサー
- [x] git_diff.py - Git差分抽出モジュール
- [x] bigquery_sync.py - BigQuery MERGE同期
- [x] gcs_exporter.py - GCS JSONL エクスポート
- [x] stored_gcs.py - GCSキャッシュユーティリティ（slack-sub-bot互換）
- [x] main.py - Cloud Run Functions エントリポイント

## Phase 3: CI/CD

- [x] .github/workflows/sync.yml - GitHub Actions ワークフロー
- [x] deploy.sh - Cloud Run Functions デプロイスクリプト
- [x] Dockerfile - コンテナビルド定義

## Phase 4: 初回ローカルアップロード

- [x] local_upload.py - ローカル Vault → GCS 一括アップロードスクリプト
- [x] local_upload.sh - 実行用シェルラッパー
- [ ] GCPプロジェクト設定（WIF, サービスアカウント, Secrets）
- [x] secrets.json 設定・動作確認
- [x] 実環境での初回アップロードテスト（2363件完了）
