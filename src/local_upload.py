"""ローカル Obsidian Vault から GCS へ初回一括アップロードするスクリプト。

Usage:
    python src/local_upload.py /path/to/obsidian-vault

    # ドライラン（アップロードせずファイル一覧を確認）
    python src/local_upload.py /path/to/obsidian-vault --dry-run

    # secrets.json のパスを指定
    python src/local_upload.py /path/to/obsidian-vault --secrets secrets.json

環境変数または secrets.json で以下を設定:
    GCS_BUCKET: GCS バケット名
    GCS_BLOB_PREFIX: GCS プレフィックス（デフォルト: obsidian/）
    GCP_PROJECT: GCP プロジェクトID（sync_state 更新時に使用）
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sync.bigquery_sync import ensure_tables_exist, update_sync_state
from sync.gcs_exporter import upsert_documents
from sync.git_diff import GitHubClient
from sync.markdown_parser import parse_markdown

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# アップロード対象外のディレクトリ
EXCLUDE_DIRS = {
    ".obsidian",
    ".trash",
    ".git",
    ".github",
    "__pycache__",
    "node_modules",
}


def collect_md_files(vault_path: Path) -> list[Path]:
    """Vault 内の全 .md ファイルを収集する（除外ディレクトリをスキップ）。"""
    md_files = []
    for path in vault_path.rglob("*.md"):
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        md_files.append(path)
    md_files.sort()
    return md_files


def build_documents(vault_path: Path, md_files: list[Path]) -> list[dict]:
    """ファイルリストを読み込み、パース済みドキュメントのリストを返す。"""
    documents = []
    errors = []
    for md_path in md_files:
        relative = str(md_path.relative_to(vault_path))
        try:
            content = md_path.read_text(encoding="utf-8")
            doc = parse_markdown(relative, content)
            documents.append(doc)
        except Exception as e:
            errors.append((relative, str(e)))
            logger.warning("Skip %s: %s", relative, e)

    if errors:
        logger.warning("Skipped %d files due to errors", len(errors))
    return documents


def load_secrets(secrets_path: str | None) -> dict:
    """secrets.json を読み込む。"""
    if secrets_path:
        path = Path(secrets_path)
        if path.exists():
            return json.loads(path.read_text())
        logger.warning("Secrets file not found: %s", secrets_path)
    return {}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ローカル Obsidian Vault から GCS へ一括アップロード"
    )
    parser.add_argument("vault_path", help="Obsidian Vault のルートディレクトリ")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="アップロードせずに対象ファイル一覧を表示",
    )
    parser.add_argument(
        "--secrets",
        default="secrets.json",
        help="secrets.json のパス（デフォルト: secrets.json）",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="一度にアップロードするファイル数（デフォルト: 100）",
    )
    args = parser.parse_args()

    vault_path = Path(args.vault_path).resolve()
    if not vault_path.is_dir():
        logger.error("Vault path does not exist: %s", vault_path)
        sys.exit(1)

    secrets = load_secrets(args.secrets)
    gcs_bucket = secrets.get("GCS_BUCKET", "")
    gcs_blob_prefix = secrets.get("GCS_BLOB_PREFIX", "obsidian/")

    github_token = secrets.get("GITHUB_TOKEN", "")
    github_repo = secrets.get("GITHUB_REPO", "")
    gcp_project = secrets.get("GCP_PROJECT", "")

    if not args.dry_run and not gcs_bucket:
        logger.error("GCS_BUCKET is required in secrets.json")
        sys.exit(1)

    # ファイル収集
    logger.info("Scanning vault: %s", vault_path)
    md_files = collect_md_files(vault_path)
    logger.info("Found %d markdown files", len(md_files))

    if not md_files:
        logger.info("No markdown files found")
        return

    # パース
    logger.info("Parsing markdown files...")
    documents = build_documents(vault_path, md_files)
    logger.info("Parsed %d documents successfully", len(documents))

    # ドライラン
    if args.dry_run:
        print(f"\n--- Dry Run: {len(documents)} files to upload ---")
        for doc in documents:
            tags = ", ".join(doc["tags"]) if doc["tags"] else "(no tags)"
            print(f"  {doc['file_path']}  [{tags}]")
        print(f"\nTotal: {len(documents)} files")
        return

    # バッチアップロード
    batch_size = args.batch_size
    total = len(documents)
    uploaded = 0

    for i in range(0, total, batch_size):
        batch = documents[i : i + batch_size]
        upsert_documents(batch, gcs_bucket, gcs_blob_prefix)
        uploaded += len(batch)
        logger.info("Progress: %d / %d uploaded", uploaded, total)

    logger.info("Upload completed: %d documents to gs://%s/%s", total, gcs_bucket, gcs_blob_prefix)

    # sync_state 更新（GitHub の最新コミットを記録し、次回から差分同期可能にする）
    if not github_token or not github_repo or not gcp_project:
        logger.warning(
            "Skipped sync_state update: GITHUB_TOKEN, GITHUB_REPO, GCP_PROJECT are all required in secrets.json"
        )
        return

    gh = GitHubClient(token=github_token, repo=github_repo)
    current_commit = gh.get_latest_commit()
    ensure_tables_exist(gcp_project, gcs_bucket, gcs_blob_prefix)
    update_sync_state(gcp_project, current_commit, files_added=total, files_modified=0, files_deleted=0)
    logger.info("sync_state updated: commit=%s (files_added=%d)", current_commit[:8], total)


if __name__ == "__main__":
    main()
