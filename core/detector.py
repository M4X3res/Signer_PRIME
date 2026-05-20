"""
core/detector.py
Detector — обнаружение и классификация знаков на одном кадре.

Рефакторинг оригинального Detector.py:
  1. Модели НЕ грузятся здесь — берутся из configs.sign_models (синглтоны)
  2. Методы разбиты по ответственности: detect → classify → read_text
  3. Типы везде где возможно
  4. LaneDetector не создаётся при каждом вызове
  5. OCR reader — синглтон на уровне модуля
"""
from __future__ import annotations

import difflib
import os
import re
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
from utils import resource_path

# OCR reader — инициализируется лениво при первом вызове
_ocr_reader = None

def _get_ocr():
    global _ocr_reader
    if _ocr_reader is None:
        import easyocr
        _ocr_reader = easyocr.Reader(["be"], gpu=False)
    return _ocr_reader


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
    """

    # Пороги уверенности
    CONF_SIDE    = 0.50
    CONF_RUBE    = 0.70
    CONF_CNN     = 0.60

    COLORS = [
        (0, 255, 0), (0, 0, 255), (255, 0, 0),
        (255, 255, 0), (255, 0, 255), (0, 255, 255),
    ]

    def __init__(self):
        from core.lane_detector import LaneDetector
        self._lane_detector = LaneDetector()
        self._city_names:  list[str] = []
        self._counter = 0

    # ── Главный метод ─────────────────────────────────────────────

    def detect(self, frame: np.ndarray) -> list[RawDetection]:
        """
        Запускает полный пайплайн детекции на одном кадре.
        Возвращает список RawDetection.
        """
        results: list[RawDetection] = []

        # Шаг 1: найти все bbox знаков через model_side_detect
        raw_boxes = self._find_boxes(frame)

        for box, is_side in raw_boxes:
            x, y, w, h = box
            crop = frame[y: y + h, x: x + w]
            if crop.size == 0:
                continue

            resized = cv2.resize(crop, (32, 32))

            # Шаг 2: грубая классификация категории
            yolo_class = self._classify_rube(resized)
            if yolo_class is None:
                continue

            # Шаг 3: точная классификация внутри категории
            cnn_class = self._classify_fine(resized, yolo_class)
            if cnn_class == -1:
                continue

            # Шаг 4: OCR текст если нужен
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
            frame, iou=0.1, conf=self.CONF_SIDE,
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
        """Запускает CNN модель для категории и субкатегории."""
        model  = model_dict[yolo_class]
        output = model(crop32)[0]

        conf = float(output.probs.top1conf.cpu().numpy())
        if conf < self.CONF_CNN:
            return -1

        result_type = output.names[np.argmax(output.probs.data.tolist())]

        # Субклассификация треугольников
        if yolo_class == "treugolnik" and result_type in sub_models:
            sub_out     = sub_models[result_type](crop32)[0]
            result_type = sub_out.names[np.argmax(sub_out.probs.data.tolist())]

        return result_type if result_type else yolo_class

    # ── Шаг 4: OCR ────────────────────────────────────────────────

    def _read_text(
        self,
        crop_orig: np.ndarray,
        cnn_class: str,
        yolo_class: str,
    ) -> str:
        """Читает текст если знак предполагает надпись."""
        if cnn_class in TYPE_SIGNS_WITH_TEXT:
            return self._ocr(crop_orig)

        if yolo_class in NAME_SIGNS_CITY:
            return self._ocr_city(crop_orig)

        return ""

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