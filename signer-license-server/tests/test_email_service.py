"""
tests/test_email_service.py

ЗАДАЧА 7: Тесты для EmailService.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from app.services.email_service import EmailService
from app.config import Settings


@pytest.fixture
def mock_settings():
    """Создаёт мок настроек с email провайдером."""
    settings = Settings(
        database_url="postgresql://test",
        email_provider="sendgrid",
        email_api_key="test-api-key",
        email_from_address="test@example.com",
        email_from_name="Test Sender"
    )
    return settings


@pytest.fixture
def email_service(mock_settings):
    """Создаёт EmailService с мок настройками."""
    with patch("app.services.email_service.get_settings", return_value=mock_settings):
        service = EmailService()
        return service


def test_send_license_key_no_api_key():
    """Тест: отправка email без API ключа должна вернуть False."""
    settings = Settings(
        database_url="postgresql://test",
        email_provider="sendgrid",
        email_api_key="",  # Пустой ключ
        email_from_address="test@example.com"
    )
    
    with patch("app.services.email_service.get_settings", return_value=settings):
        service = EmailService()
        
        result = service.send_license_key(
            to_email="customer@example.com",
            license_key="SGNR-TEST-TEST-TEST-TEST",
            plan="monthly",
            expires_at=datetime.now() + timedelta(days=30)
        )
        
        assert result is False


@patch("app.services.email_service.SendGridAPIClient")
def test_send_license_key_sendgrid_success(mock_sendgrid, email_service):
    """Тест: успешная отправка через SendGrid."""
    # Мокируем ответ SendGrid
    mock_response = MagicMock()
    mock_response.status_code = 202
    mock_sg_instance = MagicMock()
    mock_sg_instance.send.return_value = mock_response
    mock_sendgrid.return_value = mock_sg_instance
    
    result = email_service.send_license_key(
        to_email="customer@example.com",
        license_key="SGNR-TEST-TEST-TEST-TEST",
        plan="yearly",
        expires_at=datetime(2025, 12, 31)
    )
    
    assert result is True
    mock_sendgrid.assert_called_once_with("test-api-key")
    mock_sg_instance.send.assert_called_once()


@patch("app.services.email_service.SendGridAPIClient")
def test_send_license_key_sendgrid_failure(mock_sendgrid, email_service):
    """Тест: ошибка при отправке через SendGrid."""
    # Мокируем ошибку SendGrid
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.body = "Bad Request"
    mock_sg_instance = MagicMock()
    mock_sg_instance.send.return_value = mock_response
    mock_sendgrid.return_value = mock_sg_instance
    
    result = email_service.send_license_key(
        to_email="customer@example.com",
        license_key="SGNR-TEST-TEST-TEST-TEST",
        plan="monthly",
        expires_at=datetime.now() + timedelta(days=30)
    )
    
    assert result is False


@patch("app.services.email_service.SendGridAPIClient")
def test_send_license_key_sendgrid_exception(mock_sendgrid, email_service):
    """Тест: исключение при отправке через SendGrid не роняет приложение."""
    # Мокируем исключение
    mock_sendgrid.side_effect = Exception("Network error")
    
    result = email_service.send_license_key(
        to_email="customer@example.com",
        license_key="SGNR-TEST-TEST-TEST-TEST",
        plan="monthly",
        expires_at=datetime.now() + timedelta(days=30)
    )
    
    assert result is False


@patch("app.services.email_service.PostmarkClient")
def test_send_license_key_postmark_success(mock_postmark):
    """Тест: успешная отправка через Postmark."""
    settings = Settings(
        database_url="postgresql://test",
        email_provider="postmark",
        email_api_key="test-postmark-key",
        email_from_address="test@example.com",
        email_from_name="Test Sender"
    )
    
    with patch("app.services.email_service.get_settings", return_value=settings):
        service = EmailService()
        
        # Мокируем ответ Postmark
        mock_client_instance = MagicMock()
        mock_postmark.return_value = mock_client_instance
        
        result = service.send_license_key(
            to_email="customer@example.com",
            license_key="SGNR-TEST-TEST-TEST-TEST",
            plan="quarterly",
            expires_at=datetime(2025, 6, 30)
        )
        
        assert result is True
        mock_postmark.assert_called_once_with(server_token="test-postmark-key")
        mock_client_instance.emails.send.assert_called_once()


def test_send_license_key_plan_names(email_service):
    """Тест: корректное отображение названий планов в email."""
    with patch.object(email_service, '_send_via_sendgrid', return_value=True) as mock_send:
        # Тестируем все планы
        plans = [
            ("monthly", "Месячная подписка"),
            ("quarterly", "Подписка на 3 месяца"),
            ("yearly", "Годовая подписка"),
            ("internal", "Внутренняя лицензия")
        ]
        
        for plan_code, expected_name in plans:
            result = email_service.send_license_key(
                to_email="customer@example.com",
                license_key="SGNR-TEST-TEST-TEST-TEST",
                plan=plan_code,
                expires_at=datetime.now() + timedelta(days=30)
            )
            
            assert result is True
            
            # Проверяем, что название плана присутствует в HTML-теле письма
            call_args = mock_send.call_args
            html_body = call_args[0][2]  # 3-й аргумент _send_via_sendgrid
            assert expected_name in html_body


def test_email_body_contains_license_key(email_service):
    """Тест: лицензионный ключ присутствует в теле письма."""
    license_key = "SGNR-ABCD-EFGH-IJKL-MNOP"
    
    with patch.object(email_service, '_send_via_sendgrid', return_value=True) as mock_send:
        email_service.send_license_key(
            to_email="customer@example.com",
            license_key=license_key,
            plan="monthly",
            expires_at=datetime.now() + timedelta(days=30)
        )
        
        call_args = mock_send.call_args
        html_body = call_args[0][2]
        text_body = call_args[0][3]
        
        assert license_key in html_body
        assert license_key in text_body
