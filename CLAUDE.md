# Obsidian GitHub GCS Export

## プロジェクト概要

Obsidian Vault の Markdown ファイルを GitHub → GCS → BigQuery へ差分同期するパイプライン。

## 技術スタック

- Python 3.12 / uv
- Google Cloud Run Functions (gen2)
- GCS (`bulldra-api-storage`)
- BigQuery (`obsidian_vault` データセット)
- GitHub Actions (cron ETL)

## ディレクトリ構成

- `src/main.py` - Cloud Run Functions エントリポイント
- `src/sync/` - 同期コアロジック
- `src/utils/` - 共通ユーティリティ
- `docs/plan.md` - 設計書
- `docs/todo.md` - タスク管理

## デプロイ

```bash
uv pip compile pyproject.toml -o src/requirements.txt
bash deploy.sh
```

## 参考実装

- `../slack-sub-bot` - GCSキャッシュパターン、Cloud Run Functions デプロイ
