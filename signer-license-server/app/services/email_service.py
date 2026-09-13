"""
app/services/email_service.py

ЗАДАЧА 7: Отправка лицензионных ключей клиентам по email после оплаты.
Поддерживает SendGrid и Postmark.
"""
import logging
from datetime import datetime
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)


class EmailService:
    """Сервис для отправки email с лицензионными ключами."""
    
    def __init__(self):
        self.settings = get_settings()
        self.provider = self.settings.email_provider.lower()
        self.api_key = self.settings.email_api_key
        self.from_address = self.settings.email_from_address
        self.from_name = self.settings.email_from_name
        
        # Проверка настроек
        if not self.api_key:
            logger.warning("[EmailService] email_api_key не настроен, отправка email недоступна")
    
    def send_license_key(
        self,
        to_email: str,
        license_key: str,
        plan: str,
        expires_at: datetime
    ) -> bool:
        """
        Отправляет email с лицензионным ключом клиенту.
        
        Args:
            to_email: Email получателя
            license_key: Лицензионный ключ
            plan: План подписки (monthly, quarterly, yearly, internal)
            expires_at: Дата окончания подписки
        
        Returns:
            True если email отправлен успешно, False при ошибке
        """
        if not self.api_key:
            logger.warning(f"[EmailService] Пропуск отправки на {to_email}: API ключ не настроен")
            return False
        
        # Формируем тело письма
        plan_names = {
            "monthly": "Месячная подписка",
            "quarterly": "Подписка на 3 месяца",
            "yearly": "Годовая подписка",
            "internal": "Внутренняя лицензия"
        }
        plan_name = plan_names.get(plan, plan)
        expiry_date = expires_at.strftime("%d.%m.%Y")
        
        subject = "Ваш лицензионный ключ Signer PRIME"
        
        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background-color: #4CAF50; color: white; padding: 20px; text-align: center; }}
        .content {{ padding: 20px; background-color: #f9f9f9; }}
        .license-key {{ 
            font-size: 24px; 
            font-weight: bold; 
            color: #4CAF50; 
            padding: 15px; 
            background-color: #fff; 
            border: 2px solid #4CAF50; 
            text-align: center; 
            margin: 20px 0;
            letter-spacing: 2px;
        }}
        .info {{ margin: 10px 0; }}
        .footer {{ padding: 20px; text-align: center; color: #777; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Signer PRIME</h1>
        </div>
        <div class="content">
            <h2>Спасибо за покупку!</h2>
            <p>Ваша оплата успешно обработана. Ниже приведён ваш лицензионный ключ:</p>
            
            <div class="license-key">
                {license_key}
            </div>
            
            <div class="info">
                <p><strong>План подписки:</strong> {plan_name}</p>
                <p><strong>Действует до:</strong> {expiry_date}</p>
            </div>
            
            <h3>Как активировать лицензию:</h3>
            <ol>
                <li>Запустите приложение Signer PRIME</li>
                <li>При первом запуске откроется окно активации лицензии</li>
                <li>Введите ваш лицензионный ключ и нажмите "Активировать"</li>
            </ol>
            
            <p>Лицензия позволяет активировать приложение на нескольких устройствах (количество зависит от плана).</p>
            
            <p>Если у вас возникли вопросы, свяжитесь с нами по адресу support@signer-prime.com</p>
        </div>
        <div class="footer">
            <p>&copy; 2024 Signer PRIME. Все права защищены.</p>
        </div>
    </div>
</body>
</html>
"""
        
        text_body = f"""
Спасибо за покупку Signer PRIME!

Ваш лицензионный ключ:
{license_key}

План подписки: {plan_name}
Действует до: {expiry_date}

Как активировать лицензию:
1. Запустите приложение Signer PRIME
2. При первом запуске откроется окно активации лицензии
3. Введите ваш лицензионный ключ и нажмите "Активировать"

Лицензия позволяет активировать приложение на нескольких устройствах (количество зависит от плана).

Если у вас возникли вопросы, свяжитесь с нами по адресу support@signer-prime.com

---
© 2024 Signer PRIME. Все права защищены.
"""
        
        # Отправка через выбранный провайдер
        try:
            if self.provider == "sendgrid":
                return self._send_via_sendgrid(to_email, subject, html_body, text_body)
            elif self.provider == "postmark":
                return self._send_via_postmark(to_email, subject, html_body, text_body)
            else:
                logger.error(f"[EmailService] Неизвестный провайдер: {self.provider}")
                return False
        
        except Exception as e:
            logger.error(f"[EmailService] Ошибка отправки на {to_email}: {e}", exc_info=True)
            return False
    
    def _send_via_sendgrid(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str
    ) -> bool:
        """Отправка через SendGrid."""
        try:
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import Mail, Email, To, Content
            
            message = Mail(
                from_email=Email(self.from_address, self.from_name),
                to_emails=To(to_email),
                subject=subject,
                plain_text_content=Content("text/plain", text_body),
                html_content=Content("text/html", html_body)
            )
            
            sg = SendGridAPIClient(self.api_key)
            response = sg.send(message)
            
            if response.status_code in [200, 201, 202]:
                logger.info(f"[EmailService] ✅ Email отправлен (SendGrid): {to_email}")
                return True
            else:
                logger.error(f"[EmailService] SendGrid error: {response.status_code} {response.body}")
                return False
        
        except ImportError:
            logger.error("[EmailService] sendgrid library не установлена: pip install sendgrid")
            return False
        except Exception as e:
            logger.error(f"[EmailService] SendGrid exception: {e}", exc_info=True)
            return False
    
    def _send_via_postmark(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str
    ) -> bool:
        """Отправка через Postmark."""
        try:
            from postmarker.core import PostmarkClient
            
            client = PostmarkClient(server_token=self.api_key)
            
            response = client.emails.send(
                From=f"{self.from_name} <{self.from_address}>",
                To=to_email,
                Subject=subject,
                HtmlBody=html_body,
                TextBody=text_body
            )
            
            logger.info(f"[EmailService] ✅ Email отправлен (Postmark): {to_email}")
            return True
        
        except ImportError:
            logger.error("[EmailService] postmarker library не установлена: pip install postmarker")
            return False
        except Exception as e:
            logger.error(f"[EmailService] Postmark exception: {e}", exc_info=True)
            return False
