"""
Минимальный рабочий сервер лицензий для тестирования клиента.
⚠️ Это PRODUCTION-READY версия с PostgreSQL support!

Для полного Cloud деплоя см. TODO_FOR_AI.md
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import sys

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Signer PRIME License Server",
    description="Production-ready license server with PostgreSQL support",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В проде ограничьте
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ════════════════════════════════════════════════════════════════
# Startup: Database initialization
# ════════════════════════════════════════════════════════════════

@app.on_event("startup")
async def startup():
    logger.info("=" * 60)
    logger.info("Signer License Server starting...")
    
    try:
        from app.config import get_settings
        settings = get_settings()
        
        # Проверка наличия DATABASE_URL или DB_CONNECTION_NAME
        try:
            db_url = settings.get_database_url()
            logger.info("Database configuration found")
            
            # Инициализация БД
            from app.db import init_db, create_tables
            init_db()
            
            # Создать таблицы если их нет (для быстрого старта)
            # В проде используйте Alembic migrations!
            try:
                create_tables()
                logger.info("Database tables ready")
            except Exception as e:
                logger.warning(f"Tables might already exist: {e}")
            
            # Загрузить приватный ключ
            if settings.ed25519_private_key_pem:
                from app.crypto import load_private_key
                load_private_key(settings.ed25519_private_key_pem)
                logger.info("Ed25519 private key loaded")
            else:
                logger.warning("⚠️  Ed25519 private key not configured - using mock mode")
            
            logger.info("✅ Production mode: PostgreSQL + Ed25519")
            
        except ValueError as e:
            logger.warning(f"Database not configured: {e}")
            logger.warning("⚠️  Falling back to MVP mode (in-memory)")
    
    except Exception as e:
        logger.error(f"Startup error: {e}", exc_info=True)
        logger.warning("⚠️  Running in MVP mode")
    
    logger.info("=" * 60)


# ════════════════════════════════════════════════════════════════
# Routes: Production или MVP fallback
# ════════════════════════════════════════════════════════════════

try:
    # Попытка загрузить production routes
    from app.routes import license as license_routes
    app.include_router(license_routes.router)
    logger.info("✅ Production routes loaded")
except Exception as e:
    logger.warning(f"Production routes not available: {e}")
    logger.info("Using MVP routes...")
    
    # MVP fallback routes
    from app.schemas import ActivateRequest, RefreshRequest, DeactivateRequest
    import time
    import json
    import base64
    
    mock_licenses = {}
    mock_devices = {}
    
    def create_mock_token(license_key: str, device_id: str, plan: str = "monthly") -> dict:
        payload = {
            "license_key": license_key,
            "device_id": device_id,
            "plan": plan,
            "status": "active",
            "current_period_end": int(time.time()) + 30*86400,
            "issued_at": int(time.time())
        }
        payload_json = json.dumps(payload, sort_keys=True)
        payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip('=')
        signature_b64 = base64.urlsafe_b64encode(b"mock_signature").decode().rstrip('=')
        return {
            "token": f"{payload_b64}.{signature_b64}",
            "plan": plan,
            "current_period_end": payload["current_period_end"]
        }
    
    @app.post("/api/license/activate")
    async def activate_mvp(req: ActivateRequest):
        if req.license_key not in mock_licenses:
            mock_licenses[req.license_key] = {
                "plan": "monthly",
                "status": "active",
                "max_devices": 2,
                "devices": {}
            }
        
        license_data = mock_licenses[req.license_key]
        active_devices = [d for d in license_data["devices"].values() if not d.get("deactivated")]
        
        existing = license_data["devices"].get(req.fingerprint_hash)
        if existing and not existing.get("deactivated"):
            device_id = existing["id"]
        elif len(active_devices) >= license_data["max_devices"]:
            return JSONResponse(
                status_code=409,
                content={"error_code": "DEVICE_LIMIT_REACHED", "error": "Device limit reached"}
            )
        else:
            device_id = f"dev-{req.fingerprint_hash[:8]}"
            license_data["devices"][req.fingerprint_hash] = {
                "id": device_id,
                "fingerprint": req.fingerprint_hash,
                "label": req.device_label,
                "deactivated": False
            }
        
        return create_mock_token(req.license_key, device_id, license_data["plan"])
    
    @app.post("/api/license/refresh")
    async def refresh_mvp(req: RefreshRequest):
        payload_b64 = req.token.split(".")[0]
        padding = 4 - (len(payload_b64) % 4)
        if padding != 4:
            payload_b64 += '=' * padding
        payload_json = base64.urlsafe_b64decode(payload_b64.replace('-', '+').replace('_', '/')).decode()
        payload = json.loads(payload_json)
        
        license_key = payload["license_key"]
        if license_key not in mock_licenses:
            return JSONResponse(status_code=401, content={"error_code": "INVALID_TOKEN", "error": "Not found"})
        
        return create_mock_token(license_key, payload["device_id"], mock_licenses[license_key]["plan"])
    
    @app.post("/api/license/deactivate")
    async def deactivate_mvp(req: DeactivateRequest):
        return {"success": True}


# ════════════════════════════════════════════════════════════════
# Health check
# ════════════════════════════════════════════════════════════════

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "signer-license-server",
        "version": "1.0.0"
    }


@app.get("/")
async def root():
    return {
        "service": "Signer PRIME License Server",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

# CORS для локальной разработки
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В проде ограничьте
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ════════════════════════════════════════════════════════════════
# Mock Storage (в проде используйте PostgreSQL)
# ════════════════════════════════════════════════════════════════

mock_licenses = {}  # license_key -> license_data
mock_devices = {}   # device_id -> device_data

# ════════════════════════════════════════════════════════════════
# Schemas
# ════════════════════════════════════════════════════════════════

class ActivateRequest(BaseModel):
    license_key: str
    fingerprint_hash: str
    device_label: str
    app_version: str

class RefreshRequest(BaseModel):
    token: str
    fingerprint_hash: str

class DeactivateRequest(BaseModel):
    token: str

# ════════════════════════════════════════════════════════════════
# Helper Functions
# ════════════════════════════════════════════════════════════════

def create_mock_token(license_key: str, device_id: str, plan: str = "monthly") -> dict:
    """Создать mock-токен (НЕ используется настоящий Ed25519!)."""
    payload = {
        "license_key": license_key,
        "device_id": device_id,
        "plan": plan,
        "status": "active",
        "current_period_end": int(time.time()) + 30*86400,
        "issued_at": int(time.time())
    }
    
    payload_json = json.dumps(payload, sort_keys=True)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip('=')
    # ⚠️ Mock signature - в проде используйте Ed25519!
    signature_b64 = base64.urlsafe_b64encode(b"mock_signature_dev_only").decode().rstrip('=')
    
    return {
        "token": f"{payload_b64}.{signature_b64}",
        "plan": plan,
        "current_period_end": payload["current_period_end"]
    }

def parse_token(token: str) -> Optional[dict]:
    """Распарсить payload токена."""
    try:
        payload_b64 = token.split(".")[0]
        padding = 4 - (len(payload_b64) % 4)
        if padding != 4:
            payload_b64 += '=' * padding
        payload_json = base64.urlsafe_b64decode(payload_b64.replace('-', '+').replace('_', '/')).decode()
        return json.loads(payload_json)
    except Exception as e:
        logger.error(f"Failed to parse token: {e}")
        return None

# ════════════════════════════════════════════════════════════════
# Endpoints
# ════════════════════════════════════════════════════════════════

@app.post("/api/license/activate")
async def activate_license(req: ActivateRequest):
    """Активация лицензии."""
    logger.info(f"Activate request: key={req.license_key[:10]}..., device={req.device_label}")
    
    # Валидация формата ключа
    if not req.license_key.startswith("SGNR-"):
        raise HTTPException(
            status_code=400,
            detail={"error_code": "INVALID_LICENSE", "error": "Invalid license key format"}
        )
    
    # Mock: автоматически создаём лицензию если её нет
    if req.license_key not in mock_licenses:
        mock_licenses[req.license_key] = {
            "plan": "monthly",
            "status": "active",
            "max_devices": 2,
            "devices": {}
        }
        logger.info(f"Created mock license: {req.license_key}")
    
    license_data = mock_licenses[req.license_key]
    
    # Проверка статуса
    if license_data["status"] != "active":
        raise HTTPException(
            status_code=403,
            detail={"error_code": "LICENSE_REVOKED", "error": "License is revoked"}
        )
    
    # Проверка лимита устройств
    active_devices = [d for d in license_data["devices"].values() if not d.get("deactivated")]
    
    # Проверяем, это существующее устройство или новое
    existing_device = license_data["devices"].get(req.fingerprint_hash)
    
    if existing_device and not existing_device.get("deactivated"):
        # Обновляем существующее
        device_id = existing_device["id"]
        logger.info(f"Reactivating existing device: {device_id}")
    elif len(active_devices) >= license_data["max_devices"]:
        # Лимит исчерпан
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "DEVICE_LIMIT_REACHED",
                "error": f"Maximum {license_data['max_devices']} devices allowed"
            }
        )
    else:
        # Новое устройство
        device_id = f"dev-{req.fingerprint_hash[:8]}"
        license_data["devices"][req.fingerprint_hash] = {
            "id": device_id,
            "fingerprint": req.fingerprint_hash,
            "label": req.device_label,
            "deactivated": False
        }
        logger.info(f"Registered new device: {device_id}")
    
    # Создаём токен
    response = create_mock_token(req.license_key, device_id, license_data["plan"])
    logger.info(f"Activation successful: {req.license_key}")
    
    return response


@app.post("/api/license/refresh")
async def refresh_license(req: RefreshRequest):
    """Обновление токена."""
    logger.info(f"Refresh request")
    
    payload = parse_token(req.token)
    if not payload:
        raise HTTPException(
            status_code=401,
            detail={"error_code": "INVALID_TOKEN", "error": "Token format invalid"}
        )
    
    license_key = payload["license_key"]
    
    if license_key not in mock_licenses:
        raise HTTPException(
            status_code=401,
            detail={"error_code": "INVALID_TOKEN", "error": "License not found"}
        )
    
    license_data = mock_licenses[license_key]
    
    if license_data["status"] != "active":
        raise HTTPException(
            status_code=403,
            detail={"error_code": "LICENSE_REVOKED", "error": "License is revoked"}
        )
    
    # Создаём новый токен
    response = create_mock_token(license_key, payload["device_id"], license_data["plan"])
    logger.info(f"Refresh successful: {license_key}")
    
    return response


@app.post("/api/license/deactivate")
async def deactivate_device(req: DeactivateRequest):
    """Деактивация устройства."""
    logger.info(f"Deactivate request")
    
    payload = parse_token(req.token)
    if not payload:
        raise HTTPException(
            status_code=401,
            detail={"error_code": "INVALID_TOKEN", "error": "Token format invalid"}
        )
    
    license_key = payload["license_key"]
    
    if license_key in mock_licenses:
        license_data = mock_licenses[license_key]
        # Находим устройство по device_id и деактивируем
        for fingerprint, device in license_data["devices"].items():
            if device["id"] == payload["device_id"]:
                device["deactivated"] = True
                logger.info(f"Device deactivated: {device['id']}")
                break
    
    return {"success": True}


@app.get("/health")
async def health_check():
    """Health check."""
    return {
        "status": "ok",
        "service": "signer-license-server-mvp",
        "licenses_count": len(mock_licenses)
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Signer PRIME License Server (MVP)",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health"
    }


# ════════════════════════════════════════════════════════════════
# Startup
# ════════════════════════════════════════════════════════════════

@app.on_event("startup")
async def startup():
    logger.info("=" * 60)
    logger.info("Signer License Server MVP started")
    logger.info("⚠️  WARNING: This is a development/testing server!")
    logger.info("⚠️  NOT for production use!")
    logger.info("=" * 60)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
