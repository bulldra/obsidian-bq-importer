#!/usr/bin/env bash
set -e

# shellcheck disable=SC1091
source ./.env

uv pip compile pyproject.toml -o src/requirements.txt

# Update Secret Manager only if secrets.json differs from current version
# Extract secret name from path like "projects/xxx/secrets/NAME/versions/latest"
SECRET_NAME=$(echo "${SECRETS_MANAGER}" | sed -n 's|.*/secrets/\([^/:]*\).*|\1|p')
if [ -f secrets.json ]; then
	if ! gcloud secrets describe "${SECRET_NAME}" > /dev/null 2>&1; then
		echo "Secret '${SECRET_NAME}' does not exist. Creating..."
		gcloud secrets create "${SECRET_NAME}" --data-file=secrets.json
	else
		REMOTE_SECRET=$(gcloud secrets versions access latest --secret="${SECRET_NAME}" 2>/dev/null || echo "")
		LOCAL_SECRET=$(cat secrets.json)
		if [ "${REMOTE_SECRET}" != "${LOCAL_SECRET}" ]; then
			echo "Secret '${SECRET_NAME}' has changed. Uploading new version..."
			gcloud secrets versions add "${SECRET_NAME}" --data-file=secrets.json
		else
			echo "Secret '${SECRET_NAME}' is up to date. Skipping upload."
		fi
	fi
fi

DEPLOY_OUTPUT=$(gcloud -q functions deploy "${FUNCTION_NAME}" \
	--gen2 \
	--region=asia-northeast1 \
	--runtime=python312 \
	--trigger-http \
	--no-allow-unauthenticated \
	--timeout=540s \
	--min-instances=0 \
	--max-instances=5 \
	--memory=512Mi \
	--source=src/ \
	--entry-point=sync_http \
	--service-account "${SERVICE_ACCOUNT}" \
	--set-env-vars GCP_PROJECT="${GCP_PROJECT}" \
	--set-secrets SECRETS="${SECRETS_MANAGER}" 2>&1)

if [ $? -eq 0 ]; then
	echo "Function deployment succeeded."
else
	ERROR_MESSAGE=$(echo "$DEPLOY_OUTPUT" | head -n 1)
	osascript -e "display notification \"Deployment failed: ${ERROR_MESSAGE}\" with title \"Visual Studio Code\" subtitle \"Cloud Function ${FUNCTION_NAME} deployment.\" sound name \"Basso\""
	echo "Deployment failed for ${FUNCTION_NAME}."
	echo "Error: ${ERROR_MESSAGE}"
	exit 1
fi

# Cloud Scheduler (6時間ごと、HTTP トリガー)
FUNCTION_URL=$(gcloud functions describe "${FUNCTION_NAME}" \
	--region=asia-northeast1 --gen2 --format='value(serviceConfig.uri)')
SCHEDULER_JOB="${FUNCTION_NAME}-schedule"

if gcloud scheduler jobs describe "${SCHEDULER_JOB}" --location=asia-northeast1 > /dev/null 2>&1; then
	gcloud -q scheduler jobs update http "${SCHEDULER_JOB}" \
		--location=asia-northeast1 \
		--schedule="0 */6 * * *" \
		--uri="${FUNCTION_URL}" \
		--http-method=POST \
		--oidc-service-account-email="${SERVICE_ACCOUNT}" \
		--time-zone="Asia/Tokyo"
	echo "Scheduler job updated: ${SCHEDULER_JOB}"
else
	gcloud -q scheduler jobs create http "${SCHEDULER_JOB}" \
		--location=asia-northeast1 \
		--schedule="0 */6 * * *" \
		--uri="${FUNCTION_URL}" \
		--http-method=POST \
		--oidc-service-account-email="${SERVICE_ACCOUNT}" \
		--time-zone="Asia/Tokyo"
	echo "Scheduler job created: ${SCHEDULER_JOB}"
fi

osascript -e "display notification \"Deployment succeeded.\" with title \"Visual Studio Code\" subtitle \"Cloud Function ${FUNCTION_NAME} deployment.\" sound name \"Bell\""
date
