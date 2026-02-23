#!/bin/bash
# ローカル Obsidian Vault から GCS へ初回アップロードするスクリプト
#
# 使い方:
#   # ドライラン（アップロードせず対象ファイルを確認）
#   bash local_upload.sh /path/to/obsidian-vault --dry-run
#
#   # 実際にアップロード
#   bash local_upload.sh /path/to/obsidian-vault
#
# 前提条件:
#   1. secrets.json が設定済み（secrets.json.sample を参照）
#   2. gcloud 認証済み: gcloud auth application-default login
#   3. uv がインストール済み

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ $# -lt 1 ]; then
    echo "Usage: bash local_upload.sh <vault_path> [--dry-run] [--batch-size N]"
    echo ""
    echo "Example:"
    echo "  bash local_upload.sh ~/obsidian-vault --dry-run"
    echo "  bash local_upload.sh ~/obsidian-vault"
    exit 1
fi

# GCP 認証確認
if ! gcloud auth application-default print-access-token > /dev/null 2>&1; then
    echo "Error: GCP credentials not found."
    echo "Run: gcloud auth application-default login"
    exit 1
fi

# secrets.json 確認
if [ ! -f "${SCRIPT_DIR}/secrets.json" ]; then
    echo "Error: secrets.json not found."
    echo "Copy secrets.json.sample to secrets.json and fill in values."
    exit 1
fi

cd "${SCRIPT_DIR}"
uv run python src/local_upload.py "$@" --secrets secrets.json
