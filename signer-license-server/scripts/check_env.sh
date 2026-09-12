#!/bin/bash
#
# check_env.sh
# Проверка, что все необходимые переменные окружения настроены для деплоя
#

set -e

echo "════════════════════════════════════════════════════════"
echo " Environment Check"
echo "════════════════════════════════════════════════════════"
echo ""

REQUIRED_VARS=(
    "DATABASE_URL:DB_CONNECTION_NAME"  # Хотя бы одно из двух
    "ED25519_PRIVATE_KEY_PEM"
    "ADMIN_API_KEY"
)

OPTIONAL_VARS=(
    "STRIPE_SECRET_KEY"
    "STRIPE_WEBHOOK_SECRET"
    "DB_USER"
    "DB_NAME"
    "DB_PASSWORD"
)

ERRORS=0

# Проверка обязательных переменных
for VAR_GROUP in "${REQUIRED_VARS[@]}"; do
    IFS=':' read -ra VARS <<< "$VAR_GROUP"
    
    FOUND=0
    for VAR in "${VARS[@]}"; do
        if [ -n "${!VAR}" ]; then
            echo "✅ $VAR is set"
            FOUND=1
            break
        fi
    done
    
    if [ $FOUND -eq 0 ]; then
        echo "❌ Missing required: ${VARS[*]}"
        ERRORS=$((ERRORS + 1))
    fi
done

echo ""
echo "Optional variables:"
for VAR in "${OPTIONAL_VARS[@]}"; do
    if [ -n "${!VAR}" ]; then
        echo "✅ $VAR is set"
    else
        echo "⚠️  $VAR not set (optional)"
    fi
done

echo ""
echo "════════════════════════════════════════════════════════"

if [ $ERRORS -gt 0 ]; then
    echo "❌ $ERRORS required variable(s) missing"
    echo ""
    echo "Set them in .env file or export:"
    echo "  export DATABASE_URL=postgresql://..."
    echo "  export ED25519_PRIVATE_KEY_PEM='-----BEGIN PRIVATE KEY-----...'"
    echo "  export ADMIN_API_KEY=your_secret_key"
    exit 1
else
    echo "✅ All required variables are set"
    echo ""
    echo "Ready to deploy!"
    exit 0
fi
