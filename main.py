"""
RoadScanner v2 — точка входа
"""
import sys
import os
import logging

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
    logger.info("RoadScanner v2 запускается...")
    
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
        app.setApplicationVersion("2.0")

        font = QFont("Segoe UI", 13)
        app.setFont(font)

        logger.info("Применение темы оформления...")
        # BLOCK STAB-6: раньше тема ВСЕГДА принудительно сбрасывалась на
        # тёмную при каждом запуске, независимо от того, что пользователь
        # выбрал и сохранил в Настройках в прошлый раз. ThemeManager уже
        # восстановил последнюю сохранённую тему в своём конструкторе
        # (_load_saved_theme()) — здесь нужно её ПРИМЕНИТЬ, а не перезаписать.
        theme_manager.apply(app)

        logger.info("Создание главного окна...")
        window = MainWindow()
        window.show()

        logger.info("Приложение готово к работе")
        sys.exit(app.exec())
        
    except Exception as e:
        logger.critical("=" * 60)
        logger.critical("КРИТИЧЕСКАЯ ОШИБКА В MAIN:")
        logger.critical("=" * 60)
        logger.exception(f"{type(e).__name__}: {e}")
        logger.critical("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
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