"""
app/config.py
Конфигурация приложения через Pydantic Settings.
"""
import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Настройки приложения."""
    
    # Database
    database_url: str = ""
    db_connection_name: str = ""
    db_user: str = "signer_app"
    db_name: str = "signer_license"
    db_password: str = ""
    
    # Crypto
    ed25519_private_key_pem: str = ""
    
    # Admin API
    admin_api_key: str = ""
    
    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    
    # CORS
    cors_allowed_origins: str = "*"
    
    # Server
    port: int = 8080
    host: str = "0.0.0.0"
    
    # Logging
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = False
    
    def get_database_url(self) -> str:
        """
        Получить DATABASE_URL с учётом Cloud SQL.
        
        В Cloud Run подключение через Unix socket.
        В локальной разработке через обычный TCP.
        """
        if self.db_connection_name:
            # Cloud SQL через Unix socket
            db_socket_dir = "/cloudsql"
            return (
                f"postgresql+psycopg://{self.db_user}:{self.db_password}"
                f"@/{self.db_name}?host={db_socket_dir}/{self.db_connection_name}"
            )
        elif self.database_url:
            # Локальная разработка (docker-compose)
            return self.database_url
        else:
            raise ValueError("Either DATABASE_URL or DB_CONNECTION_NAME must be set")


@lru_cache()
def get_settings() -> Settings:
    """Получить настройки (кэшируется)."""
    return Settings()
