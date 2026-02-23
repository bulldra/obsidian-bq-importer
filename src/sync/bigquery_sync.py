import logging
from datetime import datetime, timezone

from google.cloud import bigquery

logger = logging.getLogger(__name__)

DATASET = "obsidian_vault"
SYNC_STATE_TABLE = "sync_state"
DOCUMENTS_EXTERNAL_TABLE = "documents"


def _get_client(project: str) -> bigquery.Client:
    return bigquery.Client(project=project)


def get_last_commit_hash(project: str) -> str | None:
    """sync_stateテーブルから前回成功コミットハッシュを取得する。"""
    client = _get_client(project)
    table_ref = f"{project}.{DATASET}.{SYNC_STATE_TABLE}"

    query = f"""
    SELECT commit_hash FROM `{table_ref}`
    WHERE id = 'latest'
    LIMIT 1
    """
    try:
        rows = list(client.query(query).result())
        if rows:
            return rows[0].commit_hash
    except Exception as e:
        logger.warning("sync_state read failed (may not exist yet): %s", e)
    return None


def update_sync_state(
    project: str,
    commit_hash: str,
    files_added: int,
    files_modified: int,
    files_deleted: int,
) -> None:
    """同期状態を更新する。"""
    client = _get_client(project)
    table_ref = f"{project}.{DATASET}.{SYNC_STATE_TABLE}"
    now = datetime.now(timezone.utc).isoformat()

    query = f"""
    MERGE `{table_ref}` AS target
    USING (SELECT 'latest' AS id) AS source
    ON target.id = source.id
    WHEN MATCHED THEN
        UPDATE SET
            commit_hash = @commit_hash,
            synced_at = TIMESTAMP(@synced_at),
            files_added = @files_added,
            files_modified = @files_modified,
            files_deleted = @files_deleted
    WHEN NOT MATCHED THEN
        INSERT (id, commit_hash, synced_at, files_added, files_modified, files_deleted)
        VALUES ('latest', @commit_hash, TIMESTAMP(@synced_at),
                @files_added, @files_modified, @files_deleted)
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("commit_hash", "STRING", commit_hash),
            bigquery.ScalarQueryParameter("synced_at", "STRING", now),
            bigquery.ScalarQueryParameter("files_added", "INT64", files_added),
            bigquery.ScalarQueryParameter("files_modified", "INT64", files_modified),
            bigquery.ScalarQueryParameter("files_deleted", "INT64", files_deleted),
        ]
    )
    client.query(query, job_config=job_config).result()
    logger.info("Sync state updated: commit=%s", commit_hash[:8])


def ensure_tables_exist(
    project: str,
    gcs_bucket: str,
    gcs_blob_prefix: str,
) -> None:
    """データセット・sync_stateテーブル・外部テーブルが存在しない場合は作成する。"""
    client = _get_client(project)
    dataset_ref = f"{project}.{DATASET}"

    try:
        client.get_dataset(dataset_ref)
    except Exception:
        dataset = bigquery.Dataset(dataset_ref)
        dataset.location = "US"
        client.create_dataset(dataset, exists_ok=True)
        logger.info("Created dataset: %s", dataset_ref)

    # sync_state: ネイティブテーブル（コミットハッシュ管理）
    sync_state_ref = f"{dataset_ref}.{SYNC_STATE_TABLE}"
    sync_state_schema = [
        bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("commit_hash", "STRING"),
        bigquery.SchemaField("synced_at", "TIMESTAMP"),
        bigquery.SchemaField("files_added", "INT64"),
        bigquery.SchemaField("files_modified", "INT64"),
        bigquery.SchemaField("files_deleted", "INT64"),
    ]
    sync_state_table = bigquery.Table(sync_state_ref, schema=sync_state_schema)
    client.create_table(sync_state_table, exists_ok=True)
    logger.info("Ensured table exists: %s", sync_state_ref)

    # documents: GCS外部テーブル
    _ensure_external_table(client, dataset_ref, gcs_bucket, gcs_blob_prefix)


def _ensure_external_table(
    client: bigquery.Client,
    dataset_ref: str,
    gcs_bucket: str,
    gcs_blob_prefix: str,
) -> None:
    """GCSのJSONファイルをデータソースとする外部テーブルを作成する。"""
    table_ref = f"{dataset_ref}.{DOCUMENTS_EXTERNAL_TABLE}"

    schema = [
        bigquery.SchemaField("file_path", "STRING"),
        bigquery.SchemaField("dir_path", "STRING"),
        bigquery.SchemaField("file_name", "STRING"),
        bigquery.SchemaField("category", "STRING"),
        bigquery.SchemaField("title", "STRING"),
        bigquery.SchemaField("tags", "STRING", mode="REPEATED"),
        bigquery.SchemaField("content", "STRING"),
        bigquery.SchemaField("frontmatter", "STRING"),
    ]

    try:
        existing = client.get_table(table_ref)
        existing_fields = {f.name for f in existing.schema}
        required_fields = {f.name for f in schema}
        if required_fields.issubset(existing_fields):
            logger.info("External table already exists: %s", table_ref)
            return
        logger.info("External table schema changed, recreating: %s", table_ref)
        client.delete_table(table_ref)
    except Exception:
        pass

    source_uri = f"gs://{gcs_bucket}/{gcs_blob_prefix}*.json"

    external_config = bigquery.ExternalConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
    )
    external_config.source_uris = [source_uri]
    external_config.autodetect = False
    external_config.schema = schema

    table = bigquery.Table(table_ref, schema=schema)
    table.external_data_configuration = external_config

    client.create_table(table, exists_ok=True)
    logger.info("Created external table: %s -> %s", table_ref, source_uri)
