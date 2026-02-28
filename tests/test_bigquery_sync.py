from unittest.mock import MagicMock, patch

import pytest
from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from sync.bigquery_sync import ensure_tables_exist, get_last_commit_hash, update_sync_state

PROJECT = "test-project"
DATASET_REF = f"{PROJECT}.obsidian_vault"
SYNC_STATE_REF = f"{DATASET_REF}.sync_state"
GCS_BUCKET = "test-bucket"
GCS_PREFIX = "obsidian/"


@pytest.fixture
def mock_client():
    with patch("sync.bigquery_sync._get_client") as mock_get:
        client = MagicMock(spec=bigquery.Client)
        mock_get.return_value = client
        yield client


class TestEnsureTablesExist:
    """ensure_tables_exist のテスト"""

    def test_dataset_exists_skip_creation(self, mock_client):
        """データセットが存在する場合は作成しない"""
        mock_client.get_dataset.return_value = MagicMock()
        mock_client.get_table.return_value = MagicMock(
            schema=[
                bigquery.SchemaField("file_path", "STRING"),
                bigquery.SchemaField("dir_path", "STRING"),
                bigquery.SchemaField("file_name", "STRING"),
                bigquery.SchemaField("category", "STRING"),
                bigquery.SchemaField("title", "STRING"),
                bigquery.SchemaField("tags", "STRING", mode="REPEATED"),
                bigquery.SchemaField("content", "STRING"),
                bigquery.SchemaField("frontmatter", "STRING"),
            ]
        )

        ensure_tables_exist(PROJECT, GCS_BUCKET, GCS_PREFIX)

        mock_client.create_dataset.assert_not_called()

    def test_dataset_not_exists_creates(self, mock_client):
        """データセットが存在しない場合は作成する"""
        mock_client.get_dataset.side_effect = NotFound("not found")
        mock_client.get_table.return_value = MagicMock(
            schema=[
                bigquery.SchemaField("file_path", "STRING"),
                bigquery.SchemaField("dir_path", "STRING"),
                bigquery.SchemaField("file_name", "STRING"),
                bigquery.SchemaField("category", "STRING"),
                bigquery.SchemaField("title", "STRING"),
                bigquery.SchemaField("tags", "STRING", mode="REPEATED"),
                bigquery.SchemaField("content", "STRING"),
                bigquery.SchemaField("frontmatter", "STRING"),
            ]
        )

        ensure_tables_exist(PROJECT, GCS_BUCKET, GCS_PREFIX)

        mock_client.create_dataset.assert_called_once()

    def test_sync_state_table_exists_skip_creation(self, mock_client):
        """sync_stateテーブルが存在する場合はcreate_tableを呼ばない"""
        mock_client.get_dataset.return_value = MagicMock()
        # get_table: 1回目=sync_state(存在), 2回目=documents(存在)
        mock_client.get_table.return_value = MagicMock(
            schema=[
                bigquery.SchemaField("file_path", "STRING"),
                bigquery.SchemaField("dir_path", "STRING"),
                bigquery.SchemaField("file_name", "STRING"),
                bigquery.SchemaField("category", "STRING"),
                bigquery.SchemaField("title", "STRING"),
                bigquery.SchemaField("tags", "STRING", mode="REPEATED"),
                bigquery.SchemaField("content", "STRING"),
                bigquery.SchemaField("frontmatter", "STRING"),
            ]
        )

        ensure_tables_exist(PROJECT, GCS_BUCKET, GCS_PREFIX)

        mock_client.create_table.assert_not_called()

    def test_sync_state_table_not_exists_creates(self, mock_client):
        """sync_stateテーブルが存在しない場合はcreate_tableを呼ぶ"""
        mock_client.get_dataset.return_value = MagicMock()

        def get_table_side_effect(ref):
            if "sync_state" in ref:
                raise NotFound("not found")
            # documents テーブルは存在するものとして返す
            return MagicMock(
                schema=[
                    bigquery.SchemaField("file_path", "STRING"),
                    bigquery.SchemaField("dir_path", "STRING"),
                    bigquery.SchemaField("file_name", "STRING"),
                    bigquery.SchemaField("category", "STRING"),
                    bigquery.SchemaField("title", "STRING"),
                    bigquery.SchemaField("tags", "STRING", mode="REPEATED"),
                    bigquery.SchemaField("content", "STRING"),
                    bigquery.SchemaField("frontmatter", "STRING"),
                ]
            )

        mock_client.get_table.side_effect = get_table_side_effect

        ensure_tables_exist(PROJECT, GCS_BUCKET, GCS_PREFIX)

        mock_client.create_table.assert_called_once()
        created_table = mock_client.create_table.call_args[0][0]
        assert isinstance(created_table, bigquery.Table)
        assert SYNC_STATE_REF in str(created_table)

    def test_sync_state_no_exists_ok_flag(self, mock_client):
        """create_tableにexists_ok=Trueが渡されていないことを確認"""
        mock_client.get_dataset.return_value = MagicMock()

        def get_table_side_effect(ref):
            if "sync_state" in ref:
                raise NotFound("not found")
            return MagicMock(
                schema=[
                    bigquery.SchemaField("file_path", "STRING"),
                    bigquery.SchemaField("dir_path", "STRING"),
                    bigquery.SchemaField("file_name", "STRING"),
                    bigquery.SchemaField("category", "STRING"),
                    bigquery.SchemaField("title", "STRING"),
                    bigquery.SchemaField("tags", "STRING", mode="REPEATED"),
                    bigquery.SchemaField("content", "STRING"),
                    bigquery.SchemaField("frontmatter", "STRING"),
                ]
            )

        mock_client.get_table.side_effect = get_table_side_effect

        ensure_tables_exist(PROJECT, GCS_BUCKET, GCS_PREFIX)

        # exists_ok が渡されていない（= API レベルの ALREADY_EXISTS エラー回避）
        call_kwargs = mock_client.create_table.call_args
        if call_kwargs.kwargs:
            assert "exists_ok" not in call_kwargs.kwargs or not call_kwargs.kwargs.get("exists_ok")


class TestGetLastCommitHash:
    """get_last_commit_hash のテスト"""

    def test_returns_hash_when_exists(self, mock_client):
        row = MagicMock()
        row.commit_hash = "abc123def456"
        mock_query_job = MagicMock()
        mock_query_job.result.return_value = [row]
        mock_client.query.return_value = mock_query_job

        result = get_last_commit_hash(PROJECT)

        assert result == "abc123def456"

    def test_returns_none_when_empty(self, mock_client):
        mock_query_job = MagicMock()
        mock_query_job.result.return_value = []
        mock_client.query.return_value = mock_query_job

        result = get_last_commit_hash(PROJECT)

        assert result is None

    def test_returns_none_on_error(self, mock_client):
        mock_client.query.side_effect = Exception("table not found")

        result = get_last_commit_hash(PROJECT)

        assert result is None


class TestUpdateSyncState:
    """update_sync_state のテスト"""

    def test_executes_merge_query(self, mock_client):
        mock_query_job = MagicMock()
        mock_query_job.result.return_value = None
        mock_client.query.return_value = mock_query_job

        update_sync_state(PROJECT, "abc123", 10, 5, 2)

        mock_client.query.assert_called_once()
        query = mock_client.query.call_args[0][0]
        assert "MERGE" in query
        assert SYNC_STATE_REF in query
