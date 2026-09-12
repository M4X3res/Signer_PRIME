"""
app/db.py
Подключение к базе данных (Cloud SQL и локальная разработка).
"""
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
from .config import get_settings
from .models import Base

logger = logging.getLogger(__name__)

# Engine (создаётся один раз)
_engine = None
_SessionLocal = None


def init_db():
    """Инициализировать подключение к БД."""
    global _engine, _SessionLocal
    
    settings = get_settings()
    database_url = settings.get_database_url()
    
    logger.info(f"Connecting to database...")
    
    _engine = create_engine(
        database_url,
        pool_pre_ping=True,  # Проверка соединения перед использованием
        pool_size=5,
        max_overflow=10
    )
    
    _SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=_engine
    )
    
    logger.info("Database connection initialized")


def get_engine():
    """Получить engine."""
    if _engine is None:
        init_db()
    return _engine


def get_session_local():
    """Получить SessionLocal."""
    if _SessionLocal is None:
        init_db()
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """
    Dependency для FastAPI.
    
    Usage:
        @app.get("/")
        def endpoint(db: Session = Depends(get_db)):
            ...
    """
    SessionLocal = get_session_local()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """Создать таблицы (только для разработки, в проде используйте Alembic)."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    logger.info("Tables created")
