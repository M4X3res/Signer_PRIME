"""
tests/conftest.py

Pytest конфигурация и фикстуры с testcontainers для Postgres.
"""
import os
import pytest
from datetime import datetime, timedelta
from typing import Generator
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from fastapi.testclient import TestClient
from testcontainers.postgres import PostgresContainer
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
from alembic import command
from alembic.config import Config

from app.main import app
from app.db import get_db
from app.models import Base, License
from app.crypto import load_private_key
from app.config import get_settings


# ════════════════════════════════════════════════════════════════
# Test Crypto Keys
# ════════════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def test_ed25519_keys():
    """Генерация тестовой пары Ed25519 ключей."""
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode()
    
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    
    return {
        "private_key": private_key,
        "public_key": public_key,
        "private_pem": private_pem,
        "public_pem": public_pem
    }


# ════════════════════════════════════════════════════════════════
# Database Fixtures
# ════════════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def postgres_container():
    """Поднимает Postgres контейнер для тестов."""
    with PostgresContainer("postgres:16-alpine") as postgres:
        yield postgres


@pytest.fixture(scope="session")
def engine(postgres_container):
    """Создаёт SQLAlchemy engine с тестовой БД."""
    db_url = postgres_container.get_connection_url(driver="psycopg")
    engine = create_engine(db_url, pool_pre_ping=True)
    
    # Применение миграций Alembic
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")
    
    yield engine
    
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(engine) -> Generator[Session, None, None]:
    """Создаёт чистую сессию БД для каждого теста."""
    connection = engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(bind=connection)
    session = SessionLocal()
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()


# ════════════════════════════════════════════════════════════════
# FastAPI Test Client
# ════════════════════════════════════════════════════════════════

@pytest.fixture(scope="function")
def client(db_session: Session, test_ed25519_keys, postgres_container):
    """Создаёт FastAPI TestClient с тестовой БД."""
    
    # Override настроек для тестов
    os.environ["DATABASE_URL"] = postgres_container.get_connection_url(driver="psycopg")
    os.environ["ED25519_PRIVATE_KEY_PEM"] = test_ed25519_keys["private_pem"]
    os.environ["ADMIN_API_KEY"] = "test_admin_key"
    os.environ["STRIPE_SECRET_KEY"] = "sk_test_mock"
    os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_test_mock"
    
    # Загрузка приватного ключа
    load_private_key(test_ed25519_keys["private_pem"])
    
    # Override get_db dependency
    def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# Test Data Fixtures
# ════════════════════════════════════════════════════════════════

@pytest.fixture
def test_license(db_session: Session) -> License:
    """Создаёт тестовую лицензию в БД."""
    license_obj = License(
        id=uuid.uuid4(),
        license_key="SGNR-TEST-ABCD-1234-WXYZ",
        plan="monthly",
        status="active",
        current_period_end=datetime.utcnow() + timedelta(days=30),
        max_devices=2,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db_session.add(license_obj)
    db_session.commit()
    db_session.refresh(license_obj)
    
    return license_obj


@pytest.fixture
def admin_headers() -> dict:
    """Заголовки для admin API."""
    return {"X-Admin-Key": "test_admin_key"}
