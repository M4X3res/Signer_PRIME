#!/bin/bash
#
# local_dev_up.sh
# Скрипт для запуска локальной разработки с docker-compose
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "════════════════════════════════════════════════════════"
echo " Signer License Server - Local Development"
echo "════════════════════════════════════════════════════════"
echo ""

# Проверка наличия docker-compose
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose not found. Please install Docker Desktop."
    exit 1
fi

echo "📦 Starting services..."
docker-compose -f docker-compose.dev.yml up -d postgres adminer

echo ""
echo "⏳ Waiting for PostgreSQL to be ready..."
for i in {1..30}; do
    if docker-compose -f docker-compose.dev.yml exec -T postgres pg_isready -U signer_app -d signer_license > /dev/null 2>&1; then
        echo "✅ PostgreSQL is ready!"
        break
    fi
    
    if [ $i -eq 30 ]; then
        echo "❌ PostgreSQL failed to start within 30 seconds"
        docker-compose -f docker-compose.dev.yml logs postgres
        exit 1
    fi
    
    sleep 1
done

echo ""
echo "🚀 Starting License Server..."
docker-compose -f docker-compose.dev.yml up app

echo ""
echo "════════════════════════════════════════════════════════"
echo " Services:"
echo "  • License Server: http://localhost:8000"
echo "  • API Docs: http://localhost:8000/docs"
echo "  • Adminer (DB UI): http://localhost:8081"
echo "════════════════════════════════════════════════════════"
