"""
core/detector.py
Detector — обнаружение и классификация знаков на одном кадре.

Рефакторинг оригинального Detector.py:
  1. Модели НЕ грузятся здесь — берутся из configs.sign_models (синглтоны)
  2. Методы разбиты по ответственности: detect → classify → read_text
  3. Типы везде где возможно
  4. LaneDetector не создаётся при каждом вызове
  5. OCR reader — синглтон на уровне модуля
  6. CNN кэширование — LRU кэш результатов классификации по хэшу изображения
"""
from __future__ import annotations

import difflib
import hashlib
import logging
import os
import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

import configs.config as config
from configs.sign_data import (
    TYPE_SIGNS_WITH_TEXT,
    NAME_SIGNS_CITY,
    NAMES_SIGNS_FOR_YOLO,
)
from configs.sign_models import (
    model_side_detect,
    rube_modal,
    model_dict,
    sub_models,
)
from core.profiler import profiler
from utils import resource_path

logger = logging.getLogger(__name__)

# OCR reader — инициализируется лениво при первом вызове
_ocr_reader = None

def _get_ocr():
    """
    Ленивая инициализация EasyOCR reader.
    Использует GPU если настройка use_cuda=True и CUDA доступна.
    """
    global _ocr_reader
    if _ocr_reader is None:
        try:
            from configs.settings import get_app_settings
            import torch
            import easyocr
            
            settings = get_app_settings()
            use_gpu = settings.use_cuda and torch.cuda.is_available()
            _ocr_reader = easyocr.Reader(["be"], gpu=use_gpu)
            
        except Exception as e:
            # Фоллбэк на CPU в случае любой ошибки
            import easyocr
            print(f"[OCR] Ошибка инициализации с проверкой настроек: {e}, используем CPU")
            _ocr_reader = easyocr.Reader(["be"], gpu=False)
    
    return _ocr_reader


# ══════════════════════════════════════════════════════════════════
# CNN КЭШИРОВАНИЕ
# ══════════════════════════════════════════════════════════════════

