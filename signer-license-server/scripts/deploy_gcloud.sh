#!/bin/bash
#
# deploy_gcloud.sh
#
# Идемпотентный скрипт для деплоя Signer License Server на Google Cloud Platform.
#

set -e

PROJECT_ID="${PROJECT_ID:-}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="signer-license-server"
DB_INSTANCE_NAME="signer-license-db"
DB_NAME="signer_license"
DB_USER="signer_app"
ARTIFACT_REPO="signer-repo"

if [ -z "$PROJECT_ID" ]; then
    echo "❌ ERROR: PROJECT_ID not set"
    exit 1
fi

echo "════════════════════════════════════════════════════════"
echo " Signer License Server - GCP Deployment"
echo "════════════════════════════════════════════════════════"

gcloud config set project "$PROJECT_ID"

# Enable APIs
echo "📦 Enabling APIs..."
gcloud services enable run.googleapis.com sqladmin.googleapis.com secretmanager.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com --quiet

# Artifact Registry
echo "📦 Creating Artifact Registry..."
gcloud artifacts repositories describe "$ARTIFACT_REPO" --location="$REGION" &>/dev/null || \
gcloud artifacts repositories create "$ARTIFACT_REPO" --repository-format=docker --location="$REGION"

# Cloud SQL
echo "🗄️  Setting up Cloud SQL..."
if ! gcloud sql instances describe "$DB_INSTANCE_NAME" &>/dev/null; then
    DB_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)
    gcloud sql instances create "$DB_INSTANCE_NAME" --database-version=POSTGRES_16 --tier=db-f1-micro --region="$REGION" --quiet
    gcloud sql users create "$DB_USER" --instance="$DB_INSTANCE_NAME" --password="$DB_PASSWORD"
    gcloud sql databases create "$DB_NAME" --instance="$DB_INSTANCE_NAME"
    echo -n "$DB_PASSWORD" | gcloud secrets create db-password --data-file=- --replication-policy=automatic
fi

# Secrets
echo "🔐 Configuring secrets..."
[ -f "$ED25519_PRIVATE_KEY_PATH" ] && (gcloud secrets describe ed25519-private-key &>/dev/null && \
gcloud secrets versions add ed25519-private-key --data-file="$ED25519_PRIVATE_KEY_PATH" || \
gcloud secrets create ed25519-private-key --data-file="$ED25519_PRIVATE_KEY_PATH" --replication-policy=automatic)

# Build & Deploy
echo "🐳 Building image..."
IMAGE_URI="$REGION-docker.pkg.dev/$PROJECT_ID/$ARTIFACT_REPO/$SERVICE_NAME:latest"
gcloud builds submit --tag="$IMAGE_URI" --dockerfile=docker/Dockerfile .

echo "🚀 Deploying Cloud Run..."
CONNECTION_NAME=$(gcloud sql instances describe "$DB_INSTANCE_NAME" --format="value(connectionName)")
gcloud run deploy "$SERVICE_NAME" --image="$IMAGE_URI" --region="$REGION" --allow-unauthenticated \
--add-cloudsql-instances="$CONNECTION_NAME" --set-env-vars="DB_CONNECTION_NAME=$CONNECTION_NAME,DB_USER=$DB_USER,DB_NAME=$DB_NAME" \
--set-secrets="ED25519_PRIVATE_KEY_PEM=ed25519-private-key:latest,DB_PASSWORD=db-password:latest" --quiet

# Migrations
echo "📊 Running migrations..."
gcloud run jobs create "$SERVICE_NAME-migrate" --image="$IMAGE_URI" --region="$REGION" \
--add-cloudsql-instances="$CONNECTION_NAME" --command="alembic" --args="upgrade,head" --quiet || true
gcloud run jobs execute "$SERVICE_NAME-migrate" --region="$REGION" --wait

SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" --region="$REGION" --format="value(status.url)")
echo "✅ Deployed: $SERVICE_URL"
