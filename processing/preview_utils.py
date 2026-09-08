"""
processing/preview_utils.py
Единая точка конвертации "сырой BGR-кадр" -> QPixmap.

ВАЖНО: функция build_pixmap_from_frame_dict() создаёт QImage/QPixmap и поэтому
ДОЛЖНА вызываться только из главного (GUI) потока. Воркеры (QThread или
worker-процессы) должны отправлять только словарь с сырыми байтами через
build_frame_dict(), не создавая никаких Qt GUI-объектов самостоятельно.

Это решает проблему, описанную в docs: QPixmap/QImage нельзя создавать в
non-GUI потоках (Qt threading restriction). Нарушение этого правила приводит к:
- Искажённым/не обновляющимся кадрам
- Непредсказуемым крашам (особенно на Windows с разными GPU драйверами)
- Зависаниям UI

Архитектура:
    Worker Thread/Process:
        image (np.ndarray) → build_frame_dict() → emit(dict)
    
    Main GUI Thread (ProcessingController):
        receive(dict) → build_pixmap_from_frame_dict() → QPixmap → UI
"""
from __future__ import annotations

import numpy as np
import cv2
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap


def build_frame_dict(image_bgr: np.ndarray) -> dict:
    """
    Вызывается из ЛЮБОГО потока/процесса.
    Сериализует BGR numpy-кадр в примитивные данные без создания Qt-объектов.
    
    Args:
        image_bgr: BGR изображение (формат OpenCV)
    
    Returns:
        dict с ключами:
            - image_bytes: сериализованный массив
            - shape: форма массива (height, width, channels)
            - dtype: тип данных numpy (строка)
    
    Note:
        np.ndarray.tobytes() всегда возвращает C-contiguous данные,
        независимо от исходного layout массива.
    """
    # Делаем копию для гарантии contiguous layout (хотя tobytes() справится и так)
    frame = np.ascontiguousarray(image_bgr)
    
    return {
        "image_bytes": frame.tobytes(),
        "shape": frame.shape,
        "dtype": str(frame.dtype),
    }


def build_pixmap_from_frame_dict(
    frame_dict: dict,
    target_size: tuple[int, int] = (960, 540),
) -> QPixmap:
    """
    Вызывать ТОЛЬКО из главного GUI-потока.
    Восстанавливает numpy-массив и создаёт QPixmap.
    
    Args:
        frame_dict: словарь из build_frame_dict()
        target_size: целевой размер для масштабирования (width, height)
    
    Returns:
        QPixmap, готовый к отображению в UI
    
    Raises:
        ValueError: если формат frame_dict некорректен
    
    Warning:
        ⚠️ Эта функция создаёт QPixmap — вызывать ТОЛЬКО из главного потока!
        Вызов из QThread/worker-процесса приведёт к undefined behavior.
    """
    if not isinstance(frame_dict, dict) or "image_bytes" not in frame_dict:
        raise ValueError(f"Invalid frame_dict format: {type(frame_dict)}")
    
    # Восстанавливаем numpy array из сериализованных данных
    dtype = np.dtype(frame_dict["dtype"])
    arr = np.frombuffer(frame_dict["image_bytes"], dtype=dtype).reshape(frame_dict["shape"])
    
    # BGR → RGB конвертация (OpenCV использует BGR, Qt использует RGB)
    rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    
    # Создаём QImage. .copy() критически важен — отвязывает QImage от временного
    # буфера rgb, который будет удалён после выхода из функции. Без .copy()
    # QPixmap может содержать мусор или крашиться при попытке отрисовки.
    qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
    
    # Создаём и масштабируем QPixmap
    pixmap = QPixmap.fromImage(qimg).scaled(
        target_size[0], target_size[1],
        aspectRatioMode=Qt.AspectRatioMode.KeepAspectRatio,
    )
    
    return pixmap
