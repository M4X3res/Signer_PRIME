import logging
import os
import cv2
import numpy as np

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

    def set_status(self, text: str, color: str = ""):
        t = theme_manager.tokens
        c = color or t["text_tertiary"]
        self._status.setText(text)
        self._status.setStyleSheet(
            f"color: {c}; font-size: 11px; background: transparent;"
        )
        self._dot.setStyleSheet(
            f"color: {c}; font-size: 8px; background: transparent;"
        )


class MainWindow(QMainWindow):
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

    # ── Page switching ─────────────────────────────────────────

    def _switch_page(self, page_id: str):
        idx = self._page_map.get(page_id, 0)
        self._pages.setCurrentIndex(idx)

    # ── Processing wiring (to be connected to ButtonsHandler) ──

    def _on_start(self):
        """Вызывается когда пользователь нажимает 'Начать обработку'."""
        
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

    def _on_multiple(self):
        """Массовая обработка."""
        
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
        # Защита от двойного вызова
        if not self._controller or not self._controller.is_running:
            if hasattr(self, '_finish_called') and self._finish_called:
                print("[MainWindow] _on_finish уже был вызван, пропускаем")
                return
        
        self._finish_called = True
        
        self.page_processing.set_active(False)
        self.page_dashboard.set_processing_active(False)
        
        print("[MainWindow] Начинаем сохранение результатов...")
        
        # Сохраняем результаты в GeoJSON
        try:
            self._save_results()
        except Exception as e:
            import traceback
            print(f"[MainWindow] КРИТИЧЕСКАЯ ОШИБКА в _save_results:")
            print(traceback.format_exc())
            self.page_processing.log(f"Критическая ошибка: {e}", "error")
        
        # Удаляем checkpoint после успешного завершения
        if self._controller:
            try:
                self._controller.delete_checkpoint()
                self.page_processing.log("Checkpoint очищен", "info")
            except Exception as e:
                print(f"[MainWindow] Ошибка удаления checkpoint: {e}")
        
        t = theme_manager.tokens
        self.status_bar.set_status("Обработка завершена", t["success"])
        self.page_processing.log("Обработка завершена — результат сохранён в GeoJSON", "success")
        self.page_processing.set_progress(100)
        
        # Уведомляем карту о завершении
        try:
            from server.map_server import emit_processing_finished
            emit_processing_finished()
        except Exception as e:
            self.page_processing.log(f"Предупреждение: не удалось уведомить карту: {e}", "warn")
        
        # Сбрасываем флаги для следующей обработки
        self._finish_called = False
        self._finish_requested_called = False

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
            self.page_processing.log(f"Ошибка: {e}", "error")
            t = theme_manager.tokens
            self.status_bar.set_status(f"Ошибка: {e}", t["error"])
    
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
    
    def _on_save_error(self, error_msg: str):
        """Вызывается при ошибке сохранения."""
        print(f"[MainWindow] ОШИБКА сохранения:")
        print(error_msg)
        self.page_processing.log(f"Ошибка сохранения", "error")
        t = theme_manager.tokens
        self.status_bar.set_status("Ошибка сохранения", t["error"])
    
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
        try:
            print("[MainWindow] Закрытие приложения...")
            
            # Останавливаем обработку если она идёт
            if self._controller and self._controller.is_running:
                print("[MainWindow] Остановка обработки...")
                self._controller.stop()
                
                # Ждём завершения потоков (до 5 секунд)
                if self._controller._detector:
                    print("[MainWindow] Ожидание завершения DetectorThread...")
                    if not self._controller._detector.wait(5000):
                        print("[MainWindow] WARNING: DetectorThread не завершился за 5 сек")
                elif self._controller._detector_pool:
                    print("[MainWindow] Ожидание завершения DetectorPool...")
                    if not self._controller._detector_pool.wait(5000):
                        print("[MainWindow] WARNING: DetectorPool не завершился за 5 сек")
                
                if self._controller._reader:
                    print("[MainWindow] Ожидание завершения VideoReader...")
                    if not self._controller._reader.wait(2000):
                        print("[MainWindow] WARNING: VideoReader не завершился за 2 сек")
            
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