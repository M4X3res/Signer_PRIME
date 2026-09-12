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

# Ed25519 private key
if [ -f "$ED25519_PRIVATE_KEY_PATH" ]; then
    if gcloud secrets describe ed25519-private-key &>/dev/null; then
        gcloud secrets versions add ed25519-private-key --data-file="$ED25519_PRIVATE_KEY_PATH"
        echo "✅ Ed25519 private key updated"
    else
        gcloud secrets create ed25519-private-key --data-file="$ED25519_PRIVATE_KEY_PATH" --replication-policy=automatic
        echo "✅ Ed25519 private key created"
    fi
fi

# Admin API key (обязательный)
if [ -z "$ADMIN_API_KEY" ]; then
    echo "⚙️  ADMIN_API_KEY not provided, generating new one..."
    ADMIN_API_KEY=$(openssl rand -hex 32)
    echo "📝 Generated ADMIN_API_KEY: $ADMIN_API_KEY"
    echo "📝 Save this key securely for admin API access!"
fi

if gcloud secrets describe admin-api-key &>/dev/null; then
    echo -n "$ADMIN_API_KEY" | gcloud secrets versions add admin-api-key --data-file=-
    echo "✅ Admin API key updated"
else
    echo -n "$ADMIN_API_KEY" | gcloud secrets create admin-api-key --data-file=- --replication-policy=automatic
    echo "✅ Admin API key created"
fi

# Stripe keys (опциональные)
if [ -n "$STRIPE_SECRET_KEY" ]; then
    if gcloud secrets describe stripe-secret-key &>/dev/null; then
        echo -n "$STRIPE_SECRET_KEY" | gcloud secrets versions add stripe-secret-key --data-file=-
        echo "✅ Stripe secret key updated"
    else
        echo -n "$STRIPE_SECRET_KEY" | gcloud secrets create stripe-secret-key --data-file=- --replication-policy=automatic
        echo "✅ Stripe secret key created"
    fi
else
    echo "⚠️  WARNING: STRIPE_SECRET_KEY not provided - Stripe integration will be unavailable"
fi

if [ -n "$STRIPE_WEBHOOK_SECRET" ]; then
    if gcloud secrets describe stripe-webhook-secret &>/dev/null; then
        echo -n "$STRIPE_WEBHOOK_SECRET" | gcloud secrets versions add stripe-webhook-secret --data-file=-
        echo "✅ Stripe webhook secret updated"
    else
        echo -n "$STRIPE_WEBHOOK_SECRET" | gcloud secrets create stripe-webhook-secret --data-file=- --replication-policy=automatic
        echo "✅ Stripe webhook secret created"
    fi
else
    echo "⚠️  WARNING: STRIPE_WEBHOOK_SECRET not provided - Stripe webhooks will be unavailable"
fi

# Build & Deploy
echo "🐳 Building image..."
IMAGE_URI="$REGION-docker.pkg.dev/$PROJECT_ID/$ARTIFACT_REPO/$SERVICE_NAME:latest"
gcloud builds submit --tag="$IMAGE_URI" --dockerfile=docker/Dockerfile .

echo "🚀 Deploying Cloud Run..."
CONNECTION_NAME=$(gcloud sql instances describe "$DB_INSTANCE_NAME" --format="value(connectionName)")

# Собираем --set-secrets (обязательные + условные)
SECRETS="ED25519_PRIVATE_KEY_PEM=ed25519-private-key:latest,DB_PASSWORD=db-password:latest,ADMIN_API_KEY=admin-api-key:latest"

if [ -n "$STRIPE_SECRET_KEY" ]; then
    SECRETS="$SECRETS,STRIPE_SECRET_KEY=stripe-secret-key:latest"
fi

if [ -n "$STRIPE_WEBHOOK_SECRET" ]; then
    SECRETS="$SECRETS,STRIPE_WEBHOOK_SECRET=stripe-webhook-secret:latest"
fi

# CORS origins (рекомендуемый параметр)
CORS_ORIGINS="${CORS_ALLOWED_ORIGINS:-*}"
if [ "$CORS_ORIGINS" = "*" ]; then
    echo "⚠️  WARNING: CORS_ALLOWED_ORIGINS not set, using wildcard (*) - not recommended for production"
    echo "⚠️  Set CORS_ALLOWED_ORIGINS='https://your-domain.com,https://app.your-domain.com' for production"
fi

gcloud run deploy "$SERVICE_NAME" --image="$IMAGE_URI" --region="$REGION" --allow-unauthenticated \
--add-cloudsql-instances="$CONNECTION_NAME" \
--set-env-vars="DB_CONNECTION_NAME=$CONNECTION_NAME,DB_USER=$DB_USER,DB_NAME=$DB_NAME,CORS_ALLOWED_ORIGINS=$CORS_ORIGINS" \
--set-secrets="$SECRETS" --quiet

# Migrations
echo "📊 Running migrations..."
gcloud run jobs create "$SERVICE_NAME-migrate" --image="$IMAGE_URI" --region="$REGION" \
--add-cloudsql-instances="$CONNECTION_NAME" --command="alembic" --args="upgrade,head" --quiet || true
gcloud run jobs execute "$SERVICE_NAME-migrate" --region="$REGION" --wait

SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" --region="$REGION" --format="value(status.url)")
echo "✅ Deployed: $SERVICE_URL"
echo ""
echo "📝 Admin API Key: $ADMIN_API_KEY"
echo "📝 Save this key for admin API operations!"
