"""
ui/widgets/license_dialog.py
Диалог активации лицензии Signer PRIME.
Два состояния: ввод ключа + информация о лицензии.
"""
import logging
import webbrowser
from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QWidget, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QFont

from ui.themes.theme_manager import theme_manager
from licensing.license_manager import LicenseManager, LicenseStatus

logger = logging.getLogger(__name__)


# URL для покупки подписки (TODO: заменить на реальный)
PURCHASE_URL = "https://signer-prime.com/pricing"


class BtnPrimary(QPushButton):
    """Основная кнопка (стиль из settings_page)."""
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(40)
        self._update_style()
        theme_manager.theme_changed.connect(self._update_style)
    
    def _update_style(self, _=None):
        t = theme_manager.tokens
        self.setStyleSheet(f"""
            QPushButton {{
                background: {t['accent']};
                color: {t['text_on_accent']};
                border: none;
                border-radius: 6px;
                font-weight: 600;
                padding: 0 24px;
            }}
            QPushButton:hover {{
                background: {t['accent_hover']};
            }}
            QPushButton:pressed {{
                background: {t['accent_pressed']};
            }}
            QPushButton:disabled {{
                background: {t.get('bg_tertiary', '#1c2128')};
                color: {t['text_secondary']};
            }}
        """)


class BtnSecondary(QPushButton):
    """Вторичная кнопка (стиль из settings_page)."""
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(40)
        self._update_style()
        theme_manager.theme_changed.connect(self._update_style)
    
    def _update_style(self, _=None):
        t = theme_manager.tokens
        self.setStyleSheet(f"""
            QPushButton {{
                background: {t.get('bg_secondary', '#161b22')};
                color: {t['text_primary']};
                border: 1px solid {t.get('border_default', '#30363d')};
                border-radius: 6px;
                font-weight: 600;
                padding: 0 24px;
            }}
            QPushButton:hover {{
                background: {t.get('bg_hover', '#2d333b')};
                border-color: {t.get('border_strong', '#444c56')};
            }}
            QPushButton:pressed {{
                background: {t.get('bg_active', '#373e47')};
            }}
            QPushButton:disabled {{
                background: {t.get('bg_tertiary', '#1c2128')};
                color: {t['text_secondary']};
                border-color: {t.get('border_subtle', '#21262d')};
            }}
        """)


