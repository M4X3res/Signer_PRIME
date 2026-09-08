"""
processing/backend_verify_thread.py
Проверка реально используемого CPU backend (torch/onnx/openvino) для
каждой модели — БЕЗ блокировки главного потока и БЕЗ загрузки моделей
в GUI-потоке (см. BLOCK CPU-6).

До этого фикса processing_controller.py вызывал verify_backend_active()
синхронно в главном GUI-потоке, что загружало все ~17 моделей (YOLO, CNN,
lane-модели) при каждом запуске обработки с backend != "torch", вызывая
зависание UI на 3-5 секунд и нарушая правило "модели грузятся только
лениво в QThread.run()". Теперь эта проверка выполняется асинхронно
в отдельном потоке параллельно с запуском VideoReader/DetectorThread.
"""
from __future__ import annotations
from PyQt6.QtCore import QThread, pyqtSignal


class BackendVerifyThread(QThread):
    """
    Поток для проверки backend'ов моделей.
    
    Signals:
        finished_check(dict): Завершена проверка, возвращает {model_name: backend_or_error}
        error(str): Произошла ошибка при проверке
    """
    finished_check = pyqtSignal(dict)   # {model_name: backend_or_error}
    error = pyqtSignal(str)

    def run(self) -> None:
        """
        Выполняет проверку backend'ов моделей.
        
        ВАЖНО: Грузит модели (через _LazyModel._load()), поэтому вызывается
        в отдельном потоке, а не в GUI-потоке.
        """
        try:
            # torch.set_num_threads(1) — та же защита, что и в DetectorThread,
            # т.к. этот поток тоже грузит модели и может использовать torch.
            try:
                import torch
                torch.set_num_threads(1)
            except Exception:
                pass

            from configs.sign_models import verify_backend_active
            result = verify_backend_active()
            self.finished_check.emit(result)
        except Exception as e:
            self.error.emit(str(e))
