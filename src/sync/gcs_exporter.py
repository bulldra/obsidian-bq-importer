import json
import logging

from google.cloud import storage

logger = logging.getLogger(__name__)


def _get_bucket(bucket_name: str) -> storage.Bucket:
    return storage.Client().get_bucket(bucket_name)


def upsert_documents(
    documents: list[dict],
    bucket_name: str,
    blob_prefix: str,
) -> None:
    """変更・追加されたドキュメントを個別JSONとしてGCSにアップロードする。

    GCSパス: gs://{bucket}/{prefix}{file_path}.json
    """
    if not documents:
        return
    bucket = _get_bucket(bucket_name)
    for doc in documents:
        blob_name = f"{blob_prefix}{doc['file_path']}.json"
        blob = bucket.blob(blob_name)
        payload = json.dumps(
            {
                "file_path": doc["file_path"],
                "dir_path": doc["dir_path"],
                "file_name": doc["file_name"],
                "category": doc["category"],
                "title": doc["title"],
                "tags": doc["tags"],
                "content": doc["content"],
                "frontmatter": json.dumps(
                    doc["frontmatter"], ensure_ascii=False
                ),
            },
            ensure_ascii=False,
        )
        blob.upload_from_string(payload, content_type="application/json")
    logger.info("GCS upserted %d documents", len(documents))


def delete_documents(
    deleted_paths: list[str],
    bucket_name: str,
    blob_prefix: str,
) -> None:
    """削除されたドキュメントをGCSから削除する。"""
    if not deleted_paths:
        return
    bucket = _get_bucket(bucket_name)
    for file_path in deleted_paths:
        blob_name = f"{blob_prefix}{file_path}.json"
        blob = bucket.blob(blob_name)
        if blob.exists():
            blob.delete()
    logger.info("GCS deleted %d documents", len(deleted_paths))