class BtnLink(QPushButton):
    """Кнопка-ссылка."""
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)
        self._update_style()
        theme_manager.theme_changed.connect(self._update_style)
    
    def _update_style(self, _=None):
        t = theme_manager.tokens
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {t['accent']};
                border: none;
                text-decoration: underline;
                padding: 0;
            }}
            QPushButton:hover {{
                color: {t['accent_hover']};
            }}
        """)


class ActivateWorker(QThread):
    """Воркер для асинхронной активации лицензии."""
    finished = pyqtSignal(bool, str)  # (success, error_message)
    
    def __init__(self, manager: LicenseManager, license_key: str):
        super().__init__()
        self.manager = manager
        self.license_key = license_key
    
    def run(self):
        """Выполняется в отдельном потоке."""
        try:
            success, error_msg = self.manager.activate(self.license_key)
            self.finished.emit(success, error_msg)
        except Exception as e:
            logger.error(f"[ActivateWorker] Error: {e}", exc_info=True)
            self.finished.emit(False, f"Unexpected error: {e}")


class DeactivateWorker(QThread):
    """Воркер для асинхронной деактивации устройства."""
    finished = pyqtSignal(bool, str)  # (success, error_message)
    
    def __init__(self, manager: LicenseManager):
        super().__init__()
        self.manager = manager
    
    def run(self):
        """Выполняется в отдельном потоке."""
        try:
            success, error_msg = self.manager.deactivate_this_device()
            self.finished.emit(success, error_msg)
        except Exception as e:
            logger.error(f"[DeactivateWorker] Error: {e}", exc_info=True)
            self.finished.emit(False, f"Unexpected error: {e}")


class LicenseDialog(QDialog):
    """
    Диалог лицензии с двумя состояниями:
    1. Ввод ключа (NOT_ACTIVATED, EXPIRED, REVOKED)
    2. Информация о лицензии (VALID, GRACE_PERIOD)
    """
    
    def __init__(self, manager: LicenseManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.activate_worker: Optional[ActivateWorker] = None
        self.deactivate_worker: Optional[DeactivateWorker] = None
        
        self.setWindowTitle("Активация Signer PRIME")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setMinimumHeight(300)
        
        # Проверяем текущий статус
        self.status = manager.check_local_status()
        
        self._setup_ui()
        self._refresh_state()
        self._update_theme()
        theme_manager.theme_changed.connect(self._update_theme)
    
    def _setup_ui(self):
        """Инициализация UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        # ── Заголовок ──
        self.title_label = QLabel()
        self.title_label.setObjectName("DialogTitle")
        font = QFont()
        font.setPointSize(16)
        font.setBold(True)
        self.title_label.setFont(font)
        layout.addWidget(self.title_label)
        
        # ── Описание ──
        self.description_label = QLabel()
        self.description_label.setObjectName("DescriptionLabel")
        self.description_label.setWordWrap(True)
        layout.addWidget(self.description_label)
        
        # ════════════════════════════════════════════════════════════════
        # Виджет ввода ключа
        # ════════════════════════════════════════════════════════════════
        self.input_widget = QWidget()
        input_layout = QVBoxLayout(self.input_widget)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(12)
        
        # Поле ввода ключа
        key_label = QLabel("Лицензионный ключ:")
        key_label.setObjectName("FieldLabel")
        input_layout.addWidget(key_label)
        
        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("SGNR-XXXX-XXXX-XXXX-XXXX")
        self.key_input.setMaxLength(24)  # 4 блока по 4 символа + 3 дефиса
        self.key_input.textChanged.connect(self._format_license_key)
        self.key_input.returnPressed.connect(self._activate)
        input_layout.addWidget(self.key_input)
        
        # Кнопка "Купить подписку"
        purchase_layout = QHBoxLayout()
        purchase_layout.setSpacing(8)
        purchase_label = QLabel("Нет лицензии?")
        purchase_layout.addWidget(purchase_label)
        self.purchase_btn = BtnLink("Купить подписку")
        self.purchase_btn.clicked.connect(self._open_purchase_url)
        purchase_layout.addWidget(self.purchase_btn)
        purchase_layout.addStretch()
        input_layout.addLayout(purchase_layout)
        
        layout.addWidget(self.input_widget)
        
        # ════════════════════════════════════════════════════════════════
        # Виджет информации о лицензии
        # ════════════════════════════════════════════════════════════════
        self.info_widget = QWidget()
        info_layout = QVBoxLayout(self.info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(12)
        
        # Информация о плане
        self.plan_label = QLabel()
        self.plan_label.setObjectName("PlanLabel")
        info_layout.addWidget(self.plan_label)
        
        # Дата окончания
        self.expiry_label = QLabel()
        self.expiry_label.setObjectName("ExpiryLabel")
        info_layout.addWidget(self.expiry_label)
        
        # Ключ лицензии
        self.license_key_label = QLabel()
        self.license_key_label.setObjectName("LicenseKeyLabel")
        self.license_key_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        info_layout.addWidget(self.license_key_label)
        
        layout.addWidget(self.info_widget)
        
        # ── Статус/ошибка ──
        self.status_label = QLabel()
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        
        # ── Кнопки ──
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        
        # Кнопка деактивации (только для VALID/GRACE_PERIOD)
        self.deactivate_btn = BtnSecondary("Деактивировать устройство")
        self.deactivate_btn.clicked.connect(self._deactivate)
        btn_layout.addWidget(self.deactivate_btn)
        
        btn_layout.addStretch()
        
        # Основные кнопки
        self.cancel_btn = BtnSecondary("Отмена")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)
        
        self.activate_btn = BtnPrimary("Активировать")
        self.activate_btn.clicked.connect(self._activate)
        btn_layout.addWidget(self.activate_btn)
        
        self.close_btn = BtnPrimary("Закрыть")
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)
        
        layout.addLayout(btn_layout)
    
    def _refresh_state(self):
        """Обновляет UI в зависимости от статуса лицензии."""
        if self.status in (LicenseStatus.VALID, LicenseStatus.GRACE_PERIOD):
            self._show_info_state()
        else:
            self._show_input_state()
    
    def _show_input_state(self):
        """Показывает состояние ввода ключа."""
        self.title_label.setText("Активация Signer PRIME")
        
        if self.status == LicenseStatus.NOT_ACTIVATED:
            self.description_label.setText(
                "Для использования Signer PRIME необходима активная подписка. "
                "Введите лицензионный ключ, полученный после оплаты."
            )
        elif self.status == LicenseStatus.EXPIRED:
            self.description_label.setText(
                "Ваша подписка истекла. Пожалуйста, продлите подписку и "
                "введите новый лицензионный ключ."
            )
        elif self.status == LicenseStatus.REVOKED:
            self.description_label.setText(
                "Ваша лицензия была отозвана. Пожалуйста, свяжитесь с поддержкой "
                "или введите новый лицензионный ключ."
            )
        else:
            self.description_label.setText(
                "Введите лицензионный ключ для активации."
            )
        
        # Видимость элементов
        self.input_widget.setVisible(True)
        self.info_widget.setVisible(False)
        self.activate_btn.setVisible(True)
        self.close_btn.setVisible(False)
        self.deactivate_btn.setVisible(False)
        self.cancel_btn.setVisible(True)
        self.status_label.setText("")
    
    def _show_info_state(self):
        """Показывает информацию о лицензии."""
        plan_info = self.manager.get_plan_info()
        if not plan_info:
            # Не должно происходить, но на всякий случай
            self._show_input_state()
            return
        
        self.title_label.setText("Лицензия активна")
        
        if self.status == LicenseStatus.GRACE_PERIOD:
            self.description_label.setText(
                "⚠️ Не удалось обновить лицензию онлайн. "
                "Убедитесь, что у вас есть подключение к интернету. "
                "Приложение продолжит работать в течение grace period."
            )
        else:
            self.description_label.setText(
                "Ваша подписка активна. Спасибо за использование Signer PRIME!"
            )
        
        # План
        plan_names = {
            "monthly": "Месячная подписка",
            "quarterly": "Подписка на 3 месяца",
            "yearly": "Годовая подписка"
        }
        plan_name = plan_names.get(plan_info["plan"], plan_info["plan"])
        self.plan_label.setText(f"<b>План:</b> {plan_name}")
        
        # Дата окончания
        expiry_ts = plan_info["current_period_end"]
        expiry_date = datetime.fromtimestamp(expiry_ts).strftime("%d.%m.%Y")
        self.expiry_label.setText(f"<b>Действует до:</b> {expiry_date}")
        
        # Ключ лицензии
        license_key = plan_info["license_key"]
        self.license_key_label.setText(f"<b>Ключ:</b> {license_key}")
        
        # Видимость элементов
        self.input_widget.setVisible(False)
        self.info_widget.setVisible(True)
        self.activate_btn.setVisible(False)
        self.close_btn.setVisible(True)
        self.deactivate_btn.setVisible(True)
        self.cancel_btn.setVisible(False)
        self.status_label.setText("")
    
    def _format_license_key(self, text: str):
        """Форматирует ключ лицензии в формате XXXX-XXXX-XXXX-XXXX."""
        # Убираем все нечисловые и не-буквенные символы кроме дефисов
        text = text.upper().replace("-", "")
        
        # Вставляем дефисы каждые 4 символа
        formatted = "-".join([text[i:i+4] for i in range(0, len(text), 4)])
        
        # Обновляем поле без рекурсии
        if formatted != self.key_input.text():
            cursor_pos = self.key_input.cursorPosition()
            self.key_input.blockSignals(True)
            self.key_input.setText(formatted)
            self.key_input.setCursorPosition(min(cursor_pos + 1, len(formatted)))
            self.key_input.blockSignals(False)
    
    def _activate(self):
        """Активировать лицензию."""
        license_key = self.key_input.text().strip()
        
        if not license_key:
            self._show_error("Введите лицензионный ключ")
            return
        
        # Проверка формата ключа
        if not self._validate_key_format(license_key):
            self._show_error("Неверный формат ключа. Ожидается: SGNR-XXXX-XXXX-XXXX-XXXX")
            return
        
        # Блокируем UI
        self.activate_btn.setEnabled(False)
        self.key_input.setEnabled(False)
        self.status_label.setText("Активация...")
        
        # Запускаем воркер
        self.activate_worker = ActivateWorker(self.manager, license_key)
        self.activate_worker.finished.connect(self._on_activate_finished)
        self.activate_worker.start()
    
    def _on_activate_finished(self, success: bool, error_msg: str):
        """Обработка результата активации."""
        self.activate_btn.setEnabled(True)
        self.key_input.setEnabled(True)
        
        if success:
            logger.info("[LicenseDialog] Activation successful")
            self.status = LicenseStatus.VALID
            
            # Показываем информацию о лицензии на 2 секунды
            self._refresh_state()
            
            # Автоматически закрываем диалог после успешной активации
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(2000, self.accept)  # Закрыть через 2 секунды
        else:
            logger.warning(f"[LicenseDialog] Activation failed: {error_msg}")
            self._show_error(error_msg)
    
    def _deactivate(self):
        """Деактивировать это устройство."""
        # Подтверждение
        from PyQt6.QtWidgets import QMessageBox
        
        reply = QMessageBox.question(
            self,
            "Деактивировать устройство",
            "Вы уверены, что хотите деактивировать это устройство?\n\n"
            "Это освободит слот для активации на другом устройстве. "
            "Вы сможете снова активировать это устройство позже.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # Блокируем UI
        self.deactivate_btn.setEnabled(False)
        self.status_label.setText("Деактивация...")
        
        # Запускаем воркер
        self.deactivate_worker = DeactivateWorker(self.manager)
        self.deactivate_worker.finished.connect(self._on_deactivate_finished)
        self.deactivate_worker.start()
    
    def _on_deactivate_finished(self, success: bool, error_msg: str):
        """Обработка результата деактивации."""
        self.deactivate_btn.setEnabled(True)
        
        if success:
            logger.info("[LicenseDialog] Deactivation successful")
            self.status = LicenseStatus.NOT_ACTIVATED
            self._refresh_state()
        else:
            logger.warning(f"[LicenseDialog] Deactivation failed: {error_msg}")
            self._show_error(error_msg)
    
    def _validate_key_format(self, key: str) -> bool:
        """Проверяет формат ключа."""
        # Ожидаем: SGNR-XXXX-XXXX-XXXX-XXXX (20 символов + 4 дефиса = 24)
        parts = key.split("-")
        if len(parts) != 5:
            return False
        
        if parts[0] != "SGNR":
            return False
        
        for part in parts[1:]:
            if len(part) != 4:
                return False
        
        return True
    
    def _show_error(self, message: str):
        """Показывает сообщение об ошибке."""
        self.status_label.setText(f"❌ {message}")
        t = theme_manager.tokens
        self.status_label.setStyleSheet(f"color: {t.get('error', '#f85149')};")
    
    def _open_purchase_url(self):
        """Открывает страницу покупки в браузере."""
        webbrowser.open(PURCHASE_URL)
    
    def _update_theme(self, _=None):
        """Обновляет стили при смене темы."""
        t = theme_manager.tokens
        
        self.setStyleSheet(f"""
            QDialog {{
                background: {t.get('bg_primary', '#0d1117')};
                color: {t['text_primary']};
            }}
            QLabel#DialogTitle {{
                color: {t['text_primary']};
            }}
            QLabel#DescriptionLabel {{
                color: {t['text_secondary']};
            }}
            QLabel#FieldLabel {{
                color: {t['text_primary']};
                font-weight: 600;
            }}
            QLabel#PlanLabel, QLabel#ExpiryLabel, QLabel#LicenseKeyLabel {{
                color: {t['text_primary']};
            }}
            QLabel#StatusLabel {{
                color: {t['text_primary']};
            }}
            QLineEdit {{
                background: {t.get('bg_secondary', '#161b22')};
                color: {t['text_primary']};
                border: 1px solid {t.get('border_default', '#30363d')};
                border-radius: 6px;
                padding: 10px;
                font-size: 14px;
            }}
            QLineEdit:focus {{
                border-color: {t['accent']};
            }}
        """)


# Для тестирования
if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication
    
    logging.basicConfig(level=logging.DEBUG)
    
    app = QApplication(sys.argv)
    
    # Создаём менеджер лицензий
    manager = LicenseManager()
    
    dialog = LicenseDialog(manager)
    result = dialog.exec()
    
    print(f"Dialog result: {result}")
    print(f"License status: {manager.check_local_status()}")
