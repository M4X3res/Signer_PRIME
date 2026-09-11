"""
ui/widgets/update_dialog.py
Диалог обновления Signer PRIME со стилизацией по образцу settings_page.py.
Два состояния: предложение обновиться + прогресс загрузки.
"""
import logging
import os
import time
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QPlainTextEdit, QProgressBar, QWidget
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from ui.themes.theme_manager import theme_manager
from ui.widgets.update_worker import UpdateDownloadWorker
from updater import updater

logger = logging.getLogger(__name__)


def _format_size(bytes_size: int) -> str:
    """Форматирует размер в человекочитаемый вид."""
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} TB"


def _format_time(seconds: float) -> str:
    """Форматирует время в MM:SS."""
    if seconds < 0 or seconds > 86400:  # больше суток - не показываем
        return "--:--"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}:{secs:02d}"


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


class UpdateDialog(QDialog):
    """
    Диалог обновления с двумя состояниями:
    1. Предложение обновиться (release notes, размер)
    2. Прогресс загрузки и применения
    """
    
    update_applied = pyqtSignal()  # Сигнал для запуска Updater и закрытия приложения
    
    def __init__(self, update_info: updater.UpdateInfo, parent=None):
        super().__init__(parent)
        self.update_info = update_info
        self.download_worker = None
        self.temp_dir = Path(os.environ.get("LOCALAPPDATA", ".")) / "Signer" / "UpdateTemp"
        
        # Накопители для расчёта оставшегося времени и прогресса
        self._speed_samples = []
        self._file_progress = {}  # {filename: bytes_downloaded}
        self._start_time = 0
        
        self.setWindowTitle("Доступно обновление")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        
        self._setup_ui()
        self._show_offer_state()
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
        
        # ── Версионная информация ──
        self.version_label = QLabel()
        self.version_label.setObjectName("VersionLabel")
        layout.addWidget(self.version_label)
        
        # ── Release notes (только в состоянии предложения) ──
        self.notes_widget = QWidget()
        notes_layout = QVBoxLayout(self.notes_widget)
        notes_layout.setContentsMargins(0, 0, 0, 0)
        notes_layout.setSpacing(8)
        
        notes_title = QLabel("Что нового:")
        notes_title.setObjectName("SectionTitle")
        notes_layout.addWidget(notes_title)
        
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setReadOnly(True)
        self.notes_edit.setMaximumHeight(200)
        notes_layout.addWidget(self.notes_edit)
        
        layout.addWidget(self.notes_widget)
        
        # ── Размер загрузки ──
        self.size_label = QLabel()
        self.size_label.setObjectName("SizeLabel")
        layout.addWidget(self.size_label)
        
        # ── Прогресс (только в состоянии загрузки) ──
        self.progress_widget = QWidget()
        progress_layout = QVBoxLayout(self.progress_widget)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(8)
        
        self.progress_file_label = QLabel()
        progress_layout.addWidget(self.progress_file_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setTextVisible(True)
        progress_layout.addWidget(self.progress_bar)
        
        self.progress_stats_label = QLabel()
        progress_layout.addWidget(self.progress_stats_label)
        
        self.progress_time_label = QLabel()
        progress_layout.addWidget(self.progress_time_label)
        
        layout.addWidget(self.progress_widget)
        
        # ── Статусное сообщение ──
        self.status_label = QLabel()
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        
        # ── Кнопки ──
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.addStretch()
        
        self.later_btn = BtnSecondary("Позже")
        self.later_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.later_btn)
        
        self.update_btn = BtnPrimary("Обновить")
        self.update_btn.clicked.connect(self._start_download)
        btn_layout.addWidget(self.update_btn)
        
        layout.addLayout(btn_layout)
    
    def _show_offer_state(self):
        """Показывает состояние предложения обновиться."""
        from app.version import APP_VERSION
        
        self.title_label.setText("Доступно обновление Signer")
        self.version_label.setText(
            f"Текущая версия: <b>{APP_VERSION}</b> → Новая версия: <b>{self.update_info.version}</b>"
        )
        self.notes_edit.setPlainText(self.update_info.release_notes)
        
        # Определяем тип обновления
        if self.update_info.is_delta:
            update_type_text = "Быстрое обновление"
        else:
            update_type_text = "Полное обновление"
        
        self.size_label.setText(
            f"{update_type_text}: {_format_size(self.update_info.total_size_bytes)}"
        )
        self.status_label.setText("")
        
        # Видимость элементов
        self.notes_widget.setVisible(True)
        self.size_label.setVisible(True)
        self.progress_widget.setVisible(False)
        self.update_btn.setVisible(True)
        self.update_btn.setEnabled(True)
        self.later_btn.setVisible(True)
    
    def _show_progress_state(self):
        """Показывает состояние загрузки."""
        self.title_label.setText("Загрузка обновления")
        self.version_label.setText(f"Версия {self.update_info.version}")
        self.status_label.setText("")
        
        # Видимость элементов
        self.notes_widget.setVisible(False)
        self.size_label.setVisible(False)
        self.progress_widget.setVisible(True)
        self.update_btn.setVisible(False)
        self.later_btn.setText("Отменить")  # Меняем текст на "Отменить"
        self.later_btn.setEnabled(True)  # Разрешаем отмену во время загрузки
        
        self.progress_bar.setValue(0)
        self.progress_file_label.setText("Подготовка...")
        self.progress_stats_label.setText("")
        self.progress_time_label.setText("")
    
    def _show_error_state(self, error_msg: str):
        """Показывает состояние ошибки."""
        self.title_label.setText("Ошибка обновления")
        self.status_label.setText(f"❌ {error_msg}")
        t = theme_manager.tokens
        self.status_label.setStyleSheet(f"color: {t.get('error', '#f85149')};")
        
        self.progress_widget.setVisible(False)
        self.update_btn.setText("Повторить")
        self.update_btn.setVisible(True)
        self.update_btn.setEnabled(True)
        self.later_btn.setText("Позже")  # Возвращаем текст "Позже"
        self.later_btn.setEnabled(True)
        
        # Восстанавливаем соединение для кнопки "Позже"
        try:
            self.later_btn.clicked.disconnect()
        except:
            pass
        self.later_btn.clicked.connect(self.reject)
    
    def _start_download(self):
        """Начинает загрузку обновления."""
        logger.info("[UpdateDialog] Начало загрузки обновления...")
        
        # Очищаем временную папку
        import shutil
        if self.temp_dir.exists():
            try:
                shutil.rmtree(self.temp_dir)
            except Exception as e:
                logger.warning(f"Не удалось очистить {self.temp_dir}: {e}")
        
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        self._show_progress_state()
        self._start_time = time.time()
        self._file_progress = {}
        self._speed_samples = []
        
        # Запускаем воркер
        self.download_worker = UpdateDownloadWorker(self.update_info, self.temp_dir)
        self.download_worker.progress.connect(self._on_download_progress)
        self.download_worker.finished_ok.connect(self._on_download_finished)
        self.download_worker.checksum_failed.connect(self._on_checksum_failed)
        self.download_worker.error.connect(self._on_download_error)
        self.download_worker.cancelled.connect(self._on_download_cancelled)
        self.download_worker.start()
        
        # Подключаем кнопку "Отменить" к методу отмены
        self.later_btn.clicked.disconnect()  # Отключаем старое действие
        self.later_btn.clicked.connect(self._cancel_download)
    
    def _cancel_download(self):
        """Отменяет загрузку."""
        if self.download_worker and self.download_worker.isRunning():
            logger.info("[UpdateDialog] Пользователь нажал Отменить")
            self.download_worker.cancel()
            self.later_btn.setEnabled(False)
            self.status_label.setText("Отмена загрузки...")
    
    def _on_download_cancelled(self):
        """Обработка отмены загрузки."""
        logger.info("[UpdateDialog] Загрузка отменена")
        
        # Очищаем временную папку
        import shutil
        if self.temp_dir.exists():
            try:
                shutil.rmtree(self.temp_dir)
            except Exception as e:
                logger.warning(f"Не удалось очистить {self.temp_dir}: {e}")
        
        # Закрываем диалог
        self.reject()
    
    def _on_download_progress(self, filename: str, downloaded: int, total: int, speed_bps: float):
        """Обновляет прогресс загрузки."""
        # Обновляем прогресс для текущего файла
        self._file_progress[filename] = downloaded
        
        # Вычисляем общий прогресс
        total_downloaded = sum(self._file_progress.values())
        
        # Прогресс-бар (процент от общего размера)
        overall_percent = int((total_downloaded / self.update_info.total_size_bytes) * 100)
        self.progress_bar.setValue(min(overall_percent, 100))
        
        # Имя файла
        self.progress_file_label.setText(f"Скачивание: {filename}")
        
        # Статистика (размер)
        downloaded_str = _format_size(total_downloaded)
        total_str = _format_size(self.update_info.total_size_bytes)
        self.progress_stats_label.setText(f"{downloaded_str} / {total_str}")
        
        # Скорость и оставшееся время
        if speed_bps > 0:
            # Усредняем скорость по последним N замерам
            self._speed_samples.append(speed_bps)
            if len(self._speed_samples) > 10:
                self._speed_samples.pop(0)
            
            avg_speed = sum(self._speed_samples) / len(self._speed_samples)
            speed_str = _format_size(avg_speed) + "/s"
            
            # Оставшееся время
            remaining_bytes = self.update_info.total_size_bytes - total_downloaded
            remaining_seconds = remaining_bytes / avg_speed if avg_speed > 0 else 0
            time_str = _format_time(remaining_seconds)
            
            self.progress_time_label.setText(f"Скорость: {speed_str} | Осталось: {time_str}")
    
    def _on_download_finished(self):
        """Обработка успешного завершения загрузки."""
        logger.info("[UpdateDialog] Загрузка завершена, применение обновления...")
        
        self.status_label.setText("Применение обновления...")
        self.progress_bar.setValue(100)
        
        # Сигнал для main window для запуска Updater.exe
        self.update_applied.emit()
        
        # Закрываем диалог
        self.accept()
    
    def _on_checksum_failed(self):
        """Обработка ошибки проверки чексумм."""
        logger.error("[UpdateDialog] Проверка целостности провалена")
        self._show_error_state("Проверка целостности провалена. Файлы повреждены.")
    
    def _on_download_error(self, error_msg: str):
        """Обработка ошибки загрузки."""
        logger.error(f"[UpdateDialog] Ошибка загрузки: {error_msg}")
        self._show_error_state(error_msg)
    
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
            QLabel#VersionLabel {{
                color: {t['text_secondary']};
            }}
            QLabel#SectionTitle {{
                color: {t['text_primary']};
                font-weight: 600;
            }}
            QLabel#SizeLabel {{
                color: {t['text_secondary']};
            }}
            QLabel#StatusLabel {{
                color: {t['text_primary']};
            }}
            QPlainTextEdit {{
                background: {t.get('bg_secondary', '#161b22')};
                color: {t['text_primary']};
                border: 1px solid {t.get('border_default', '#30363d')};
                border-radius: 6px;
                padding: 8px;
            }}
            QProgressBar {{
                background: {t.get('bg_secondary', '#161b22')};
                border: 1px solid {t.get('border_default', '#30363d')};
                border-radius: 6px;
                text-align: center;
                color: {t['text_primary']};
            }}
            QProgressBar::chunk {{
                background: {t['accent']};
                border-radius: 5px;
            }}
        """)


# Для тестирования
if __name__ == "__main__":
    import sys
    import os
    from PyQt6.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    
    # Мок UpdateInfo
    mock_info = updater.UpdateInfo(
        version="2.1.0",
        release_notes="• Новая функция A\n• Исправлен баг B\n• Улучшена производительность C",
        assets=[
            ("Signer.7z.001", "https://example.com/file1", 100 * 1024 * 1024),
            ("Signer.7z.002", "https://example.com/file2", 150 * 1024 * 1024),
            ("checksum.sha256", "https://example.com/checksum", 1024),
        ],
        total_size_bytes=251 * 1024 * 1024
    )
    
    dialog = UpdateDialog(mock_info)
    dialog.exec()
