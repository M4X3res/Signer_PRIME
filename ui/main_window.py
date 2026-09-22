import logging
import os
import cv2
import numpy as np
from licensing.access import online_action
from licensing.license_manager import LicenseStatus

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QStackedWidget, QFrame, QSizePolicy, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap, QImage

from ui.themes.theme_manager import theme_manager
from ui.widgets.sidebar import Sidebar
from ui.widgets.dashboard_page import DashboardPage
from ui.widgets.processing_page import ProcessingPage
from ui.widgets.settings_page import SettingsPage
from ui.widgets.map_page import MapPage
from ui.widgets.error_editor_page import ErrorEditorPage
from configs import config

logger = logging.getLogger(__name__)


class StatusBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("StatusBar")
        self.setMinimumHeight(28)  # Минимальная высота
        self.setMaximumHeight(32)  # Максимальная высота

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(16)

        self._status = QLabel("Готов к работе")
        self._status.setStyleSheet(
            f"color: {theme_manager.tokens['text_tertiary']}; font-size: 11px;"
            "background: transparent;"
        )
        self._status.setWordWrap(False)  # Не переносим статус

        self._dot = QLabel("●")
        self._dot.setStyleSheet(
            f"color: {theme_manager.tokens['text_tertiary']}; font-size: 8px;"
            "background: transparent;"
        )

        self._right = QLabel("Signer v2.0")
        self._right.setStyleSheet(
            f"color: {theme_manager.tokens['text_tertiary']}; font-size: 11px;"
            "background: transparent;"
        )

        layout.addWidget(self._dot)
        layout.addWidget(self._status)
        layout.addStretch()
        layout.addWidget(self._right)

        self._restyle_static()
        theme_manager.theme_changed.connect(self._restyle_static)

    def _restyle_static(self):
        t = theme_manager.tokens
        self._right.setStyleSheet(
            f"color: {t['text_tertiary']}; font-size: 11px; background: transparent;"
        )

    def set_status(self, text: str, color: str = "", duration_ms: int = 0):
        """
        Устанавливает текст статуса.
        
        Args:
            text: Текст статуса
            color: Цвет текста (опционально, по умолчанию text_tertiary)
            duration_ms: Длительность показа в миллисекундах. Если >0, автоматически
                        вернётся к "Готов к работе" через указанное время.
        """
        t = theme_manager.tokens
        c = color or t["text_tertiary"]
        self._status.setText(text)
        self._status.setStyleSheet(
            f"color: {c}; font-size: 11px; background: transparent;"
        )
        self._dot.setStyleSheet(
            f"color: {c}; font-size: 8px; background: transparent;"
        )
        
        # БАГ-3: Поддержка автосброса статуса через duration_ms
        if duration_ms > 0:
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(duration_ms, lambda: self.set_status("Готов к работе"))


