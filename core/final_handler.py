"""
core/final_handler.py
FinalHandler — финальная обработка и сохранение знаков в GeoJSON.

Рефакторинг оригинального FinalHandler.py:
  1. Дедупликация O(n²) → O(n) через пространственный индекс (словарь по сетке)
  2. handling_signs / handling_turns разбиты на мелкие методы
  3. Все магические числа — именованные константы
  4. Типы везде
"""
from __future__ import annotations

import uuid
import re
from typing import Optional

import geojson
from geojson import Feature, FeatureCollection, LineString

from core.coordinate_calculation import CoordinateCalculation
from core.converter import Converter
from configs import config
from configs.sign_data import (
    NAME_SIGNS_CITY,
    TYPE_SIGNS_WITH_TEXT,
    CODES_SIGNS,
)
from core.sign import TrackedSign


class FinalHandler:
    # Радиус дедупликации в метрах при финальной обработке
    DEDUP_RADIUS_M    = 20.0
    # Минимальная разница азимутов (градусы) чтобы не считать дублем
    DEDUP_AZIMUTH_DEG = 30.0
    # Размер ячейки пространственной сетки (метры в EPSG:32635)
    GRID_CELL_M       = 20.0

    def __init__(self):
        self._calc      = CoordinateCalculation()
        self._converter = Converter()

    # ── Главный метод ─────────────────────────────────────────────

    def save_result(
        self,
        result_signs: list[TrackedSign],
        turns:        list,
    ) -> None:
        features = (
            self._process_straight_signs(result_signs)
            + self._process_turn_signs(turns)
        )
        features = self._deduplicate(features)

        collection = FeatureCollection(features)
        with open(config.PATH_TO_GEOJSON, "w", encoding="utf-8") as f:
            geojson.dump(collection, f, ensure_ascii=False)

        print(f"[FinalHandler] Сохранено {len(features)} знаков → {config.PATH_TO_GEOJSON}")

    # ── Прямолинейные знаки ───────────────────────────────────────

    def _process_straight_signs(
        self, signs: list[TrackedSign]
    ) -> list[Feature]:
        """Группирует знаки по позиции+стороне, строит линии."""
        grouped = self._group_by_position(signs)
        features: list[Feature] = []

        for items in grouped.values():
            coefficient = 2
            for sign in items:
                feature = self._sign_to_feature(sign, coefficient)
                if feature:
                    features.append(feature)
                coefficient += 1

        return features

    def _group_by_position(
        self, signs: list[TrackedSign]
    ) -> dict[str, list[TrackedSign]]:
        """
        Группирует знаки стоящие на одном столбе/месте.
        Ключ: последняя координата автомобиля + сторона.
        Также разворачивает составные знаки 5.8 (A-B → [A, B]).
        """
        groups: dict[str, list[TrackedSign]] = {}

        for sign in signs:
            if sign.best_yolo == "5.8":
                expanded = self._expand_lane_sign(sign)
                for s in expanded:
                    key = f"{s.car_x[-1]:.0f}_{s.is_left}"
                    groups.setdefault(key, []).append(s)
            else:
                key = f"{sign.car_x[-1]:.0f}_{sign.is_left}"
                groups.setdefault(key, []).append(sign)

        return groups

    def _expand_lane_sign(self, sign: TrackedSign) -> list[TrackedSign]:
        """
        Знак 5.8 может содержать несколько типов через '-'
        (напр. '4.1.1-4.1.2'). Разворачиваем в отдельные знаки.
        """
        import copy
        type_str = sign.best_cnn
        if "-" not in type_str:
            sign.is_left = False
            return [sign]

        types = list(set(type_str.split("-")))
        result = []
        for t in types:
            clone = copy.copy(sign)
            clone.cnn_results  = [t]
            clone.yolo_results = [t]
            clone.is_left      = False
            result.append(clone)
        return result

    def _snap_sign_coords(self, sign: TrackedSign) -> None:
        """
        Привязывает координаты знака к ближайшему ребру дороги OSM.
        Обновляет sign.azimuth если snap прошёл успешно.
        """
        if not sign.car_x:
            return
        try:
            from core.converter import Converter
            conv = Converter()
            lat, lon = conv.coordinateConverter(
                sign.car_x[-1], sign.car_y[-1],
                "epsg:32635", "epsg:4326",
            )
            from core.osm_snap import snap_sign
            result = snap_sign(lat, lon, radius_m=30)
            if result.snapped:
                sign.azimuth = result.azimuth
        except Exception as e:
            print(f"[FinalHandler] OSM snap error: {e}")

    def _sign_to_feature(
        self, sign: TrackedSign, coefficient: int
    ) -> Optional[Feature]:
        """Строит GeoJSON Feature для одного знака."""
        self._snap_sign_coords(sign)
        try:
            x1, y1, x2, y2 = self._calc.get_line(sign, coefficient)
        except Exception as e:
            print(f"[FinalHandler] get_line error: {e}")
            return None

        # Корректируем азимут для боковых знаков
        if sign.best_side:
            sign.azimuth = (
                (sign.azimuth - 90) % 360
                if sign.is_left
                else (sign.azimuth + 90) % 360
            )

        return self._build_feature(x1, y1, x2, y2, sign)

    # ── Знаки на поворотах ────────────────────────────────────────

    def _process_turn_signs(self, turns: list) -> list[Feature]:
        features: list[Feature] = []

        # Позиции на повороте → точка расчёта
        TURN_POSITIONS = {
            "0": "start",  "1": "start",  "2": "start",
            "3": "rev_end","4": "rev_end","5": "rev_start",
            "5.1":"rev_start","6":"rev_start",
            "7": "rev_end","8": "rev_end",
        }

        for turn in turns:
            dots = self._calc.calculation_four_dots(turn)
            if not dots:
                continue
            start, end, rev_start, rev_end = dots

            dot_map = {
                "start":     start,
                "rev_end":   rev_end,
                "rev_start": rev_start,
            }

            grouped: dict[str, list[TrackedSign]] = {}
            for sign in turn.signs:
                if sign.best_yolo == "5.8":
                    continue
                grouped.setdefault(str(sign.number), []).append(sign)

            for pos_key, items in grouped.items():
                dot_name = TURN_POSITIONS.get(pos_key, "start")
                x_cur, y_cur, x_prv, y_prv, azimuth = dot_map[dot_name]

                x_cur, y_cur = self._converter.coordinateConverter(
                    x_cur, y_cur, "epsg:4326", "epsg:32635"
                )
                x_prv, y_prv = self._converter.coordinateConverter(
                    x_prv, y_prv, "epsg:4326", "epsg:32635"
                )

                coefficient = 2
                for sign in items:
                    sign.azimuth = azimuth
                    x1, y1, x2, y2 = CoordinateCalculation.calculate_result_line(
                        sign, coefficient,
                        x_cur, y_cur, x_prv, y_prv,
                    )
                    x1, y1 = self._converter.coordinateConverter(
                        x1, y1, "epsg:32635", "epsg:4326"
                    )
                    x2, y2 = self._converter.coordinateConverter(
                        x2, y2, "epsg:32635", "epsg:4326"
                    )
                    feat = self._build_feature(x1, y1, x2, y2, sign)
                    if feat:
                        features.append(feat)
                    coefficient += 1

        return features

    # ── Дедупликация O(n) ─────────────────────────────────────────

    def _deduplicate(self, features: list[Feature]) -> list[Feature]:
        """
        Убирает дубли используя пространственную сетку.
        O(n) вместо O(n²) оригинала.

        Два знака считаются дублями если:
          - одинаковый тип
          - одинаковая сторона (left/right)
          - расстояние < DEDUP_RADIUS_M
          - разница азимутов < DEDUP_AZIMUTH_DEG
        """
        # Словарь: (cell_x, cell_y, type, side) → Feature
        grid: dict[tuple, Feature] = {}
        result: list[Feature] = []

        for feat in features:
            p     = feat["properties"]
            coords= feat["geometry"]["coordinates"]
            if not coords:
                result.append(feat)
                continue

            lon, lat = coords[0][0], coords[0][1]
            # Конвертируем в EPSG:32635 для расстояний
            try:
                cx, cy = self._converter.coordinateConverter(
                    lat, lon, "epsg:4326", "epsg:32635"
                )
            except Exception:
                result.append(feat)
                continue

            cell_x = int(cx // self.GRID_CELL_M)
            cell_y = int(cy // self.GRID_CELL_M)
            ftype  = p.get("type", "")
            side   = p.get("left", "")

            # Проверяем текущую и соседние ячейки
            is_dup = False
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    key = (cell_x + dx, cell_y + dy, ftype, side)
                    if key not in grid:
                        continue
                    existing = grid[key]
                    ep       = existing["properties"]

                    # Проверяем расстояние точно
                    dist = self._feature_distance_m(feat, existing)
                    if dist > self.DEDUP_RADIUS_M:
                        continue

                    # Проверяем азимут
                    az_diff = abs(
                        float(p.get("azimuth", 0))
                        - float(ep.get("azimuth", 0))
                    )
                    if az_diff > self.DEDUP_AZIMUTH_DEG:
                        continue

                    # Дубль — оставляем длиннее
                    if self._feature_length(feat) > self._feature_length(existing):
                        grid[key] = feat
                    is_dup = True
                    break
                if is_dup:
                    break

            if not is_dup:
                grid[(cell_x, cell_y, ftype, side)] = feat
                result.append(feat)

        return result

    def _feature_distance_m(self, a: Feature, b: Feature) -> float:
        """Расстояние между первыми точками двух Feature в метрах."""
        try:
            ca = a["geometry"]["coordinates"][0]
            cb = b["geometry"]["coordinates"][0]
            ax, ay = self._converter.coordinateConverter(
                ca[1], ca[0], "epsg:4326", "epsg:32635"
            )
            bx, by = self._converter.coordinateConverter(
                cb[1], cb[0], "epsg:4326", "epsg:32635"
            )
            return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5
        except Exception:
            return float("inf")

    def _feature_length(self, feat: Feature) -> int:
        """Длина знака — число наблюдений из properties."""
        try:
            return int(feat["properties"].get("length", 0))
        except Exception:
            return 0

    # ── Построение Feature ────────────────────────────────────────

    def _build_feature(
        self,
        x1: float, y1: float,
        x2: float, y2: float,
        sign: TrackedSign,
    ) -> Optional[Feature]:
        """Создаёт GeoJSON Feature из знака и координат линии."""
        type_sign = sign.best_cnn
        if type_sign not in CODES_SIGNS:
            return None

        # Видео и время
        avg_frame   = (
            sum(sign.abs_frame_numbers) / len(sign.abs_frame_numbers)
            if sign.abs_frame_numbers else 0
        )
        video_idx   = int(avg_frame // 63600)
        frame_local = int(avg_frame % 63600)
        video_name  = (
            config.VIDEOS[video_idx]
            if config.VIDEOS and video_idx < len(config.VIDEOS)
            else "unknown"
        )
        minute  = frame_local // 3600
        seconds = (frame_local // 60) % 60
        time_str = f"{minute}:{seconds:02d}"

        # Текст на знаке
        if sign.best_yolo in NAME_SIGNS_CITY:
            text = sign.best_city_name()
        elif len(sign.text_results) > 4:
            text = sign.most_common(sign.text_results)[0]
        else:
            text = ""

        line = LineString([(y1, x1), (y2, x2)])

        props: dict = {
            "type":                  type_sign,
            "length":                str(sign.observation_count),
            "side":                  str(sign.side_results),
            "turn":                  sign.turn_direction,
            "left":                  str(sign.is_left),
            "num":                   str(sign.number_sign),
            "pixel_coordinates_x":   str(sign.pixel_x),
            "pixel_coordinates_y":   str(sign.pixel_y),
            "h":                     str(sign.heights),
            "w":                     str(sign.widths),
            "car_coordinates_x":     str(sign.car_x),
            "car_coordinates_y":     str(sign.car_y),
            "frame_numbers":         str(sign.frame_numbers),
            "absolute_frame_numbers":str(sign.abs_frame_numbers),
            "azimuth":               str(sign.azimuth),
            "id":                    str(uuid.uuid4()),
            "time":                  time_str,
            "name_video":            video_name,
            "code":                  int(CODES_SIGNS[type_sign]),
        }

        if type_sign in TYPE_SIGNS_WITH_TEXT:
            props["MVALUE"] = text
            props["SEM250"] = text

        return Feature(geometry=line, properties=props)