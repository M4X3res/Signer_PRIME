"""
RoadScanner v2 — точка входа
"""
import sys
import os
import logging
from typing import Optional

# ════════════════════════════════════════════════════════════════
# КРИТИЧНО: Флаги Chromium для QWebEngineView
# ════════════════════════════════════════════════════════════════
# Должны быть установлены ДО создания QApplication
sys.argv.extend([
    '--disable-web-security',  # Отключить CORS ограничения
    '--allow-file-access-from-files',  # Разрешить доступ к файлам
    '--autoplay-policy=no-user-gesture-required',  # Автовоспроизведение без жеста
    '--disable-features=AudioServiceOutOfProcess',  # Фикс для аудио/видео
])

# ════════════════════════════════════════════════════════════════
# Импорты (выполняются всегда, в т.ч. в worker процессах)
# ════════════════════════════════════════════════════════════════

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


def setup_environment():
    """Настройка окружения - вызывается ТОЛЬКО в главном процессе."""
    
    # ════════════════════════════════════════════════════════════════
    # Подавление warning'ов (до настройки логирования)
    # ════════════════════════════════════════════════════════════════
    import warnings
    # Подавляем TensorRT warning'и от ONNX Runtime
    # (даже с ORT_DISABLE_CUDA=1, ONNX пытается зарегистрировать TensorRT плагины)
    warnings.filterwarnings('ignore', message='.*TensorRT.*')
    warnings.filterwarnings('ignore', message='.*TensorrtExecutionProvider.*')
    
    # ════════════════════════════════════════════════════════════════
    # Настройка ONNX Runtime (BLOCK M)
    # ════════════════════════════════════════════════════════════════
    # DEPRECATED: ORT_DISABLE_CUDA — не распознается ни ONNX Runtime, ни ultralytics.
    # Реальная защита от CUDA-провайдера теперь идёт через disable_cuda_providers=True
    # в apply_cpu_thread_limits() (см. ниже, BLOCK CPU-5).
    # Оставлено для обратной совместимости, но не имеет эффекта.
    try:
        from configs.settings import get_app_settings
        settings = get_app_settings()
        if not settings.use_cuda:
            os.environ["ORT_DISABLE_CUDA"] = "1"  # DEPRECATED, no-op
            logger = logging.getLogger(__name__)
            logger.info("CPU режим: ONNX Runtime будет использовать только CPU провайдеры")
    except Exception:
        os.environ.setdefault("ORT_DISABLE_CUDA", "1")  # DEPRECATED, no-op
    
    # ════════════════════════════════════════════════════════════════
    # Настройка логирования
    # ════════════════════════════════════════════════════════════════
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('roadscan.log', encoding='utf-8', mode='a')
        ]
    )
    
    # Уменьшаем verbosity сторонних библиотек
    logging.getLogger('ultralytics').setLevel(logging.WARNING)
    logging.getLogger('PIL').setLevel(logging.WARNING)
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    from app.version import APP_VERSION
    logger.info(f"RoadScanner v{APP_VERSION} запускается...")
    
    # ════════════════════════════════════════════════════════════════
    # КРИТИЧНО: Защита от STATUS_STACK_BUFFER_OVERRUN (0xC0000409)
    # ════════════════════════════════════════════════════════════════
    
    # Подавляет краш при одновременном использовании torch (OpenMP libiomp5md.dll) и Qt.
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    
    # Отключает OpenMP-параллелизм внутри torch — убирает второй источник
    # конфликта DLL при инференции YOLO в QThread рядом с Qt WebEngine.
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    
    # Дополнительная защита для Intel MKL
    os.environ["MKL_THREADING_LAYER"] = "GNU"
    
    # Отключаем TBB (Threading Building Blocks) если есть
    os.environ["TBB_NUM_THREADS"] = "1"
    
    # Для OpenCV
    os.environ["OPENCV_NUM_THREADS"] = "1"
    
    # Увеличиваем лимит попыток чтения для GoPro видео с множественными потоками
    # (видео + GPS + акселерометр + аудио)
    os.environ["OPENCV_FFMPEG_READ_ATTEMPTS"] = "100000"
    
    # Дополнительная защита для Qt диалогов на Windows
    # Отключает аппаратное ускорение для избежания конфликтов драйверов
    os.environ["QT_OPENGL"] = "software"
    
    logger.info("Установлены environment workarounds для предотвращения крашей")
    
    # ════════════════════════════════════════════════════════════════
    # Task F: Явное управление потоками ONNX Runtime / OpenVINO
    # ════════════════════════════════════════════════════════════════
    # ONNX Runtime и OpenVINO используют собственные пулы потоков, которые
    # НЕ подчиняются torch.set_num_threads(1) / OMP_NUM_THREADS=1 выше.
    # ИСПРАВЛЕНО Task F: После Task E всегда num_workers=1 (single_thread),
    # поэтому даём ONNX/OpenVINO использовать (cpu_count - 1) потоков для
    # максимальной производительности, а не искусственно ограничиваем их
    # "паритетом с PyTorch".
    
    try:
        from configs.settings import get_app_settings
        from configs.inference_threading import apply_cpu_thread_limits
        
        settings = get_app_settings()
        if not settings.use_cuda:
            # Task F: num_workers всегда 1 после Task E (Process Pool удалён из UI)
            num_workers = 1
            
            # Task F: Используем почти все ядра (cpu_count - 1, оставляем 1 под GUI/чтение видео)
            cpu_count = os.cpu_count() or 4
            intra = settings.cpu_onnx_intra_threads or max(1, cpu_count - 1)
            ov_threads = settings.cpu_openvino_threads or intra
            
            apply_cpu_thread_limits(
                intra_threads=intra,
                inter_threads=settings.cpu_onnx_inter_threads,
                openvino_threads=ov_threads,
                disable_cuda_providers=True,
            )
            logger.info(f"[main] CPU inference threads: intra={intra}, openvino={ov_threads} (Task F: восстановлена многопоточность)")
    except Exception as e:
        logger.warning(f"[main] Не удалось применить CPU thread limits: {e}")
    
    # ════════════════════════════════════════════════════════════════
    
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, base_path)
    
    # КРИТИЧНО: должно быть ДО создания QApplication
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)