class MainWindow(QMainWindow):
    from PyQt6.QtCore import pyqtSignal
    
    # Сигнал эмитится после завершения сохранения результатов (успешного или с ошибкой)
    # Используется для надёжного ожидания завершения сохранения перед закрытием приложения
    results_saved = pyqtSignal()
    
    def     __init__(self):
        super().__init__()
        self.setWindowTitle("Signer v2")
        self.setMinimumSize(1200, 720)
        self.resize(1400, 860)

        # ── Central widget ──────────────────────────────────────
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Sidebar ─────────────────────────────────────────────
        self.sidebar = Sidebar()
        self.sidebar.page_changed.connect(self._switch_page)
        root.addWidget(self.sidebar)

        # ── Right side: stacked pages + status bar ──────────────
        right = QWidget()
        right.setObjectName("ContentArea")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Pages
        self._pages = QStackedWidget()
        self._pages.setObjectName("ContentArea")

        self.page_dashboard   = DashboardPage()
        self.page_processing  = ProcessingPage()
        self.page_map         = MapPage()
        self.page_errors      = ErrorEditorPage()
        # SettingsPage создаётся лениво — license_manager устанавливается в setattr из main.py
        # Временно создаём без license_manager, он будет передан через property setter
        self.page_settings    = SettingsPage()

        self._pages.addWidget(self.page_dashboard)   # index 0
        self._pages.addWidget(self.page_processing)  # index 1
        self._pages.addWidget(self.page_map)          # index 2
        self._pages.addWidget(self.page_errors)       # index 3
        self._pages.addWidget(self.page_settings)     # index 4

        self._page_map = {
            "dashboard":  0,
            "processing": 1,
            "map":        2,
            "errors":     3,
            "settings":   4,
        }

        right_layout.addWidget(self._pages)

        # Thin separator above status bar
        sep = QFrame()
        sep.setObjectName("StatusBarSep")
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {theme_manager.tokens['border_subtle']};")
        right_layout.addWidget(sep)
        theme_manager.theme_changed.connect(
            lambda: sep.setStyleSheet(
                f"background: {theme_manager.tokens['border_subtle']};"
            )
        )

        # Status bar
        self.status_bar = StatusBar()
        right_layout.addWidget(self.status_bar)

        root.addWidget(right)

        # ProcessingController создаётся лениво при первом запуске
        # чтобы не грузить модели при старте UI
        self._controller = None
        self._finish_called = False  # Флаг защиты от двойного вызова _on_finish

        # Редактор ошибок — прыжок к кадру
        self.page_errors.jump_to_frame.connect(self._on_editor_jump)
        
        # ЗАДАЧА 4 (P2): Редактор ошибок — показать на карте
        self.page_errors.show_on_map.connect(self._on_show_sign_on_map)
        
        # Карта — прыжок к секунде
        self.page_map.jump_to_second.connect(self._on_jump_to_second)

        # ── Wire dashboard signals ──────────────────────────────
        self.page_dashboard.start_requested.connect(self._on_start)
        self.page_dashboard.multiple_requested.connect(self._on_multiple)
        self.page_processing.finish_requested.connect(self._on_finish_requested)
        self.page_processing.pause_requested.connect(self._on_pause_requested)
        self.page_processing.resume_requested.connect(self._on_resume_requested)

        # ── Apply theme ─────────────────────────────────────────
        from PyQt6.QtWidgets import QApplication
        theme_manager.apply(QApplication.instance())
    
    @property
    def license_manager(self):
        """Getter для license_manager."""
        return getattr(self, '_license_manager', None)
    
    @license_manager.setter
    def license_manager(self, manager):
        """Setter для license_manager — передаёт его в SettingsPage."""
        self._license_manager = manager
        if hasattr(self, 'page_settings'):
            self.page_settings._license_manager = manager
            # Обновляем отображение лицензии после установки менеджера
            if hasattr(self.page_settings, '_update_license_display'):
                self.page_settings._update_license_display()

    # ── Page switching ─────────────────────────────────────────

    def _switch_page(self, page_id: str):
        idx = self._page_map.get(page_id, 0)
        self._pages.setCurrentIndex(idx)

    def on_license_access_changed(self, status):
        """Lock work immediately on a failed check; keep recovery UI available."""
        # Queued signals can arrive after a newer successful activation. The
        # shared manager, not an outdated signal argument, is the authority.
        valid = self.license_manager.has_online_access()
        was_blocked = getattr(self, "_license_blocked", False)
        self._license_blocked = not valid
        self.page_settings._update_license_display()
        self._pages.setEnabled(True)
        self.sidebar.setEnabled(True)
        for index in range(self._pages.count()):
            page = self._pages.widget(index)
            page.setEnabled(valid or page is self.page_settings)
        if valid:
            dialog = getattr(self, '_license_access_dialog', None)
            if dialog:
                dialog.close()
            self._license_access_dialog = None
            if was_blocked:
                self.status_bar.set_status('Лицензия подтверждена. Готов к работе')
            return
        controller = getattr(self, '_controller', None)
        if controller and controller.is_running:
            self._license_interrupted = True
            controller.finish_and_save()
        self.status_bar.set_status('Работа заблокирована: требуется онлайн-проверка лицензии', theme_manager.tokens['warning'])
        self._switch_page('settings')
        if getattr(self, '_license_access_dialog', None):
            return
        dialog = QMessageBox(self)
        self._license_access_dialog = dialog
        dialog.setWindowTitle('Требуется проверка лицензии')
        dialog.setText('Связь с сервером не подтверждена или лицензия недействительна.\n'
                       'Обработка останавливается с сохранением прогресса.\n'
                       'Повторите проверку или закройте это сообщение и обновите лицензию в настройках.')
        dialog.setStandardButtons(QMessageBox.StandardButton.Retry | QMessageBox.StandardButton.Close)
        def respond(button):
            self._license_access_dialog = None
            if dialog.standardButton(button) == QMessageBox.StandardButton.Retry:
                if self.license_manager._access_status in (LicenseStatus.NOT_ACTIVATED, LicenseStatus.EXPIRED, LicenseStatus.REVOKED):
                    from ui.widgets.license_dialog import LicenseDialog
                    LicenseDialog(self.license_manager).exec()
                self.license_manager.verify_access_async(lambda status, error: None)
        dialog.buttonClicked.connect(respond)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.show()

    # ── Processing wiring (to be connected to ButtonsHandler) ──

    @online_action
    def _on_start(self):
        """Вызывается когда пользователь нажимает 'Начать обработку'."""
        if getattr(self, '_saving_results', False) or (self._controller and self._controller.is_running):
            return
        
        logger.info("Запуск обработки...")
        
        # Сбрасываем флаги при старте новой обработки
        self._finish_requested_called = False
        self._finish_called = False
        
        # Создаём контроллер лениво
        self._ensure_controller()
        
        # Проверяем наличие checkpoint
        if self._controller.has_checkpoint():
            from PyQt6.QtWidgets import QMessageBox
            
            reply = QMessageBox.question(
                self,
                "Восстановление прогресса",
                "Найден сохранённый прогресс обработки.\n\n"
                "Хотите продолжить с места остановки?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )

            if not self.license_manager.has_online_access():
                self.on_license_access_changed(LicenseStatus.NETWORK_ERROR)
                return
            
            if reply == QMessageBox.StandardButton.Yes:
                if self._controller.load_checkpoint():
                    self.page_processing.log("Прогресс восстановлен из checkpoint", "success")
                else:
                    self.page_processing.log("Не удалось загрузить checkpoint", "error")
            else:
                # Удаляем checkpoint и начинаем заново
                self._controller.delete_checkpoint()
                self.page_processing.log("Checkpoint удалён, начинаем заново", "info")
        
        self._switch_page("processing")
        self.sidebar.set_page("processing")
        self.page_processing.set_active(True)
        self.page_dashboard.set_processing_active(True)
        t = theme_manager.tokens
        self.status_bar.set_status("Обработка запущена…", t["accent"])
        self.page_processing.log("Загрузка моделей…", "info")

        self._controller.start()

        # Запускаем сервер карты
        self.page_map.start_server()
        
        # Уведомляем сервер о начале обработки
        try:
            from server.map_server import set_processing_state
            set_processing_state(True)
        except Exception as e:
            self.page_processing.log(f"Предупреждение: {e}", "warn")

    @online_action
    def _on_multiple(self):
        """Массовая обработка."""
        if getattr(self, '_saving_results', False) or (self._controller and self._controller.is_running):
            return
        
        # Сбрасываем флаги при старте новой обработки
        self._finish_requested_called = False
        self._finish_called = False
        
        self._switch_page("processing")
        self.sidebar.set_page("processing")
        self.page_processing.set_active(True)
        self.page_dashboard.set_processing_active(True)
        t = theme_manager.tokens
        self.status_bar.set_status("Массовая обработка…", t["accent"])
        self.page_processing.log("Загрузка моделей…", "info")
        self._ensure_controller()
        self._controller.start()
        self.page_map.start_server()
        
        # Уведомляем сервер о начале обработки
        try:
            from server.map_server import set_processing_state
            set_processing_state(True)
        except Exception as e:
            self.page_processing.log(f"Предупреждение: {e}", "warn")

    def _on_jump_to_second(self, seconds: int):
        """
        Task C: Карта просит прыгнуть к секунде через кнопку '⏩ К кадру'.
        
        Основной механизм показа видео по знаку реализован в map.html::loadVideoForSign()
        — видео проигрывается прямо в панели карты.
        
        Этот обработчик дополнительно показывает кадр на странице обработки PyQt.
        """
        config.SECONDS_ALL_VIDEO = seconds
        
        # Если обработка идёт — обновляем позицию в реальном времени
        if self._controller and self._controller.is_running:
            self.page_map.update_position(seconds)
            return
        
        # Если обработка не идёт — загружаем и показываем кадр
        try:
            from core.video_index import resolve_video_and_frame
            
            # Предполагаем FPS = 60 (можно улучшить, получив реальный FPS из метаданных)
            fps = config.VIDEO_FPS if hasattr(config, 'VIDEO_FPS') else 60.0
            abs_frame = int(seconds * fps)
            
            # Task C: Используем resolve_video_and_frame для корректного определения видео
            video_idx, frame_num = resolve_video_and_frame(abs_frame)
            
            # Переключаемся на страницу обработки
            self._switch_page("processing")
            self.sidebar.set_page("processing")
            
            # Загружаем и показываем кадр
            success = self._load_and_show_frame(video_idx, frame_num)
            
            if success:
                self.page_processing.log(
                    f"Переход к секунде {seconds} (видео {video_idx + 1}, кадр {frame_num})", "success"
                )
            else:
                self.page_processing.log(
                    f"Не удалось загрузить кадр для секунды {seconds}", "error"
                )
        except Exception as e:
            logger.error(f"[MainWindow] Ошибка в _on_jump_to_second: {e}", exc_info=True)
            self.page_processing.log(f"Ошибка перехода: {e}", "error")
            self.page_map.update_position(seconds)

    def _on_finish(self):
        """Завершение обработки."""
        if self._finish_called:
            return
        if getattr(self, '_license_blocked', False) or getattr(self, '_license_interrupted', False):
            self._controller.save_checkpoint(force=True)
            self._license_interrupted = False
            self.page_processing.set_active(False)
            self.page_dashboard.set_processing_active(False)
            self._saving_results = False
            return
        self._finish_called = True
        self._saving_results = True
        self.page_processing.set_active(False)
        self.page_dashboard.set_processing_active(True)
        
        print("[MainWindow] Начинаем сохранение результатов...")
        
        # Сохраняем результаты в GeoJSON
        try:
            # Детектор завершён: фиксируем и последние знаки до чтения очереди.
            self._controller.save_checkpoint(force=True)
            self._save_results()
        except Exception as e:
            import traceback
            print(f"[MainWindow] КРИТИЧЕСКАЯ ОШИБКА в _save_results:")
            print(traceback.format_exc())
            self._on_save_error(str(e))

    # ── Public API for PlayerHandler integration ────────────────

    def update_frame(self, pixmap: QPixmap):
        self.page_processing.set_frame(pixmap)

    def update_progress(self, value: int, eta: str = ""):
        self.page_processing.set_progress(value, eta)

    def update_stats(self, frames: int, signs: int, fps: float,
                     video_idx: int, video_total: int):
        self.page_processing.set_stats(frames, signs, fps, video_idx, video_total)

    def log(self, msg: str, level: str = "info"):
        self.page_processing.log(msg, level)

    def set_status(self, text: str, color: str = ""):
        self.status_bar.set_status(text, color)

    # ── ProcessingController callbacks ─────────────────────────

    def _on_finish_requested(self):
        """Кнопка 'Завершить' — мягкая остановка. Сохранение произойдёт
        когда DetectorThread завершит обработку очереди (_on_finish)."""
        
        # Защита от повторного вызова
        if hasattr(self, '_finish_requested_called') and self._finish_requested_called:
            print("[MainWindow] _on_finish_requested уже был вызван, игнорируем")
            return
        
        self._finish_requested_called = True
        
        self.page_processing.log("Завершение обработки…", "info")
        
        if self._controller:
            self._controller.finish_and_save()
        # _save_results() вызывается из _on_finish() после сигнала finished
        
        # Уведомляем сервер
        try:
            from server.map_server import set_processing_state
            set_processing_state(False)
        except Exception:
            pass
    
    def _on_pause_requested(self):
        """Пауза обработки."""
        if self._controller:
            self._controller.pause()
            self.page_processing.log("Обработка приостановлена", "warn")
            t = theme_manager.tokens
            self.status_bar.set_status("Обработка приостановлена", t["warning"])
    
    @online_action
    def _on_resume_requested(self):
        """Возобновление обработки."""
        if self._controller:
            self._controller.resume()
            self.page_processing.log("Обработка возобновлена", "info")
            t = theme_manager.tokens
            self.status_bar.set_status("Обработка возобновлена…", t["accent"])

    def _on_progress(self, abs_frame: int, total: int):
        pct = int(abs_frame / total * 100) if total else 0
        self.page_processing.set_progress(pct)
        self.page_processing.set_frame_info(abs_frame, total)

    def _on_stats(self, frames: int, signs: int, fps: float):
        total_videos = len(config.VIDEOS) if config.VIDEOS else 1
        self.page_processing.set_stats(
            frames, signs, fps,
            config.INDEX_OF_VIDEO + 1, total_videos,
        )

    def _on_video_switched(self, idx: int, name: str):
        t = theme_manager.tokens
        self.status_bar.set_status(f"Видео {idx + 1}: {name}", t["accent"])
        self.page_processing.log(f"Переключение на {name}", "info")

    def _on_sign_found(self, sign_type: str, video: str, conf: float):
        self.page_processing.log(
            f"Знак {sign_type} — {video}", "info"
        )

    @online_action
    def _save_results(self):
        """Финальное сохранение GeoJSON через FinalHandler."""
        print("[MainWindow] _save_results вызван")
        
        # Отключаем кнопки чтобы предотвратить повторные нажатия
        self.page_processing.set_active(False)
        self.page_processing.log("Сохранение результатов...", "info")
        
        try:
            from core.final_handler import FinalHandler
            signs = self._controller.get_result_signs()
            turns = self._controller.get_turn_data()
            print(f"[MainWindow] Получено из контроллера: {len(signs)} знаков, {len(turns)} поворотов")
            
            # BLOCK SIGN-LOSS-4: сохраняем входное количество для сравнения
            self._last_input_sign_count = len(signs)
            
            if len(signs) == 0:
                self.page_processing.log("Предупреждение: знаки не обнаружены", "warn")
            
            # Запускаем сохранение в отдельном потоке чтобы не блокировать UI
            from PyQt6.QtCore import QThread, pyqtSignal
            
            class SaveThread(QThread):
                finished_ok = pyqtSignal(int)  # количество знаков
                progress = pyqtSignal(int, int, str)  # текущий, всего, сообщение
                error = pyqtSignal(str)
                
                def __init__(self, signs, turns, parent=None):
                    super().__init__(parent)
                    self.signs = signs
                    self.turns = turns
                
                def run(self):
                    try:
                        handler = FinalHandler()
                        # BLOCK SIGN-LOSS-4: используем возвращённое значение — реальное число записанных features
                        saved_count = handler.save_result(
                            self.signs, 
                            self.turns, 
                            progress_cb=self.progress.emit
                        )
                        self.finished_ok.emit(saved_count)
                    except Exception as e:
                        import traceback
                        self.error.emit(f"{e}\n{traceback.format_exc()}")
            
            self._save_thread = SaveThread(signs, turns, self)
            self._save_thread.finished_ok.connect(self._on_save_finished)
            self._save_thread.progress.connect(self._on_save_progress)
            self._save_thread.error.connect(self._on_save_error)
            self._save_thread.start()
            
            # Показываем начальный статус
            self.page_processing.log("Сохранение результатов...", "info")
            t = theme_manager.tokens
            self.status_bar.set_status("Сохранение GeoJSON...", t["info"])
            
        except Exception as e:
            import traceback
            print(f"[MainWindow] ОШИБКА создания потока сохранения:")
            print(traceback.format_exc())
            self._on_save_error(str(e))
    
    def _on_save_progress(self, current: int, total: int, message: str):
        """Обработчик прогресса сохранения."""
        # Обновляем статус-бар и лог
        if total > 0:
            percent = int((current / total) * 100)
            self.page_processing.log(f"{message} ({percent}%)", "info")
            t = theme_manager.tokens
            self.status_bar.set_status(f"{message} {current}/{total}", t["info"])
    
    def _on_save_finished(self, sign_count: int):
        """Вызывается когда сохранение завершено успешно."""
        if self._controller:
            self._controller.delete_checkpoint()
        self._saving_results = False
        self.page_dashboard.set_processing_active(False)
        self.page_processing.set_progress(100)
        print(f"[MainWindow] Сохранение завершено: {sign_count} знаков")
        t = theme_manager.tokens
        
        # BLOCK SIGN-LOSS-4: предупреждение если реально сохранено заметно меньше чем было на входе
        input_count = getattr(self, "_last_input_sign_count", sign_count)
        if input_count > 0 and sign_count < input_count * 0.5:
            self.status_bar.set_status(
                f"Сохранено только {sign_count} из {input_count} знаков — см. лог", t["warning"]
            )
            self.page_processing.log(
                f"⚠️ В файл попало заметно меньше знаков, чем было найдено "
                f"({sign_count} из {input_count}). Проверьте roadscan.log.", "warn"
            )
        else:
            self.status_bar.set_status("GeoJSON сохранён", t["success"])
            self.page_processing.log(
                f"Сохранено {sign_count} знаков в GeoJSON", "success"
            )
        
        # Уведомляем карту о завершении обработки
        try:
            from server.map_server import emit_processing_finished
            emit_processing_finished(sign_count)
            print(f"[MainWindow] Отправлен сигнал processing_finished с count={sign_count}")
        except Exception as e:
            print(f"[MainWindow] Не удалось отправить processing_finished: {e}")
        
        # Перезагружаем редактор через небольшую задержку
        try:
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(500, self._reload_editor_after_save)
            self.page_processing.log("Обновление редактора запланировано", "info")
        except Exception as e:
            print(f"[MainWindow] Предупреждение при планировании обновления редактора: {e}")
        
        self.page_processing.log("Карта будет обновлена автоматически", "info")
        self.page_processing.log("Для просмотра результатов перейдите на вкладку 'Карта' или 'Редактор'", "info")
        
        # Эмитим сигнал о завершении сохранения (для ожидания в main.py при истечении лицензии)
        self.results_saved.emit()
        from licensing.access import get_manager
        manager = get_manager()
        if manager is not None:
            manager.verify_access_async(lambda status, error: None)
    
    def _on_save_error(self, error_msg: str):
        """Вызывается при ошибке сохранения."""
        self._saving_results = False
        self.page_dashboard.set_processing_active(False)
        print(f"[MainWindow] ОШИБКА сохранения:")
        print(error_msg)
        self.page_processing.log(f"Ошибка сохранения", "error")
        t = theme_manager.tokens
        self.status_bar.set_status("Ошибка сохранения", t["error"])
        
        # Эмитим сигнал о завершении попытки сохранения (даже при ошибке)
        self.results_saved.emit()
    
    def _reload_editor_after_save(self):
        """Перезагружает редактор после сохранения GeoJSON."""
        try:
            print("[MainWindow] Перезагрузка редактора...")
            self.page_errors.reload()
            print("[MainWindow] Редактор перезагружен успешно")
        except Exception as e:
            print(f"[MainWindow] Ошибка при перезагрузке редактора: {e}")
            import traceback
            traceback.print_exc()
    
    def _reload_map_after_processing(self):
        """Перезагружает карту после завершения обработки."""
        try:
            if self.page_map._webview and self.page_map._server_ready:
                self.page_map._reload_map()
                self.page_processing.log("Карта обновлена — данные доступны", "success")
                # Уведомляем сервер о доступности данных
                from server.map_server import notify_data_ready
                notify_data_ready()
            else:
                self.page_processing.log("Запуск сервера карты для отображения результатов…", "info")
                self.page_map.start_server()
                QTimer.singleShot(2000, lambda: self.page_map._reload_map() if self.page_map._webview else None)
        except Exception as e:
            self.page_processing.log(f"Ошибка обновления карты: {e}", "warn")

    def _on_editor_jump(self, video_idx: int, frame_num: int):
        """
        Редактор ошибок просит перейти к кадру через кнопку '⏩ К кадру'.
        Загружает и показывает кадр на странице обработки.
        """
        self._switch_page("processing")
        self.sidebar.set_page("processing")
        
        # Загружаем и показываем кадр
        success = self._load_and_show_frame(video_idx, frame_num)
        
        if success:
            self.page_processing.log(
                f"Переход к видео {video_idx + 1}, кадр {frame_num}", "success"
            )
        else:
            self.page_processing.log(
                f"Не удалось загрузить кадр: видео {video_idx + 1}, кадр {frame_num}", "error"
            )
    
    def _on_show_sign_on_map(self, sign_id: str) -> None:
        """
        ЗАДАЧА 4 (P2): Переключает на вкладку "Карта" и просит веб-страницу карты 
        выбрать и отцентрировать конкретный знак по его id.
        """
        self._switch_page("map")
        self.sidebar.set_page("map")
        
        # Если сервер карты ещё не запущен — запускаем его
        if not self.page_map._server_ready:
            self.page_map.start_server()
        
        # Передаём sign_id в MapPage для фокусировки
        self.page_map.focus_sign(sign_id)

    def _load_and_show_frame(self, video_idx: int, frame_num: int) -> bool:
        """
        Загружает конкретный кадр из видео и отображает его на странице обработки.
        
        Args:
            video_idx: индекс видеофайла
            frame_num: номер кадра в видеофайле
            
        Returns:
            True если кадр успешно загружен и отображён, иначе False
        """
        try:
            # Проверяем доступность данных
            if not config.PATH_TO_VIDEO or not config.VIDEOS:
                logger.error("[MainWindow] PATH_TO_VIDEO или VIDEOS не установлены")
                return False
            
            if video_idx >= len(config.VIDEOS):
                logger.error(f"[MainWindow] video_idx {video_idx} >= len(VIDEOS) {len(config.VIDEOS)}")
                return False
            
            video_path = os.path.join(config.PATH_TO_VIDEO, config.VIDEOS[video_idx])
            
            if not os.path.exists(video_path):
                logger.error(f"[MainWindow] Видеофайл не найден: {video_path}")
                return False
            
            # Открываем видео
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                logger.error(f"[MainWindow] Не удалось открыть видео: {video_path}")
                cap.release()
                return False
            
            # Получаем общее количество кадров перед чтением
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames <= 0:
                total_frames = config.FRAMES_PER_VIDEO
            
            # Перематываем на нужный кадр
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            ret, frame = cap.read()
            cap.release()
            
            if not ret or frame is None:
                logger.error(f"[MainWindow] Не удалось прочитать кадр {frame_num}")
                return False
            
            # Конвертируем BGR -> RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Создаём QImage и QPixmap
            h, w, ch = frame_rgb.shape
            bytes_per_line = ch * w
            qimage = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(qimage)
            
            # Отображаем на странице обработки
            self.page_processing.set_frame(pixmap)
            
            # Обновляем информацию о кадре
            self.page_processing.set_frame_info(frame_num, total_frames)
            
            logger.info(f"[MainWindow] Кадр загружен: видео {video_idx}, кадр {frame_num}")
            return True
            
        except Exception as e:
            logger.error(f"[MainWindow] Ошибка загрузки кадра: {e}", exc_info=True)
            return False

    def _ensure_controller(self) -> None:
        """Создаёт ProcessingController при первом запуске."""
        if self._controller is not None:
            return
        from processing.processing_controller import ProcessingController
        self._controller = ProcessingController(self)
        self._controller.frame_ready.connect(self.page_processing.set_frame)
        self._controller.progress.connect(self._on_progress)
        self._controller.stats.connect(self._on_stats)
        self._controller.video_switched.connect(self._on_video_switched)
        self._controller.sign_found.connect(self._on_sign_found)
        self._controller.finished.connect(self._on_finish)
        self._controller.error.connect(
            lambda msg: self.page_processing.log(msg, "error")
        )
    
    def closeEvent(self, event):
        """Обработка закрытия окна — очистка ресурсов."""
        if getattr(self, '_license_interrupted', False) and self._controller and self._controller.is_running:
            self.page_processing.log('Сохраняется прогресс остановленной обработки. Закройте окно после завершения.', 'info')
            event.ignore()
            return
        manager = getattr(self, 'license_manager', None)
        if manager and manager._verify_workers:
            event.ignore()
            QTimer.singleShot(200, self.close)
            return
        if getattr(self, '_saving_results', False):
            self.page_processing.log("Дождитесь завершения сохранения результатов", "info")
            event.ignore()
            if getattr(self, '_closing_processing', False):
                QTimer.singleShot(200, self.close)
            return
        controller = self._controller
        if controller:
            workers = [getattr(controller, name, None) for name in
                       ('_reader', '_detector', '_detector_pool')]
            if controller.is_running or any(worker and worker.isRunning() for worker in workers):
                if not getattr(self, '_closing_processing', False):
                    self._closing_processing = True
                    controller.finish_and_save()
                event.ignore()
                QTimer.singleShot(200, self.close)
                return
        try:
            # Очищаем ресурсы редактора
            self.page_errors.cleanup()
            
            # Останавливаем сервер карты
            if hasattr(self.page_map, 'stop_server'):
                self.page_map.stop_server()
            
            print("[MainWindow] Очистка завершена")
        except Exception as e:
            print(f"[MainWindow] Ошибка при закрытии: {e}")
            import traceback
            traceback.print_exc()
        finally:
            event.accept()
