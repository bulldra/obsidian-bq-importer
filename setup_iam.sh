#!/usr/bin/env bash
set -e

# shellcheck disable=SC1091
source ./.env

echo "=== IAM Setup for ${FUNCTION_NAME} ==="
echo "Project: ${GCP_PROJECT}"
echo "Service Account: ${SERVICE_ACCOUNT}"

# BigQuery Data Editor (sync_state 読み書き + 外部テーブル作成)
echo "[1/4] Granting BigQuery Data Editor..."
gcloud projects add-iam-policy-binding "${GCP_PROJECT}" \
	--member="serviceAccount:${SERVICE_ACCOUNT}" \
	--role="roles/bigquery.dataEditor" \
	--condition=None --quiet > /dev/null

# BigQuery Job User (クエリ実行)
echo "[2/4] Granting BigQuery Job User..."
gcloud projects add-iam-policy-binding "${GCP_PROJECT}" \
	--member="serviceAccount:${SERVICE_ACCOUNT}" \
	--role="roles/bigquery.jobUser" \
	--condition=None --quiet > /dev/null

# GCS Object User (ドキュメント読み書き)
echo "[3/4] Granting GCS Object User..."
gcloud projects add-iam-policy-binding "${GCP_PROJECT}" \
	--member="serviceAccount:${SERVICE_ACCOUNT}" \
	--role="roles/storage.objectUser" \
	--condition=None --quiet > /dev/null

# Secret Manager Secret Accessor (シークレット読み取り)
SECRET_NAME=$(echo "${SECRETS_MANAGER}" | sed -n 's|.*/secrets/\([^/:]*\).*|\1|p')
echo "[4/4] Granting Secret Manager Accessor for '${SECRET_NAME}'..."
gcloud secrets add-iam-policy-binding "${SECRET_NAME}" \
	--member="serviceAccount:${SERVICE_ACCOUNT}" \
	--role="roles/secretmanager.secretAccessor" \
	--quiet > /dev/null

echo "=== IAM Setup Complete ==="
