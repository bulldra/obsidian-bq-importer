import json
import logging
import os

import functions_framework

from sync.bigquery_sync import (
    ensure_tables_exist,
    get_last_commit_hash,
    update_sync_state,
)
from sync.gcs_exporter import delete_documents, upsert_documents
from sync.git_diff import DiffResult, GitHubClient
from sync.markdown_parser import parse_markdown

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def _load_secrets() -> dict:
    raw = os.environ.get("SECRETS", "{}")
    return json.loads(raw)


def run_sync() -> dict:
    """メイン同期処理。Cloud Run Functions から呼び出される。

    1. BigQuery sync_state から前回コミットハッシュ取得
    2. GitHub Compare API で差分ファイル特定
    3. 変更ファイルを Markdown パース
    4. GCS 差分反映 (個別JSON upsert/delete)
    5. sync_state 更新
    ※ BigQuery は GCS 外部テーブルとして参照（DML不要）
    """
    secrets = _load_secrets()
    project = os.environ.get("GCP_PROJECT", "")
    if not project:
        raise ValueError("GCP_PROJECT environment variable is required")

    github_token = secrets.get("GITHUB_TOKEN", "")
    if not github_token:
        raise ValueError("GITHUB_TOKEN is required in SECRETS")

    github_repo = secrets.get("GITHUB_REPO", "")
    if not github_repo:
        raise ValueError("GITHUB_REPO is required in SECRETS")

    gcs_bucket = secrets.get("GCS_BUCKET", "")
    if not gcs_bucket:
        raise ValueError("GCS_BUCKET is required in SECRETS")

    gcs_blob_prefix = secrets.get("GCS_BLOB_PREFIX", "obsidian/")

    gh = GitHubClient(token=github_token, repo=github_repo)

    ensure_tables_exist(project, gcs_bucket, gcs_blob_prefix)

    current_commit = gh.get_latest_commit()
    last_commit = get_last_commit_hash(project)

    # 初回同期: 全ファイルを対象にする
    if last_commit is None:
        logger.info("Initial sync: processing all files")
        all_paths = gh.get_all_md_files(ref=current_commit)
        diff = DiffResult(added=all_paths)
    elif last_commit == current_commit:
        logger.info("No new commits since last sync")
        return {"status": "no_changes", "commit": current_commit}
    else:
        diff = gh.get_compare(last_commit, current_commit)

    if not diff.has_changes:
        logger.info("No markdown file changes detected")
        update_sync_state(project, current_commit, 0, 0, 0)
        return {"status": "no_md_changes", "commit": current_commit}

    # 変更ファイルの内容を取得してパース
    upsert_docs = []
    for file_path in diff.upsert_paths:
        content = gh.get_file_content(file_path, ref=current_commit)
        if content:
            doc = parse_markdown(file_path, content)
            upsert_docs.append(doc)

    # GCS 差分同期 (BigQuery は外部テーブルで自動反映)
    upsert_documents(upsert_docs, gcs_bucket, gcs_blob_prefix)
    delete_documents(diff.deleted, gcs_bucket, gcs_blob_prefix)

    # コミットハッシュ更新
    update_sync_state(
        project,
        current_commit,
        files_added=len(diff.added),
        files_modified=len(diff.modified),
        files_deleted=len(diff.deleted),
    )

    result = {
        "status": "synced",
        "commit": current_commit,
        "added": len(diff.added),
        "modified": len(diff.modified),
        "deleted": len(diff.deleted),
    }
    logger.info("Sync completed: %s", json.dumps(result))
    return result


@functions_framework.http
def sync_http(request) -> tuple[str, int]:
    """Cloud Run Functions エントリポイント（HTTP トリガー）"""
    try:
        result = run_sync()
        return json.dumps(result), 200
    except Exception as e:
        logger.error("Sync failed: %s", e, exc_info=True)
        return json.dumps({"error": "Internal sync error"}), 500