class CNNCache:
    """
    LRU кэш для результатов CNN классификации и OCR.
    Ключ: хэш изображения
    Значение: tuple[str, float] для CNN или str для OCR
    """
    
    def __init__(self, maxsize: int = 1000):
        self._cache: OrderedDict = OrderedDict()
        self._maxsize = maxsize
        self._hits = 0
        self._misses = 0
    
    def get(self, img_hash: str):
        """Получить закэшированный результат (может быть tuple или str)."""
        if img_hash in self._cache:
            self._hits += 1
            # Перемещаем в конец (самый свежий)
            self._cache.move_to_end(img_hash)
            return self._cache[img_hash]
        
        self._misses += 1
        return None
    
    def put(self, img_hash: str, result) -> None:
        """Сохранить результат в кэш (может быть tuple[str, float] или str)."""
        if img_hash in self._cache:
            # Обновляем существующий
            self._cache.move_to_end(img_hash)
        else:
            # Добавляем новый
            self._cache[img_hash] = result
            
            # Удаляем самый старый если превысили лимит
            if len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)
    
    def clear(self) -> None:
        """Очистить кэш."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
    
    @property
    def hit_rate(self) -> float:
        """Процент попаданий в кэш."""
        total = self._hits + self._misses
        return (self._hits / total * 100) if total > 0 else 0.0
    
    @property
    def size(self) -> int:
        """Текущий размер кэша."""
        return len(self._cache)
    
    def stats(self) -> dict:
        """Статистика кэша."""
        return {
            "size": self.size,
            "maxsize": self._maxsize,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self.hit_rate,
        }


def compute_image_hash(img: np.ndarray) -> str:
    """
    Вычисляет perceptual hash изображения (pHash).
    Возвращает одинаковый хеш для визуально похожих изображений.
    Используется для кэширования CNN классификации знаков.
    
    Алгоритм:
    1. Resize to 8x8 (уже делается до 32x32, downscale еще раз)
    2. Grayscale (если цветное)
    3. DCT (Discrete Cosine Transform) на 8x8
    4. Берем top-left 8x8 DCT коэффициенты
    5. Медиана и бинаризация
    """
    # Downscale to 8x8 для pHash
    small = cv2.resize(img, (8, 8), interpolation=cv2.INTER_AREA)
    
    # Convert to grayscale if needed
    if len(small.shape) == 3:
        small = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    
    # DCT на 8x8
    # OpenCV cv2.dct требует float32
    small_float = np.float32(small)
    dct = cv2.dct(small_float)
    
    # Берем левый верхний угол 8x8 (low frequencies)
    dct_low = dct[:8, :8]
    
    # Медиана (без DC коэффициента [0,0])
    median = np.median(dct_low[1:, 1:])
    
    # Бинаризация: 1 если > median, иначе 0
    diff = dct_low > median
    
    # BLOCK K.2: Векторизация через numpy.packbits (вместо Python циклов)
    bits = diff.flatten().astype(np.uint8)
    packed = np.packbits(bits)  # 8 байт для 64 бит
    hash_value = int.from_bytes(packed.tobytes(), byteorder="big")
    
    return f"{hash_value:016x}"


@dataclass
class RawDetection:
    """Сырой результат детекции одного знака в кадре."""
    box:        tuple[int, int, int, int]  # x, y, w, h
    color:      tuple[int, int, int]
    yolo_class: str     # класс первого уровня (напр. "treugolnik")
    cnn_class:  str     # класс второго уровня (напр. "1.21")
    text:       str     # OCR текст если знак с надписью
    is_side:    bool    # боковой знак


class Detector:
    """
    Обнаруживает знаки на одном BGR-кадре.
    Использует:
      1. model_side_detect — YOLO, находит bbox и тип (боковой/нет)
      2. rube_modal        — YOLO, грубая классификация категории
      3. model_dict        — YOLO, точная классификация внутри категории
      4. sub_models        — YOLO, субклассификация (треугольники)
      5. LaneDetector      — для знаков 5.8 (разметка полос)
      6. OCR               — для знаков с текстом
      7. CNNCache          — кэширование результатов CNN классификации
    """

    # Размер кэша (количество уникальных изображений)
    CACHE_SIZE   = 1000

    COLORS = [
        (0, 255, 0), (0, 0, 255), (255, 0, 0),
        (255, 255, 0), (255, 0, 255), (0, 255, 255),
    ]

    def __init__(self, settings=None):
        """
        Инициализирует детектор.
        
        Args:
            settings: AppSettings или None (используются defaults)
        """
        from core.lane_detector import LaneDetector
        
        # Загружаем настройки
        if settings is None:
            from configs.settings import get_app_settings
            settings = get_app_settings()
        
        # Применяем пороги уверенности из настроек
        self.CONF_SIDE = settings.conf_side
        self.CONF_RUBE = settings.conf_rube
        self.CONF_CNN = settings.conf_cnn
        self.IOU_THRESHOLD = settings.iou_threshold
        
        # BLOCK N.2: Сохранение error_frames
        self._save_error_frames = settings.save_error_frames
        self._error_frames_dir = settings.error_frames_dir
        self._error_frames_saved = {}  # track_id → count (троттлинг: макс 1 на знак)
        
        self._lane_detector = LaneDetector()
        self._city_names:  list[str] = []
        self._counter = 0
        
        # CNN кэш для ускорения повторных классификаций
        self._cnn_cache = CNNCache(maxsize=self.CACHE_SIZE)
        self._last_stats_print = 0  # для throttling статистики
        
        # OCR кэш для ускорения повторных распознаваний текста (BLOCK CPU-4)
        self._ocr_cache = CNNCache(maxsize=500)  # переиспользуем LRU-механизм CNNCache
        
        # ── BLOCK CPU-3: TrackedSign CNN-skip статистика ──────────
        self._tracked_skip_count = 0  # Сколько раз пропустили CNN благодаря трекингу
        
        logger.info(f"Detector инициализирован: CONF_SIDE={self.CONF_SIDE:.2f}, "
                   f"CONF_RUBE={self.CONF_RUBE:.2f}, CONF_CNN={self.CONF_CNN:.2f}, "
                   f"IOU={self.IOU_THRESHOLD:.2f}, "
                   f"save_error_frames={self._save_error_frames}")

    # ── Главный метод ─────────────────────────────────────────────

    def detect(self, frame: np.ndarray, skip_ocr: bool = False) -> list[RawDetection]:
        """
        Запускает полный пайплайн детекции на одном кадре.
        
        Args:
            frame: BGR изображение
            skip_ocr: Если True, OCR не выполняется (для pipeline режима)
        
        Returns:
            Список RawDetection
        """
        results: list[RawDetection] = []

        # Шаг 1: найти все bbox знаков через model_side_detect
        with profiler.measure("yolo_bbox_detection"):
            raw_boxes = self._find_boxes(frame)
        
        if len(raw_boxes) == 0:
            return results

        # Подготовка всех кропов и resize (векторизовано)
        with profiler.measure("batch_prepare_crops"):
            crops_data = []  # [(box, is_side, crop, resized32)]
            
            for box, is_side in raw_boxes:
                x, y, w, h = box
                crop = frame[y: y + h, x: x + w]
                if crop.size == 0:
                    continue
                
                resized = cv2.resize(crop, (32, 32))
                crops_data.append((box, is_side, crop, resized))
        
        if len(crops_data) == 0:
            return results

        # Шаг 2: батчинг грубой классификации (rube)
        with profiler.measure("batch_classify_rube"):
            rube_results = self._classify_rube_batch([cd[3] for cd in crops_data])
        
        # Фильтрация: убираем знаки, которые не прошли rube классификацию
        valid_crops = []
        for crop_data, yolo_class in zip(crops_data, rube_results):
            if yolo_class is not None:
                valid_crops.append((*crop_data, yolo_class))
        
        if len(valid_crops) == 0:
            return results

        # Шаг 3: батчинг точной классификации (CNN)
        # Группируем по yolo_class для эффективного батчинга
        with profiler.measure("batch_classify_fine"):
            cnn_results = self._classify_fine_batch(
                [vc[3] for vc in valid_crops],  # resized32
                [vc[4] for vc in valid_crops]   # yolo_class
            )
        
        # Шаг 4: формирование финальных результатов
        for (box, is_side, crop, resized, yolo_class), cnn_class in zip(valid_crops, cnn_results):
            if cnn_class == -1:
                continue
            
            # OCR текст если нужен (пропускаем в pipeline режиме)
            text = ""
            if not skip_ocr:
                with profiler.measure("ocr_read_text"):
                    text = self._read_text(crop, cnn_class, yolo_class)

            color = self.COLORS[self._counter % len(self.COLORS)]
            self._counter += 1

            results.append(RawDetection(
                box       = box,
                color     = color,
                yolo_class= yolo_class,
                cnn_class = cnn_class,
                text      = text,
                is_side   = is_side,
            ))

        return results

    # ── Шаг 1: поиск bbox ─────────────────────────────────────────

    def _find_boxes(
        self, frame: np.ndarray
    ) -> list[tuple[tuple[int,int,int,int], bool]]:
        """
        Возвращает [(x,y,w,h), is_side] для каждого обнаруженного знака.
        is_side=True если знак находится сбоку (не фронтально).
        """
        results_raw = model_side_detect.predict(
            frame, iou=self.IOU_THRESHOLD, conf=self.CONF_SIDE,
            imgsz=608, verbose=False,
        )
        boxes:   list[tuple] = []
        classes: list[int]   = results_raw[0].boxes.cls.cpu().numpy().astype(int).tolist()
        xyxy:    np.ndarray  = results_raw[0].boxes.xyxy.cpu().numpy().astype(int)

        for cls, coords in zip(classes, xyxy):
            is_side = not bool(cls)
            x1, y1, x2, y2 = coords
            w, h = x2 - x1, y2 - y1
            boxes.append(((x1, y1, w, h), is_side))

        return boxes

    # ── Шаг 2: грубая классификация ───────────────────────────────

    def _classify_rube(self, crop32: np.ndarray) -> Optional[str]:
        """
        Определяет категорию знака через rube_modal.
        Возвращает None если уверенность ниже CONF_RUBE.
        """
        result = rube_modal.predict(crop32, conf=self.CONF_RUBE)[0]
        if not result:
            return None

        conf = float(result.probs.top1conf.cpu().numpy())
        if conf < self.CONF_RUBE:
            return None

        class_name = result.names[np.argmax(result.probs.data.tolist())]

        # Игнорируем пешеходный переход
        if class_name == "5.16.2":
            return None

        # Нормализация
        if class_name == "7.13":
            class_name = "7.13.1"
        if class_name == "5.7.1-5.7.2":
            class_name = "5.7.1"

        return class_name

    # ── Шаг 3: точная классификация ───────────────────────────────

    def _classify_fine(
        self, crop32: np.ndarray, yolo_class: str
    ) -> str | int:
        """
        Классифицирует знак внутри категории.
        Возвращает строку-тип или -1 если ненадёжно.
        """
        if yolo_class in model_dict:
            return self._run_cnn_model(crop32, yolo_class)

        if yolo_class == "5.8":
            return self._lane_detector.find_signs(crop32)

        # YOLO-класс прямо соответствует типу знака
        return yolo_class

    def _run_cnn_model(
        self, crop32: np.ndarray, yolo_class: str
    ) -> str | int:
        """
        Запускает CNN модель для категории и субкатегории.
        Использует кэш для ускорения повторных классификаций.
        """
        # Вычисляем хэш изображения для кэширования
        img_hash = compute_image_hash(crop32)
        cache_key = f"{yolo_class}:{img_hash}"
        
        # Проверяем кэш
        cached = self._cnn_cache.get(cache_key)
        if cached is not None:
            cnn_class, conf = cached
            # Проверяем что кэшированная уверенность проходит порог
            if conf >= self.CONF_CNN:
                return cnn_class
            else:
                return -1
        
        # Кэш промах — запускаем модель
        model  = model_dict[yolo_class]
        output = model(crop32)[0]

        conf = float(output.probs.top1conf.cpu().numpy())
        result_type = output.names[np.argmax(output.probs.data.tolist())]

        # Субклассификация треугольников
        if yolo_class == "treugolnik" and result_type in sub_models:
            # Для субмоделей тоже используем кэш
            sub_hash = compute_image_hash(crop32)
            sub_cache_key = f"sub_{result_type}:{sub_hash}"
            
            sub_cached = self._cnn_cache.get(sub_cache_key)
            if sub_cached is not None:
                result_type, sub_conf = sub_cached
                conf = sub_conf
            else:
                sub_out = sub_models[result_type](crop32)[0]
                sub_conf = float(sub_out.probs.top1conf.cpu().numpy())
                result_type = sub_out.names[np.argmax(sub_out.probs.data.tolist())]
                conf = sub_conf
                
                # Кэшируем результат субмодели
                self._cnn_cache.put(sub_cache_key, (result_type, sub_conf))
        
        # Сохраняем в кэш
        final_result = result_type if result_type else yolo_class
        self._cnn_cache.put(cache_key, (final_result, conf))
        
        # Периодически выводим статистику кэша (раз в 100 вызовов)
        if self._counter % 100 == 0:
            self._print_cache_stats()
        
        if conf < self.CONF_CNN:
            # BLOCK N.2: Сохранение error_frames при низкой уверенности
            self._maybe_save_error_frame(crop32, yolo_class, conf, frame_idx=-1)
            return -1
        
        return final_result
    
    def _maybe_save_error_frame(
        self,
        crop: np.ndarray,
        yolo_class: str,
        conf: float,
        frame_idx: int,
        track_id: Optional[int] = None
    ) -> None:
        """
        Сохраняет кроп с низкой уверенностью в error_frames_dir.
        Троттлинг: максимум 1 сохранение на track_id (или на yolo_class, если track_id нет).
        
        Args:
            crop: Изображение кропа (BGR)
            yolo_class: Класс YOLO модели
            conf: Уверенность модели
            frame_idx: Номер кадра (для имени файла)
            track_id: ID трекаемого знака (для троттлинга)
        """
        if not self._save_error_frames:
            return
        
        # Троттлинг: сохраняем максимум 1 раз на track_id (или yolo_class)
        key = track_id if track_id is not None else yolo_class
        if key in self._error_frames_saved:
            return
        
        try:
            # Создаём директорию лениво
            os.makedirs(self._error_frames_dir, exist_ok=True)
            
            # Имя файла: frame_{idx}_{yolo_class}_{conf:.2f}_{timestamp}.jpg
            import time
            timestamp = int(time.time() * 1000)
            filename = f"frame_{frame_idx}_{yolo_class}_{conf:.2f}_{timestamp}.jpg"
            filepath = os.path.join(self._error_frames_dir, filename)
            
            # Сохраняем
            cv2.imwrite(filepath, crop)
            logger.debug(f"[Detector] Сохранён error_frame: {filename}")
            
            # Отмечаем, что для этого знака уже сохранили
            self._error_frames_saved[key] = True
            
        except Exception as e:
            logger.warning(f"[Detector] Не удалось сохранить error_frame: {e}")
    
    def _print_cache_stats(self) -> None:
        """Выводит статистику CNN кэша в консоль."""
        import time
        now = time.time()
        
        # Throttling: раз в 10 секунд
        if now - self._last_stats_print < 10:
            return
        
        self._last_stats_print = now
        stats = self._cnn_cache.stats()
        
        print(f"[CNNCache] Размер: {stats['size']}/{stats['maxsize']}, "
              f"Попаданий: {stats['hits']}, Промахов: {stats['misses']}, "
              f"Hit Rate: {stats['hit_rate']:.1f}%")
    
    def get_ocr_cache_stats(self) -> dict:
        """
        Возвращает статистику OCR кэша.
        Рекомендуется для мониторинга эффективности кэширования в продакшене.
        """
        return self._ocr_cache.stats()

    # ── Шаг 4: OCR ────────────────────────────────────────────────
    
    def needs_ocr(self, cnn_class: str, yolo_class: str) -> bool:
        """
        Проверяет, требуется ли OCR для данного знака.
        Используется в pipeline режиме для фильтрации.
        """
        return (cnn_class in TYPE_SIGNS_WITH_TEXT or 
                yolo_class in NAME_SIGNS_CITY)

    def _read_text(
        self,
        crop_orig: np.ndarray,
        cnn_class: str,
        yolo_class: str,
    ) -> str:
        """
        Читает текст если знак предполагает надпись.
        Использует OCR-кэш по perceptual hash для ускорения.
        """
        needs_basic = cnn_class in TYPE_SIGNS_WITH_TEXT
        needs_city = yolo_class in NAME_SIGNS_CITY
        
        if not needs_basic and not needs_city:
            return ""
        
        # Вычисляем hash изображения для кэша
        img_hash = compute_image_hash(crop_orig)
        cache_key = f"{'ocr_city' if needs_city else 'ocr_basic'}:{img_hash}"
        
        # Проверяем кэш
        cached = self._ocr_cache.get(cache_key)
        if cached is not None:
            return cached  # CNNCache для OCR хранит строки, а не кортежи
        
        # Выполняем OCR
        if needs_city:
            text = self._ocr_city(crop_orig)
        else:
            text = self._ocr(crop_orig)
        
        # Сохраняем в кэш
        self._ocr_cache.put(cache_key, text)
        return text

    def _ocr(self, crop: np.ndarray) -> str:
        """Базовый OCR — возвращает первую строку."""
        result = _get_ocr().readtext(crop)
        if not result:
            return ""
        return result[0][1]

    def _ocr_city(self, crop: np.ndarray) -> str:
        """
        OCR для городских знаков с нормализацией и
        поиском ближайшего совпадения в справочнике городов.
        """
        raw = self._ocr(crop)
        if not raw:
            return ""

        normalized = re.sub(r"[^a-zA-Zа-яА-ЯёЁ]", "", raw).lower()

        if not self._city_names:
            self._load_city_names()

        matches = difflib.get_close_matches(
            normalized, self._city_names, n=1, cutoff=0.6
        )
        return matches[0] if matches else normalized

    def _load_city_names(self) -> None:
        path = resource_path("static/cities_be.txt")
        try:
            with open(path, encoding="utf-8") as f:
                self._city_names = [
                    line.strip().lower() for line in f if line.strip()
                ]
        except FileNotFoundError:
            pass

    # ── БАТЧИНГ методы ─────────────────────────────────────────────

    def _classify_rube_batch(self, crops32: list[np.ndarray]) -> list[Optional[str]]:
        """
        Батчинг версия _classify_rube.
        Обрабатывает несколько кропов за один проход через модель.
        
        Args:
            crops32: Список изображений 32x32
            
        Returns:
            Список yolo_class (или None если знак не прошёл порог)
        """
        if len(crops32) == 0:
            return []
        
        # YOLO ultralytics поддерживает батчинг через список изображений
        results = rube_modal.predict(crops32, conf=self.CONF_RUBE, verbose=False)
        
        yolo_classes = []
        for result in results:
            if not result or len(result.probs) == 0:
                yolo_classes.append(None)
                continue
            
            conf = float(result.probs.top1conf.cpu().numpy())
            if conf < self.CONF_RUBE:
                yolo_classes.append(None)
                continue
            
            class_name = result.names[np.argmax(result.probs.data.tolist())]
            
            # Игнорируем пешеходный переход
            if class_name == "5.16.2":
                yolo_classes.append(None)
                continue
            
            # Нормализация
            if class_name == "7.13":
                class_name = "7.13.1"
            if class_name == "5.7.1-5.7.2":
                class_name = "5.7.1"
            
            yolo_classes.append(class_name)
        
        return yolo_classes

    def _classify_fine_batch(
        self, 
        crops32: list[np.ndarray], 
        yolo_classes: list[str]
    ) -> list[str | int]:
        """
        Батчинг версия _classify_fine.
        Группирует кропы по yolo_class и обрабатывает батчами.
        
        Args:
            crops32: Список изображений 32x32
            yolo_classes: Список yolo_class для каждого кропа
            
        Returns:
            Список cnn_class (или -1 если знак не прошёл порог)
        """
        if len(crops32) != len(yolo_classes):
            raise ValueError("crops32 и yolo_classes должны иметь одинаковую длину")
        
        if len(crops32) == 0:
            return []
        
        # Группируем по yolo_class для эффективного батчинга
        groups: dict[str, list[tuple[int, np.ndarray]]] = {}  # yolo_class -> [(index, crop)]
        
        for i, (crop, yolo_class) in enumerate(zip(crops32, yolo_classes)):
            if yolo_class not in groups:
                groups[yolo_class] = []
            groups[yolo_class].append((i, crop))
        
        # Результаты в порядке индексов
        results = [None] * len(crops32)
        
        # Обрабатываем каждую группу батчем
        for yolo_class, items in groups.items():
            indices = [idx for idx, _ in items]
            group_crops = [crop for _, crop in items]
            
            # Проверяем кэш для каждого изображения
            cached_results = []
            uncached_indices = []
            uncached_crops = []
            
            for idx, crop in zip(indices, group_crops):
                img_hash = compute_image_hash(crop)
                cache_key = f"{yolo_class}:{img_hash}"
                
                cached = self._cnn_cache.get(cache_key)
                if cached is not None:
                    cnn_class, conf = cached
                    cached_results.append((idx, cnn_class if conf >= self.CONF_CNN else -1, img_hash))
                else:
                    uncached_indices.append(idx)
                    uncached_crops.append(crop)
            
            # Применяем кэшированные результаты
            for idx, cnn_class, _ in cached_results:
                results[idx] = cnn_class
            
            # Обрабатываем некэшированные батчем
            if len(uncached_crops) > 0:
                batch_results = self._run_cnn_batch(uncached_crops, yolo_class)
                
                for idx, cnn_class in zip(uncached_indices, batch_results):
                    results[idx] = cnn_class
        
        return results

    def _run_cnn_batch(
        self, 
        crops32: list[np.ndarray], 
        yolo_class: str
    ) -> list[str | int]:
        """
        Запускает CNN модель на батче изображений одного yolo_class.
        
        Args:
            crops32: Список изображений 32x32
            yolo_class: Категория знака
            
        Returns:
            Список cnn_class (или -1 если не прошёл порог)
        """
        # Специальные случаи (без модели)
        if yolo_class not in model_dict:
            if yolo_class == "5.8":
                # LaneDetector не поддерживает батчинг, обрабатываем поштучно
                return [self._lane_detector.find_signs(crop) for crop in crops32]
            else:
                # YOLO-класс = CNN-класс
                return [yolo_class] * len(crops32)
        
        # Батчинг через ultralytics
        model = model_dict[yolo_class]
        batch_outputs = model(crops32, verbose=False)
        
        results = []
        for i, output in enumerate(batch_outputs):
            conf = float(output.probs.top1conf.cpu().numpy())
            result_type = output.names[np.argmax(output.probs.data.tolist())]
            
            # Субклассификация треугольников (пока без батчинга)
            if yolo_class == "treugolnik" and result_type in sub_models:
                crop = crops32[i]
                img_hash = compute_image_hash(crop)
                sub_cache_key = f"sub_{result_type}:{img_hash}"
                
                sub_cached = self._cnn_cache.get(sub_cache_key)
                if sub_cached is not None:
                    result_type, conf = sub_cached
                else:
                    sub_out = sub_models[result_type](crop, verbose=False)[0]
                    sub_conf = float(sub_out.probs.top1conf.cpu().numpy())
                    result_type = sub_out.names[np.argmax(sub_out.probs.data.tolist())]
                    conf = sub_conf
                    
                    # Кэшируем результат субмодели
                    self._cnn_cache.put(sub_cache_key, (result_type, sub_conf))
            
            # Сохраняем в основной кэш
            final_result = result_type if result_type else yolo_class
            img_hash = compute_image_hash(crops32[i])
            cache_key = f"{yolo_class}:{img_hash}"
            self._cnn_cache.put(cache_key, (final_result, conf))
            
            # Проверяем порог уверенности
            if conf < self.CONF_CNN:
                # BLOCK N.2: Сохранение error_frames при низкой уверенности (батч)
                self._maybe_save_error_frame(crops32[i], yolo_class, conf, frame_idx=i)
                results.append(-1)
            else:
                results.append(final_result)
        
        # Периодически выводим статистику кэша
        if self._counter % 100 == 0:
            self._print_cache_stats()
        
        return results

    # ── Совместимость со старым API ───────────────────────────────

    def find_rectangles(self, frame: np.ndarray) -> list:
        """
        Обратная совместимость с оригинальным Detector.find_rectangles.
        Возвращает список в старом формате:
          [box, color, label, class_name, res, text_on_sign, isSide]
        """
        detections = self.detect(frame)
        return [
            [
                list(d.box),
                d.color,
                d.cnn_class,
                d.yolo_class,
                d.cnn_class,
                d.text,
                d.is_side,
            ]
            for d in detections
        ]
    
    # ── Управление кэшем ──────────────────────────────────────────
    
    def clear_cache(self) -> None:
        """Очистить CNN кэш."""
        self._cnn_cache.clear()
        print("[CNNCache] Кэш очищен")
    
    def get_cache_stats(self) -> dict:
        """Получить статистику кэша."""
        return self._cnn_cache.stats()
    
    @property
    def cache_hit_rate(self) -> float:
        """Процент попаданий в кэш."""
        return self._cnn_cache.hit_rate
    
    # ── Оптимизация для TrackedSign (B.3) ─────────────────────────
    
    def detect_with_tracking(
        self, 
        frame: np.ndarray, 
        tracked_signs: dict[tuple[int, int], "TrackedSign"],
        skip_ocr: bool = False
    ) -> list[RawDetection]:
        """
        Оптимизированная детекция с учётом трекинга знаков.
        Пропускает CNN классификацию для стабильных знаков.
        
        Args:
            frame: BGR изображение
            tracked_signs: dict {(pixel_x, pixel_y) -> TrackedSign}
            skip_ocr: Если True, OCR не выполняется
        
        Returns:
            Список RawDetection
        """
        # Обычная детекция YOLO bbox + rube
        with profiler.measure("yolo_bbox_detection"):
            raw_boxes = self._find_boxes(frame)
        
        if len(raw_boxes) == 0:
            return []
        
        # Подготовка кропов
        with profiler.measure("batch_prepare_crops"):
            crops_data = []
            
            for box, is_side in raw_boxes:
                x, y, w, h = box
                crop = frame[y: y + h, x: x + w]
                if crop.size == 0:
                    continue
                
                resized = cv2.resize(crop, (32, 32))
                crops_data.append((box, is_side, crop, resized))
        
        if len(crops_data) == 0:
            return []
        
        # Батчинг rube
        with profiler.measure("batch_classify_rube"):
            rube_results = self._classify_rube_batch([cd[3] for cd in crops_data])
        
        valid_crops = []
        for crop_data, yolo_class in zip(crops_data, rube_results):
            if yolo_class is not None:
                valid_crops.append((*crop_data, yolo_class))
        
        if len(valid_crops) == 0:
            return []
        
        # Проверка стабильности для CNN
        cnn_results = []
        cnn_skipped = 0
        
        # BLOCK FIX-2.2: масштабируем радиус с учётом текущего skip
        from configs import config
        _skip_factor = max(1, int(config.CURRENT_EFFECTIVE_SKIP))
        tracking_radius_px = min(50 * _skip_factor, 220)  # потолок - не склеиваем соседние знаки
        
        for box, is_side, crop, resized, yolo_class in valid_crops:
            x, y, w, h = box
            center = (x + w // 2, y + h // 2)
            
            # Ищем TrackedSign рядом с этой позицией (в адаптивном радиусе)
            stable_class = None
            for (tracked_x, tracked_y), tracked_sign in tracked_signs.items():
                # BLOCK FIX-2.2: было "< 50", теперь адаптивный радиус
                if abs(center[0] - tracked_x) < tracking_radius_px and abs(center[1] - tracked_y) < tracking_radius_px:
                    stable_class = tracked_sign.get_stable_cnn_class()
                    if stable_class is not None:
                        cnn_skipped += 1
                        break
            
            if stable_class is not None:
                # Используем стабильный класс без вызова CNN
                # BLOCK CPU-3: Инкрементируем счётчик TrackedSign-skip
                cnn_results.append(stable_class)
                self._tracked_skip_count += 1
            else:
                # Обычная CNN классификация
                cnn_class = self._classify_fine(resized, yolo_class)
                cnn_results.append(cnn_class)
        
        # Выводим статистику пропусков
        if cnn_skipped > 0 and self._counter % 10 == 0:
            total_cnn = len(valid_crops)
            skip_pct = cnn_skipped / total_cnn * 100 if total_cnn > 0 else 0
            logger.debug(f"[TrackedSign-CNN] Пропущено {cnn_skipped}/{total_cnn} "
                        f"CNN вызовов ({skip_pct:.1f}%)")
        
        # Формирование результатов
        results = []
        
        # Fix 2.1: OCR throttling для single_thread режима (Option A)
        # Счётчики для логирования
        ocr_called = 0
        ocr_skipped = 0
        
        for (box, is_side, crop, resized, yolo_class), cnn_class in zip(valid_crops, cnn_results):
            if cnn_class == -1:
                continue
            
            text = ""
            if not skip_ocr:
                # Fix 2.1: Проверяем throttling перед OCR (Option A)
                should_call_ocr = True
                
                # Проверяем нужен ли OCR для этого типа знака
                if self.needs_ocr(cnn_class, yolo_class):
                    # Ищем соответствующий TrackedSign для проверки throttling
                    x, y, w, h = box
                    center = (x + w // 2, y + h // 2)
                    
                    for (tracked_x, tracked_y), tracked_sign in tracked_signs.items():
                        # BLOCK FIX-2.2: было "< 50", теперь используем тот же адаптивный радиус
                        if abs(center[0] - tracked_x) < tracking_radius_px and abs(center[1] - tracked_y) < tracking_radius_px:
                            # Используем текущий abs_frame_number из config
                            from configs import config
                            abs_frame = config.INDEX_OF_All_FRAME
                            
                            # Проверяем throttling
                            if not tracked_sign.should_run_ocr(abs_frame):
                                should_call_ocr = False
                                ocr_skipped += 1
                            else:
                                # Отмечаем что OCR был запрошен
                                tracked_sign.mark_ocr_requested(abs_frame)
                                ocr_called += 1
                            break
                    else:
                        # Новый знак (нет TrackedSign) — всегда делаем OCR
                        ocr_called += 1
                else:
                    # OCR не нужен для этого типа знака
                    should_call_ocr = False
                
                if should_call_ocr:
                    with profiler.measure("ocr_read_text"):
                        text = self._read_text(crop, cnn_class, yolo_class)
            
            color = self.COLORS[self._counter % len(self.COLORS)]
            self._counter += 1
            
            results.append(RawDetection(
                box       = box,
                color     = color,
                yolo_class= yolo_class,
                cnn_class = cnn_class,
                text      = text,
                is_side   = is_side,
            ))
        
        # Логируем статистику OCR throttling (аналогично pipeline режиму)
        if (ocr_called > 0 or ocr_skipped > 0) and self._counter % 10 == 0:
            total_ocr = ocr_called + ocr_skipped
            skip_pct = ocr_skipped / total_ocr * 100 if total_ocr > 0 else 0
            logger.debug(f"[OCR-Throttling] Вызовов: {ocr_called}, Пропущено: {ocr_skipped} ({skip_pct:.1f}%)")
        
        return results