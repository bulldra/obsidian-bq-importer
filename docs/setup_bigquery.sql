-- BigQuery セットアップ
-- ※ Python側の ensure_tables_exist() でも自動作成されるが、手動確認用

CREATE SCHEMA IF NOT EXISTS `obsidian_vault`;

-- 同期状態管理（ネイティブテーブル）
CREATE TABLE IF NOT EXISTS `obsidian_vault.sync_state` (
  id STRING NOT NULL,
  commit_hash STRING,
  synced_at TIMESTAMP,
  files_added INT64,
  files_modified INT64,
  files_deleted INT64
);

-- ドキュメント（GCS外部テーブル）
-- GCS上の個別JSONファイルをデータソースとして参照
CREATE OR REPLACE EXTERNAL TABLE `obsidian_vault.documents` (
  file_path STRING,
  title STRING,
  tags ARRAY<STRING>,
  content STRING,
  frontmatter STRING
)
OPTIONS (
  format = 'JSON',
  uris = ['gs://${GCS_BUCKET}/${GCS_BLOB_PREFIX}*.json']
);

-- 全文検索インデックス（外部テーブルでは不可、必要時はマテビュー経由）
-- CREATE SEARCH INDEX IF NOT EXISTS idx_documents_content
-- ON `obsidian_vault.documents`(content);