def main():
    """Главная функция приложения."""
    from ui.main_window import MainWindow
    from ui.themes.theme_manager import theme_manager, Theme
    from app.version import APP_VERSION
    
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("Инициализация QApplication...")
        
        # ════════════════════════════════════════════════════════════════
        # Task A: Фикс нечитаемых попапов QComboBox в Windows dark mode
        # ════════════════════════════════════════════════════════════════
        # Альтернативная защита: отключить Windows dark-mode интеграцию
        # КРИТИЧНО: должно быть ДО создания QApplication
        os.environ.setdefault("QT_QPA_PLATFORM", "windows:darkmode=0")
        
        # Fusion стиль рисуется Qt программно и не подхватывает OS dark-mode
        # для попапов/менюшек, что решает проблему чёрного фона с тёмным текстом.
        # КРИТИЧНО: должно быть ДО создания QApplication
        QApplication.setStyle("Fusion")
        
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )

        app = QApplication(sys.argv)
        app.setApplicationName("Signer")
        app.setApplicationVersion(APP_VERSION)

        font = QFont("Segoe UI", 13)
        app.setFont(font)

        logger.info("Применение темы оформления...")
        # BLOCK STAB-6: раньше тема ВСЕГДА принудительно сбрасывалась на
        # тёмную при каждом запуске, независимо от того, что пользователь
        # выбрал и сохранил в Настройках в прошлый раз. ThemeManager уже
        # восстановил последнюю сохранённую тему в своём конструкторе
        # (_load_saved_theme()) — здесь нужно её ПРИМЕНИТЬ, а не перезаписать.
        theme_manager.apply(app)

        # ════════════════════════════════════════════════════════════════
        # Проверка лицензии (ПЕРЕД созданием главного окна)
        # ЗАДАЧА 2: Строгая онлайн-проверка при каждом запуске
        # ════════════════════════════════════════════════════════════════
        logger.info("Проверка лицензии...")
        from licensing.license_manager import LicenseManager, LicenseStatus
        from PyQt6.QtWidgets import QMessageBox, QDialog
        from PyQt6.QtCore import QEventLoop
        
        license_manager = LicenseManager()
        
        # Создаём модальный диалог "Проверка лицензии..."
        from ui.widgets.license_dialog import LicenseDialog
        
        verify_dialog = QDialog()
        verify_dialog.setWindowTitle("Signer PRIME")
        verify_dialog.setModal(True)
        verify_dialog.setFixedSize(300, 100)
        
        from PyQt6.QtWidgets import QVBoxLayout, QLabel
        layout = QVBoxLayout()
        label = QLabel("Проверка лицензии...\nПожалуйста, подождите.")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        verify_dialog.setLayout(layout)
        verify_dialog.show()
        app.processEvents()  # Отрисовать диалог
        
        # Флаг для хранения результата проверки
        verification_result = {"status": None, "error_msg": None}
        event_loop = QEventLoop()
        
        def _on_verify_result(status: LicenseStatus, error_msg: Optional[str]):
            """Callback после проверки доступа."""
            verification_result["status"] = status
            verification_result["error_msg"] = error_msg
            verify_dialog.close()
            event_loop.quit()
        
        # Запускаем асинхронную проверку
        license_manager.verify_access_async(_on_verify_result)
        event_loop.exec()  # Ждём завершения
        
        license_status = verification_result["status"]
        error_msg = verification_result["error_msg"]
        
        logger.info(f"Статус лицензии: {license_status.value}")
        
        # Обработка результатов проверки
        if license_status == LicenseStatus.VALID:
            # Всё ОК, продолжаем запуск
            logger.info("Лицензия подтверждена сервером, запуск приложения")
        
        elif license_status == LicenseStatus.NOT_ACTIVATED:
            # Нет токена → показываем диалог активации
            logger.info("Лицензия не активирована, показываем диалог...")
            license_dialog = LicenseDialog(license_manager)
            
            if license_dialog.exec() != LicenseDialog.DialogCode.Accepted:
                logger.info("Пользователь отменил активацию лицензии, выход...")
                return  # Выходим из приложения
            
            logger.info("Лицензия успешно активирована")
        
        elif license_status in (LicenseStatus.EXPIRED, LicenseStatus.REVOKED):
            # Лицензия истекла/отозвана → показываем диалог активации
            logger.warning(f"Лицензия {license_status.value}, требуется повторная активация")
            
            QMessageBox.warning(
                None,
                "Лицензия недействительна",
                f"Ваша подписка {'истекла' if license_status == LicenseStatus.EXPIRED else 'была отозвана'}.\n"
                "Пожалуйста, активируйте лицензию заново.",
            )
            
            license_dialog = LicenseDialog(license_manager)
            if license_dialog.exec() != LicenseDialog.DialogCode.Accepted:
                logger.info("Пользователь отменил активацию лицензии, выход...")
                return
            
            logger.info("Лицензия успешно активирована")
        
        elif license_status == LicenseStatus.NETWORK_ERROR:
            # Сетевая ошибка → блокируем запуск с возможностью повтора
            logger.error(f"Не удалось подключиться к серверу лицензий: {error_msg}")
            
            while True:
                reply = QMessageBox.critical(
                    None,
                    "Ошибка подключения",
                    "Не удалось подключиться к серверу лицензий.\n"
                    "Проверьте интернет-соединение.\n\n"
                    f"Ошибка: {error_msg or 'Неизвестная ошибка'}\n\n"
                    "Попробовать снова?",
                    QMessageBox.StandardButton.Retry | QMessageBox.StandardButton.Cancel
                )
                
                if reply == QMessageBox.StandardButton.Cancel:
                    logger.info("Пользователь отменил запуск из-за ошибки сети")
                    return
                
                # Повторная попытка
                logger.info("Повторная попытка проверки лицензии...")
                verify_dialog.show()
                app.processEvents()
                
                event_loop2 = QEventLoop()
                
                def _on_retry_result(status: LicenseStatus, error_msg: Optional[str]):
                    verification_result["status"] = status
                    verification_result["error_msg"] = error_msg
                    verify_dialog.close()
                    event_loop2.quit()
                
                license_manager.verify_access_async(_on_retry_result)
                event_loop2.exec()
                
                license_status = verification_result["status"]
                error_msg = verification_result["error_msg"]
                
                if license_status == LicenseStatus.VALID:
                    logger.info("Повторная проверка успешна")
                    break
                elif license_status != LicenseStatus.NETWORK_ERROR:
                    # Не сетевая ошибка → выходим из цикла повторов и обрабатываем как обычно
                    break
        
        else:
            # Неизвестный статус
            logger.error(f"Неизвестный статус лицензии: {license_status}")
            QMessageBox.critical(
                None,
                "Ошибка",
                "Произошла неизвестная ошибка при проверке лицензии.\n"
                "Приложение будет закрыто.",
            )
            return
        
        logger.info("Создание главного окна...")
        window = MainWindow()
        
        # Передаём license_manager в MainWindow для доступа из SettingsPage
        window.license_manager = license_manager
        
        window.show()
        
        # ════════════════════════════════════════════════════════════════
        # Задача 2: Запуск runtime мониторинга лицензии
        # ════════════════════════════════════════════════════════════════
        # Флаг для предотвращения двойного вызова _show_license_expired_and_quit
        _quit_dialog_shown = False
        
        def _on_license_status_changed(status: LicenseStatus):
            """Обработчик изменения статуса лицензии во время работы приложения."""
            nonlocal _quit_dialog_shown
            
            if status in (LicenseStatus.EXPIRED, LicenseStatus.REVOKED):
                logger.warning(f"Лицензия стала недействительна во время работы: {status.value}")
                
                # Проверяем, идёт ли обработка видео - если да, даём завершить
                try:
                    if hasattr(window, '_controller') and hasattr(window._controller, 'is_running'):
                        if window._controller.is_running:
                            logger.info("Обнаружена активная обработка, даём завершить перед закрытием...")
                            # Мягко останавливаем обработку
                            if hasattr(window, '_on_finish_requested'):
                                window._on_finish_requested()
                            
                            # БАГ 6: Используем UniqueConnection чтобы избежать дублирования подключений
                            try:
                                window.results_saved.connect(
                                    _show_license_expired_and_quit,
                                    Qt.ConnectionType.UniqueConnection
                                )
                            except TypeError:
                                # Уже подключено - игнорируем
                                pass
                            
                            # Подстраховка: жёсткий потолок ожидания 5 минут
                            # (если сохранение зависнет, не держим приложение навечно)
                            from PyQt6.QtCore import QTimer
                            QTimer.singleShot(5 * 60 * 1000, _show_license_expired_and_quit)
                            return
                except Exception as e:
                    logger.error(f"Ошибка при проверке статуса обработки: {e}")
                
                # Если обработки нет или ошибка - сразу показываем диалог
                _show_license_expired_and_quit()
        
        def _show_license_expired_and_quit():
            """Показывает критический диалог и закрывает приложение."""
            nonlocal _quit_dialog_shown
            
            # Идемпотентность: не показываем диалог дважды
            if _quit_dialog_shown:
                return
            _quit_dialog_shown = True
            
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(
                window,
                "Лицензия недействительна",
                "Ваша подписка истекла или была отозвана.\n"
                "Приложение будет закрыто. Пожалуйста, активируйте лицензию заново.",
            )
            app.quit()
        
        # ВАЖНО: сохранить ссылку на таймер, иначе Python GC соберёт его
        window._license_monitor_timer = license_manager.start_runtime_monitor(
            _on_license_status_changed
        )
        logger.info("Runtime мониторинг лицензии запущен")
        
        # Очистка старых временных файлов обновления
        logger.info("Очистка старых временных файлов обновления...")
        try:
            from updater import updater
            updater.cleanup_stale_update_temp()
        except Exception as e:
            logger.warning(f"Ошибка при очистке временных файлов: {e}")

        logger.info("Приложение готово к работе")
        
        # ════════════════════════════════════════════════════════════════
        # БАГ-1: Проверка локального баннера "обновлено" (не зависит от auto_check_updates)
        # ════════════════════════════════════════════════════════════════
        # Вынесено ИЗ условия автопроверки — это чисто локальная проверка QSettings,
        # не требующая сетевого запроса и не должна зависеть от настройки автообновлений.
        from PyQt6.QtCore import QSettings
        settings = QSettings("Signer", "RoadScanner")
        last_known_version = settings.value("last_known_version", "")
        
        if last_known_version and last_known_version != APP_VERSION:
            # Версия изменилась - показываем уведомление
            logger.info(f"Версия изменилась: {last_known_version} -> {APP_VERSION}")
            # Показываем в статус-баре главного окна (БАГ-3: исправлен вызов set_status)
            if hasattr(window, 'status_bar'):
                window.status_bar.set_status(f"Signer обновлён до версии {APP_VERSION}", duration_ms=10000)
            
            # Обновляем сохранённую версию
            settings.setValue("last_known_version", APP_VERSION)
        
        # ════════════════════════════════════════════════════════════════
        # БАГ-1: Фоновая сетевая проверка обновлений (зависит от настроек)
        # ════════════════════════════════════════════════════════════════
        # Проверяем три условия:
        # 1. Frozen build ИЛИ форс-флаг в окружении
        # 2. Пользователь включил автопроверку в настройках
        from configs.settings import get_app_settings
        app_settings = get_app_settings()
        
        should_check_for_updates = (
            (getattr(sys, "frozen", False) or os.environ.get("SIGNER_FORCE_UPDATE_CHECK") == "1")
            and app_settings.auto_check_updates
        )
        
        if should_check_for_updates:
            from ui.widgets.update_worker import UpdateCheckWorker
            from ui.widgets.update_dialog import UpdateDialog
            
            logger.info("Запуск фоновой проверки обновлений...")
            
            # Функция для обработки результата проверки обновлений
            def _on_update_check_finished(update_info):
                if update_info:
                    try:
                        logger.info(f"Найдено обновление: {update_info.version}")
                        dialog = UpdateDialog(update_info, window)
                        
                        # Подключаем сигнал для применения обновления
                        def _apply_update():
                            try:
                                from updater import updater
                                from pathlib import Path
                                
                                # БАГ-4: Используем единую функцию mark_update_pending
                                updater.mark_update_pending(APP_VERSION)
                                
                                # Определяем директорию установки
                                if getattr(sys, "frozen", False):
                                    install_dir = Path(sys.executable).parent
                                else:
                                    install_dir = Path(__file__).parent / "dist" / "Signer"
                                
                                # Подготавливаем параметры для дельта-режима
                                is_delta = dialog.update_info.is_delta
                                delta_manifest_path = None
                                if is_delta:
                                    delta_manifest_path = dialog.temp_dir / "delta_manifest.json"
                                
                                # Запускаем Updater и закрываем приложение
                                updater.launch_updater_and_exit(
                                    dialog.temp_dir,
                                    install_dir,
                                    is_delta=is_delta,
                                    delta_manifest_path=delta_manifest_path
                                )
                                app.quit()
                                
                            except Exception as e:
                                logger.error(f"Ошибка при применении обновления: {e}", exc_info=True)
                        
                        dialog.update_applied.connect(_apply_update)
                        dialog.exec()
                        
                    except Exception as e:
                        logger.error(f"Ошибка при показе диалога обновления: {e}", exc_info=True)
                else:
                    logger.info("Обновлений не найдено")
            
            def _on_update_check_error(error_msg):
                logger.warning(f"Ошибка проверки обновлений: {error_msg}")
            
            # БАГ-2: Передаём канал обновлений в воркер
            update_worker = UpdateCheckWorker(channel=app_settings.update_channel)
            update_worker.finished_check.connect(_on_update_check_finished)
            update_worker.error.connect(_on_update_check_error)
            update_worker.start()
        
        sys.exit(app.exec())
        
    except Exception as e:
        logger.critical("=" * 60)
        logger.critical("КРИТИЧЕСКАЯ ОШИБКА В MAIN:")
        logger.critical("=" * 60)
        logger.exception(f"{type(e).__name__}: {e}")
        logger.critical("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    # ════════════════════════════════════════════════════════════════
    # HEADLESS РЕЖИМ: --verify-backends (для scripts/build/verify_cpu_backends.py)
    # ════════════════════════════════════════════════════════════════
    if "--verify-backends" in sys.argv:
        import json
        
        # Минимальная настройка окружения без GUI
        os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
        os.environ["OMP_NUM_THREADS"] = "1"
        
        # Базовое логирование
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s',
            handlers=[logging.StreamHandler(sys.stdout)]
        )
        logger = logging.getLogger(__name__)
        
        try:
            from configs import sign_models
            from configs.settings import AppSettings
            
            # Проверяем оба backend'а
            results = {}
            for backend_name in ["onnx", "openvino"]:
                logger.info(f"Проверка backend: {backend_name}")
                
                # Временные настройки для этого backend
                temp_settings = AppSettings()
                temp_settings.use_cuda = False
                temp_settings.cpu_inference_backend = backend_name
                
                # Патчим get_app_settings
                import configs.settings
                original = configs.settings.get_app_settings
                configs.settings.get_app_settings = lambda: temp_settings
                
                try:
                    # Сбрасываем кеш и проверяем
                    sign_models.reload_all_models_if_device_changed()
                    backend_status = sign_models.verify_backend_active()
                    
                    # Проверяем результат
                    errors = []
                    for model_name, actual_backend in backend_status.items():
                        if actual_backend != backend_name:
                            errors.append(f"{model_name}: {actual_backend}")
                    
                    results[backend_name] = {
                        "success": len(errors) == 0,
                        "errors": errors
                    }
                finally:
                    configs.settings.get_app_settings = original
            
            # Выводим результат в JSON
            all_success = all(r["success"] for r in results.values())
            output = {
                "success": all_success,
                "backends": results
            }
            print("\n=== VERIFICATION RESULT ===")
            print(json.dumps(output, indent=2))
            
            sys.exit(0 if all_success else 1)
            
        except Exception as e:
            logger.error(f"Критическая ошибка: {e}", exc_info=True)
            sys.exit(1)
    
    # ════════════════════════════════════════════════════════════════
    
    # КРИТИЧНО для multiprocessing на Windows
    from multiprocessing import freeze_support, current_process
    freeze_support()
    
    # Настройка окружения и запуск GUI только в главном процессе
    if current_process().name == 'MainProcess':
        setup_environment()
        main()
    else:
        # Worker процессы - только базовая настройка для избежания крашей
        # КРИТИЧНО: переменные окружения должны быть установлены ДО любых импортов
        os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
        os.environ["OMP_NUM_THREADS"] = "1"
        os.environ["MKL_NUM_THREADS"] = "1"
        
        # BLOCK M: Настройка ONNX Runtime для worker процессов
        # DEPRECATED: ORT_DISABLE_CUDA не имеет эффекта, см. apply_cpu_thread_limits()
        os.environ.setdefault("ORT_DISABLE_CUDA", "1")  # DEPRECATED, no-op
        
        # Worker процесс не запускает GUI - ProcessPoolExecutor использует его для задач
        pass