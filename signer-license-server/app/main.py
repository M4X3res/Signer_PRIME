"""
Signer PRIME License Server
Production-ready FastAPI application с PostgreSQL и Ed25519.
"""
from contextlib import asynccontextmanager
import logging
import sys

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.db import init_db
from app.routes import license, admin, stripe_webhook

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

# Rate limiter для защиты от brute-force атак
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения."""
    logger.info("=" * 60)
    logger.info("Signer License Server starting...")
    
    try:
        settings = get_settings()
        
        # Проверка обязательных настроек
        try:
            db_url = settings.get_database_url()
            logger.info("✅ Database configuration found")
        except ValueError as e:
            logger.error(f"❌ Database not configured: {e}")
            logger.error("❌ Set DATABASE_URL or DB_CONNECTION_NAME environment variable")
            raise RuntimeError("Database configuration required") from e
        
        # Инициализация БД (engine и session factory, БЕЗ create_all)
        init_db()
        logger.info("✅ Database connection initialized")
        
        # Проверка приватного ключа
        if not settings.ed25519_private_key_pem:
            logger.error("❌ ED25519_PRIVATE_KEY_PEM not configured")
            logger.error("❌ Set ED25519_PRIVATE_KEY_PEM environment variable")
            raise RuntimeError("Ed25519 private key required")
        
        # Загрузка приватного ключа
        from app.crypto import load_private_key
        load_private_key(settings.ed25519_private_key_pem)
        logger.info("✅ Ed25519 private key loaded")
        
        logger.info("✅ Server ready (PostgreSQL + Ed25519)")
        logger.info("=" * 60)
        
        yield
        
    except Exception as e:
        logger.error(f"❌ Startup failed: {e}", exc_info=True)
        raise
    
    finally:
        logger.info("Signer License Server shutting down...")


# Создание приложения
app = FastAPI(
    title="Signer PRIME License Server",
    description="Production license server with PostgreSQL and Ed25519 signing",
    version="1.0.0",
    lifespan=lifespan
)

# Rate limiter setup
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В проде ограничьте конкретными доменами
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключение роутеров
app.include_router(license.router)
app.include_router(admin.router)
app.include_router(stripe_webhook.router)


@app.get("/health")
async def health_check():
    """Health check endpoint для Cloud Run и мониторинга."""
    return {
        "status": "ok",
        "service": "signer-license-server",
        "version": "1.0.0"
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Signer PRIME License Server",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }
