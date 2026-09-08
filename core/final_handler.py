"""
core/final_handler.py
FinalHandler — финальная обработка и сохранение знаков в GeoJSON.

Рефакторинг оригинального FinalHandler.py:
  1. Дедупликация O(n^2) -> O(n) через пространственный индекс (словарь по сетке)
  2. handling_signs / handling_turns разбиты на мелкие методы
  3. Все магические числа — именованные константы
  4. Типы везде
"""
from __future__ import annotations

import uuid
import re
import logging
from typing import Optional

import geojson
from geojson import Feature, FeatureCollection, LineString

logger = logging.getLogger(__name__)

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
    def __init__(self, settings=None):
        """
        Инициализирует FinalHandler.
        
        Args:
            settings: AppSettings или None (используются defaults)
        """
        # Загружаем настройки
        if settings is None:
            from configs.settings import get_app_settings
            settings = get_app_settings()
        
        # Применяем настройки дедупликации
        self.DEDUP_RADIUS_M = settings.dedup_radius_final_m
        self.DEDUP_AZIMUTH_DEG = settings.dedup_azimuth_deg
        
        # BLOCK N.1: Размер ячейки сетки не больше половины радиуса дедупликации
        # Гарантирует, что окно поиска соседних ячеек покрывает весь заявленный радиус
        self.GRID_CELL_M = max(10.0, self.DEDUP_RADIUS_M / 2.0)
        
        self._calc      = CoordinateCalculation()
        self._converter = Converter()
        
        logger.info(f"[FinalHandler] Инициализирован: DEDUP_RADIUS_M={self.DEDUP_RADIUS_M:.1f}m, "
                    f"DEDUP_AZIMUTH_DEG={self.DEDUP_AZIMUTH_DEG:.1f}°, "
                    f"GRID_CELL_M={self.GRID_CELL_M:.1f}m")

    # ── Главный метод ─────────────────────────────────────────────

    def save_result(
        self,
        result_signs: list[TrackedSign],
        turns:        list,
        progress_cb=None,  # Optional[Callable[[int, int, str], None]] = None
    ) -> int:
        """
        Сохраняет результаты обработки в GeoJSON.
        
        Args:
            result_signs: Список обнаруженных знаков
            turns: Список поворотов
            progress_cb: Опциональный callback для отображения прогресса (current, total, stage)
        
        Returns:
            Количество знаков (features), реально записанных в GeoJSON.
        """
        logger.info(f"[FinalHandler] save_result вызван:")
        logger.info(f"  - Знаков: {len(result_signs)}")
        logger.info(f"  - Поворотов: {len(turns)}")
        logger.info(f"  - Путь: {config.PATH_TO_GEOJSON}")
        
        if not config.PATH_TO_GEOJSON:
            logger.error("[FinalHandler] ERROR: PATH_TO_GEOJSON пустой!")
            raise ValueError("PATH_TO_GEOJSON не установлен")
        
        total_signs = len(result_signs) + len(turns)
        
        try:
            if progress_cb:
                progress_cb(0, total_signs, "Обработка знаков...")
            
            logger.info("[FinalHandler] Начинаем обработку прямолинейных знаков...")
            features = self._process_straight_signs(result_signs, progress_cb, total_signs)
            logger.info(f"[FinalHandler] Обработано {len(features)} прямолинейных знаков")
        except Exception as e:
            logger.exception("[FinalHandler] ОШИБКА в _process_straight_signs")
            features = []
        
        try:
            if progress_cb:
                progress_cb(len(result_signs), total_signs, "Обработка поворотов...")
            
            logger.info("[FinalHandler] Начинаем обработку знаков на поворотах...")
            turn_features = self._process_turn_signs(turns, progress_cb, len(result_signs), total_signs)
            logger.info(f"[FinalHandler] Обработано {len(turn_features)} знаков на поворотах")
            features += turn_features
        except Exception as e:
            logger.error(f"[FinalHandler] ОШИБКА в _process_turn_signs: {e}")
            import traceback
            traceback.print_exc()
        
        logger.info(f"[FinalHandler] После обработки: {len(features)} features")
        
        try:
            logger.info("[FinalHandler] Начинаем дедупликацию...")
            features = self._deduplicate(features)
            logger.info(f"[FinalHandler] После дедупликации: {len(features)} features")
        except Exception as e:
            logger.error(f"[FinalHandler] ОШИБКА в _deduplicate: {e}")
            import traceback
            traceback.print_exc()

        try:
            logger.info("[FinalHandler] Сохраняем GeoJSON...")
            collection = FeatureCollection(features)
            with open(config.PATH_TO_GEOJSON, "w", encoding="utf-8") as f:
                geojson.dump(collection, f, ensure_ascii=False)
            logger.info(f"[FinalHandler] Сохранено {len(features)} знаков → {config.PATH_TO_GEOJSON}")
        except Exception as e:
            logger.exception("[FinalHandler] ОШИБКА при сохранении файла")
            raise
        
        # BLOCK SIGN-LOSS-3: итоговая сводка для диагностики потерь
        total_input = len(result_signs) + sum(len(t.signs) for t in turns)
        logger.info(
            f"[FinalHandler] ИТОГ: на входе знаков≈{total_input}, "
            f"после обработки и дедупликации записано {len(features)} features "
            f"→ {config.PATH_TO_GEOJSON}"
        )
        if len(features) < total_input * 0.5 and total_input > 0:
            logger.error(
                f"[FinalHandler] ВНИМАНИЕ: в файл попало менее половины знаков "
                f"({len(features)} из ~{total_input}). Проверь лог выше на ошибки этапов."
            )
        
        return len(features)

    # ── Прямолинейные знаки ───────────────────────────────────────

    def _validate_signs_for_processing(self, signs: list[TrackedSign]) -> list[TrackedSign]:
        """
        BLOCK SIGN-LOSS-3: отфильтровывает знаки без валидных координат автомобиля,
        чтобы одна повреждённая запись не приводила к потере ВСЕХ остальных знаков
        в этом пакете (см. _batch_snap_signs — там раньше падал IndexError на
        sign.car_x[-1] для всего списка целиком).
        """
        valid, skipped = [], []
        for sign in signs:
            if not sign.car_x or not sign.car_y:
                skipped.append(sign)
                continue
            valid.append(sign)

        if skipped:
            logger.warning(
                f"[FinalHandler] Пропущено {len(skipped)} знаков без car_x/car_y "
                f"(типы: {[s.best_cnn for s in skipped]}) — не могут быть привязаны к карте"
            )
        return valid

    def _process_straight_signs(
        self, signs: list[TrackedSign], progress_cb=None, total_signs=0
    ) -> list[Feature]:
        """Группирует знаки по позиции+стороне, строит линии."""
        logger.info(f"[FinalHandler] _process_straight_signs: обрабатываем {len(signs)} знаков")
        
        # BLOCK SIGN-LOSS-3: валидация входных данных ДО batch snap
        signs = self._validate_signs_for_processing(signs)
        if not signs:
            logger.warning("[FinalHandler] Нет валидных знаков после фильтрации")
            return []
        
        try:
            grouped = self._group_by_position(signs)
            logger.info(f"[FinalHandler] Сгруппировано в {len(grouped)} групп")
        except Exception as e:
            logger.error(f"[FinalHandler] ОШИБКА в _group_by_position: {e}")
            return []
        
        # Batch OSM snap (D.1) — загружаем дороги один раз для всех знаков
        logger.info("[FinalHandler] Выполняем batch OSM snap...")
        all_signs = [sign for items in grouped.values() for sign in items]
        snap_results = self._batch_snap_signs(all_signs, progress_cb, total_signs)
        
        # BLOCK I.2: Второй проход мержа дублей ПОСЛЕ snap
        from configs.settings import get_app_settings
        settings = get_app_settings()
        logger.info("[FinalHandler] Второй проход мержа дублей (post-snap)...")
        all_signs, snap_results = self._merge_duplicates_post_snap(all_signs, snap_results, settings)
        
        # Создаём map sign -> snap_result для быстрого доступа
        sign_to_snap = {id(sign): result for sign, result in zip(all_signs, snap_results)}
        
        # BLOCK I.3: Перегруппируем знаки после post-snap merge и сортируем по distance_m
        logger.info("[FinalHandler] Перегруппировка и сортировка по cross-track distance...")
        grouped_post_snap = self._regroup_by_position(all_signs)
        
        features: list[Feature] = []
        processed_count = 0

        for group_key, group_signs in grouped_post_snap.items():
            # BLOCK I.3: Сортируем знаки внутри группы по distance_m (от дороги)
            # Знаки ближе к дороге получают меньший coefficient
            sorted_signs = self._sort_signs_by_distance(group_signs, sign_to_snap)
            
            coefficient = 2
            for sign in sorted_signs:
                try:
                    snap_result = sign_to_snap.get(id(sign))
                    feature = self._sign_to_feature_with_snap(sign, coefficient, snap_result)
                    if feature:
                        features.append(feature)
                    coefficient += 1
                    processed_count += 1
                    
                    # Обновляем прогресс каждые 20 знаков
                    if progress_cb and processed_count % 20 == 0:
                        progress_cb(processed_count, total_signs, f"Построение линий... {processed_count}/{len(all_signs)}")
                        
                except Exception as e:
                    logger.info(f"[FinalHandler] Ошибка обработки знака {sign.best_cnn}: {e}")
                    # Продолжаем обработку остальных знаков

        logger.info(f"[FinalHandler] _process_straight_signs завершён: {len(features)} features")
        return features
    
    def _regroup_by_position(self, signs: list[TrackedSign]) -> dict[str, list[TrackedSign]]:
        """
        BLOCK I.3: Перегруппировка знаков после post-snap merge.
        Группирует по округлённым координатам (без учёта is_left в ключе — Шаг I.4).
        
        Args:
            signs: Список знаков после post-snap merge
        
        Returns:
            Dict с ключом "x_y" (округлённые координаты) и списком знаков
        """
        # BLOCK I.4: Ослабленный ключ группировки - только позиция (без is_left)
        # Округление до ~5 метров
        groups = {}
        for sign in signs:
            if not sign.car_x or not sign.car_y:
                continue
            
            # Округление до 5 метров
            x_rounded = round(sign.car_x[-1] / 5.0) * 5
            y_rounded = round(sign.car_y[-1] / 5.0) * 5
            key = f"{x_rounded:.0f}_{y_rounded:.0f}"
            
            groups.setdefault(key, []).append(sign)
        
        return groups
    
    def _sort_signs_by_distance(
        self, 
        signs: list[TrackedSign],
        sign_to_snap: dict
    ) -> list[TrackedSign]:
        """
        BLOCK I.3: Сортирует знаки по расстоянию от дороги (distance_m).
        
        Знаки ближе к дороге идут первыми (получат меньший coefficient).
        Знаки с неудавшимся snap или без данных о расстоянии — в конец списка.
        
        Args:
            signs: Список знаков в одной группе
            sign_to_snap: Маппинг id(sign) -> SnapResult
        
        Returns:
            Отсортированный список знаков
        """
        def get_distance(sign):
            snap_result = sign_to_snap.get(id(sign))
            if snap_result and snap_result.snapped and snap_result.distance_m >= 0:
                return snap_result.distance_m
            else:
                return float('inf')  # Знаки без snap — в конец
        
        return sorted(signs, key=get_distance)

    def _group_by_position(
        self, signs: list[TrackedSign]
    ) -> dict[str, list[TrackedSign]]:
        """
        Группирует знаки стоящие на одном столбе/месте.
        Ключ: последняя координата автомобиля + сторона.
        Также разворачивает составные знаки 5.8 (A-B → [A, B]).
        
        ЗАДАЧА 1: Улучшена логика - перед группировкой мержит реальные дубликаты
        и разделяет знаки на противоположных сторонах широких дорог.
        """
        from configs.settings import get_app_settings
        settings = get_app_settings()
        
        # Разворачиваем составные знаки 5.8
        expanded_signs = []
        for sign in signs:
            if sign.best_yolo == "5.8":
                expanded = self._expand_lane_sign(sign)
                expanded_signs.extend(expanded)
            else:
                expanded_signs.append(sign)
        
        # ЗАДАЧА 1.2: Мержим реальные дубликаты перед группировкой
        merged_signs = self._merge_duplicate_signs(expanded_signs, settings)
        
        logger.info(f"[FinalHandler] После merge дубликатов: {len(signs)} → {len(merged_signs)} знаков")
        
        # Группируем по позиции
        groups: dict[str, list[TrackedSign]] = {}
        for sign in merged_signs:
            key = f"{sign.car_x[-1]:.0f}_{sign.is_left}"
            groups.setdefault(key, []).append(sign)

        return groups
    
    def _merge_duplicate_signs(
        self, 
        signs: list[TrackedSign],
        settings
    ) -> list[TrackedSign]:
        """
        ЗАДАЧА 1.2: Мержит повторные детекции одного и того же физического знака.
        
        Два знака считаются дубликатами если:
        - Одинаковый best_cnn (тип знака)
        - Близкие координаты (< duplicate_merge_distance_m)
        - Близкие азимуты (< duplicate_azimuth_diff_deg)
        - Перекрытие по времени наблюдения (abs_frame_numbers)
        """
        if not signs:
            return []
        
        merged: list[TrackedSign] = []
        used: set[int] = set()
        
        for i, sign1 in enumerate(signs):
            if i in used:
                continue
            
            # Ищем дубликаты для sign1
            duplicates = [sign1]
            used.add(i)
            
            for j, sign2 in enumerate(signs[i+1:], start=i+1):
                if j in used:
                    continue
                
                if self._are_duplicates(sign1, sign2, settings):
                    duplicates.append(sign2)
                    used.add(j)
            
            # Мержим если нашли дубликаты
            if len(duplicates) > 1:
                merged_sign = self._merge_signs(duplicates)
                merged.append(merged_sign)
            else:
                merged.append(sign1)
        
        return merged
    
    def _are_duplicates(
        self, 
        sign1: TrackedSign, 
        sign2: TrackedSign,
        settings
    ) -> bool:
        """
        Проверяет являются ли два знака повторными детекциями одного физического знака.
        """
        # Разные типы знаков - не дубликаты
        if sign1.best_cnn != sign2.best_cnn:
            return False
        
        # Разные стороны - не дубликаты
        if sign1.is_left != sign2.is_left:
            return False
        
        # Проверяем расстояние между последними позициями
        if sign1.car_x and sign2.car_x:
            dx = sign1.car_x[-1] - sign2.car_x[-1]
            dy = sign1.car_y[-1] - sign2.car_y[-1]
            dist = (dx*dx + dy*dy) ** 0.5
            
            if dist > settings.duplicate_merge_distance_m:
                return False
        
        # Проверяем разницу в азимутах
        az_diff = abs(sign1.azimuth - sign2.azimuth)
        if az_diff > 180:
            az_diff = 360 - az_diff
        
        if az_diff > settings.duplicate_azimuth_diff_deg:
            return False
        
        # Проверяем перекрытие по времени (кадрам)
        frames1 = set(sign1.abs_frame_numbers) if sign1.abs_frame_numbers else set()
        frames2 = set(sign2.abs_frame_numbers) if sign2.abs_frame_numbers else set()
        
        if not frames1 or not frames2:
            # Если нет данных о кадрах - считаем дубликатами
            return True
        
        # Проверяем перекрытие или близость
        overlap = len(frames1 & frames2)
        if overlap > 0:
            return True
        
        # Проверяем близость по времени
        min1, max1 = min(frames1), max(frames1)
        min2, max2 = min(frames2), max(frames2)
        
        time_gap = min(abs(min1 - max2), abs(min2 - max1))
        if time_gap <= settings.duplicate_time_overlap_frames:
            return True
        
        return False
    
    def _merge_signs(self, signs: list[TrackedSign]) -> TrackedSign:
        """
        Объединяет несколько дубликатов в один знак (как TrackedSign.merge).
        """
        if len(signs) == 1:
            return signs[0]
        
        # Берём первый как базу
        result = signs[0]
        
        # Мержим данные из остальных
        for sign in signs[1:]:
            result.pixel_x.extend(sign.pixel_x)
            result.pixel_y.extend(sign.pixel_y)
            result.widths.extend(sign.widths)
            result.heights.extend(sign.heights)
            result.bbox_centers_x.extend(sign.bbox_centers_x)
            result.bbox_centers_y.extend(sign.bbox_centers_y)
            result.car_x.extend(sign.car_x)
            result.car_y.extend(sign.car_y)
            result.frame_numbers.extend(sign.frame_numbers)
            result.abs_frame_numbers.extend(sign.abs_frame_numbers)
            result.yolo_results.extend(sign.yolo_results)
            result.cnn_results.extend(sign.cnn_results)
            result.side_results.extend(sign.side_results)
            result.text_results.extend(sign.text_results)
        
        # best_* атрибуты пересчитываются автоматически через @property
        # при обращении к result.best_yolo, result.best_cnn, result.best_side
        
        return result

    def _batch_snap_signs(
        self, 
        signs: list[TrackedSign], 
        progress_cb=None, 
        total_signs=0
    ) -> list:
        """
        Batch OSM snap для списка знаков (D.1).
        """
        from core.osm_snap import OSMSnapper
        
        if not signs:
            return []
        
        # Получаем координаты всех знаков для batch snap
        points = [(sign.car_y[-1], sign.car_x[-1]) for sign in signs]  # (lat, lon)
        
        # Batch snap через OSMSnapper
        snapper = OSMSnapper()
        snap_results = snapper.snap_batch(points, radius_m=30)
        
        if progress_cb:
            progress_cb(len(signs), total_signs, f"OSM snap завершён для {len(signs)} знаков")
        
        return snap_results
    
    def _merge_duplicates_post_snap(
        self,
        signs: list[TrackedSign],
        snap_results: list,
        settings
    ) -> tuple[list[TrackedSign], list]:
        """
        BLOCK I.2: Второй проход мержа дублей ПОСЛЕ OSM snap.
        
        Вызывается после _batch_snap_signs, но ДО построения финальных Feature.
        Критерии дубля во втором проходе (более строгие благодаря snap):
        - Одинаковый best_cnn (тип знака)
        - Одинаковый way_id из snap_result (на той же дороге)
        - abs(distance_m_a - distance_m_b) < 3.0м (похожее удаление от дороги)
        - Разница азимутов < settings.duplicate_azimuth_diff_deg
        - is_left НЕ участвует (уже пересчитан геометрически в Шаге I.1)
        
        Args:
            signs: Список знаков после первого прохода мержа
            snap_results: Результаты batch snap (в том же порядке что и signs)
            settings: AppSettings
        
        Returns:
            Tuple (merged_signs, merged_snap_results) с синхронизированными индексами
        """
        if not signs or len(signs) != len(snap_results):
            logger.warning(f"[FinalHandler] _merge_duplicates_post_snap: signs/snap_results mismatch")
            return signs, snap_results
        
        logger.info(f"[FinalHandler] Второй проход мержа дублей: {len(signs)} знаков")
        
        merged_signs = []
        merged_snaps = []
        used = set()
        
        for i, sign1 in enumerate(signs):
            if i in used:
                continue
            
            snap1 = snap_results[i]
            duplicates_indices = [i]
            used.add(i)
            
            # Ищем дубликаты для sign1
            for j, sign2 in enumerate(signs[i+1:], start=i+1):
                if j in used:
                    continue
                
                snap2 = snap_results[j]
                
                if self._are_duplicates_post_snap(sign1, sign2, snap1, snap2, settings):
                    duplicates_indices.append(j)
                    used.add(j)
            
            # Мержим если нашли дубликаты
            if len(duplicates_indices) > 1:
                logger.debug(f"[FinalHandler] Post-snap merge: {len(duplicates_indices)} дубликатов знака {sign1.best_cnn}")
                duplicate_signs = [signs[idx] for idx in duplicates_indices]
                duplicate_snaps = [snap_results[idx] for idx in duplicates_indices]
                
                merged_sign = self._merge_signs(duplicate_signs)
                # Выбираем snap с наименьшим distance_m (ближайший к дороге)
                best_snap = min(duplicate_snaps, key=lambda s: s.distance_m if s.snapped else float('inf'))
                
                merged_signs.append(merged_sign)
                merged_snaps.append(best_snap)
            else:
                merged_signs.append(sign1)
                merged_snaps.append(snap1)
        
        logger.info(f"[FinalHandler] После post-snap merge: {len(signs)} → {len(merged_signs)} знаков")
        return merged_signs, merged_snaps
    
    def _are_duplicates_post_snap(
        self,
        sign1: TrackedSign,
        sign2: TrackedSign,
        snap1,
        snap2,
        settings
    ) -> bool:
        """
        BLOCK I.2: Проверка дубликатов с учётом OSM snap данных.
        
        Более строгие критерии чем в первом проходе:
        - Snap должен быть успешен у обоих знаков
        - Они должны быть на одной дороге (way_id совпадает через road_name)
        - Похожее расстояние от дороги
        - Похожий азимут
        """
        # Разные типы знаков - не дубликаты
        if sign1.best_cnn != sign2.best_cnn:
            return False
        
        # Если snap не удался хотя бы у одного - не можем надёжно определить
        if not snap1.snapped or not snap2.snapped:
            return False
        
        # Должны быть на одной дороге (используем road_name как proxy для way_id)
        if snap1.road_name != snap2.road_name:
            # Если нет названия дороги - проверяем близость координат snap-точек
            if not snap1.road_name or not snap2.road_name:
                # Расстояние между snap-точками должно быть мало
                from core.osm_snap import OSMSnapper
                dist = OSMSnapper._haversine(snap1.lat, snap1.lon, snap2.lat, snap2.lon)
                if dist > 10.0:  # 10 метров
                    return False
            else:
                return False
        
        # Похожее удаление от дороги (cross-track distance)
        distance_diff = abs(snap1.distance_m - snap2.distance_m)
        if distance_diff > 3.0:  # 3 метра
            return False
        
        # Похожий азимут (используем snap азимут, не GPS)
        az_diff = abs(snap1.azimuth - snap2.azimuth)
        if az_diff > 180:
            az_diff = 360 - az_diff
        
        if az_diff > settings.duplicate_azimuth_diff_deg:
            return False
        
        # is_left НЕ проверяем - после геометрического пересчёта он корректен
        # и не должен различаться у дубликатов на одной дороге
        
        return True

    def _sign_to_feature_with_snap(
        self, 
        sign: TrackedSign, 
        coefficient: int,
        snap_result
    ) -> Optional[Feature]:
        """
        Строит GeoJSON Feature для знака используя pre-snapped результат.
        
        ЗАДАЧА 1.1: Офсет (coefficient) теперь ограничен реальной шириной дороги.
        """
        from configs.settings import get_app_settings
        settings = get_app_settings()
        
        # Вычисляем ширину дороги
        road_width_m = self._estimate_road_width(snap_result, settings)
        
        # Ограничиваем coefficient чтобы офсет не выходил за пределы дороги
        max_coefficient = self._calc_max_coefficient(road_width_m, settings)
        effective_coefficient = min(coefficient, max_coefficient)
        
        if effective_coefficient != coefficient:
            logger.debug(f"[FinalHandler] Офсет ограничен: {coefficient} → {effective_coefficient} (road_width={road_width_m:.1f}m)")
        
        # Используем результат batch snap
        if snap_result and snap_result.snapped:
            gpx_azimuth = sign.azimuth  # Сохраняем оригинальный
            sign.azimuth = snap_result.azimuth
            
            # BLOCK I.1.4: Пересчитываем is_left геометрически через OSM snap
            if snap_result.side_relative_to_way is not None:
                # Определяем направление движения автомобиля относительно way
                # Сравниваем GPX-азимут машины и азимут way
                azimuth_diff = abs(gpx_azimuth - snap_result.azimuth)
                if azimuth_diff > 180:
                    azimuth_diff = 360 - azimuth_diff
                
                # Если машина едет примерно в том же направлении что и way (разница < 90°)
                # — используем side_relative_to_way как есть
                # Если машина едет в обратном направлении (разница > 90°)
                # — инвертируем side_relative_to_way
                if azimuth_diff < 90:
                    # Машина едет вдоль way
                    sign.is_left = snap_result.side_relative_to_way
                else:
                    # Машина едет против way — инвертируем сторону
                    sign.is_left = not snap_result.side_relative_to_way
                
                logger.debug(f"[FinalHandler] Геометрический is_left: {sign.is_left} "
                            f"(side_relative_to_way={snap_result.side_relative_to_way}, "
                            f"azimuth_diff={azimuth_diff:.1f}°)")
            # Если side_relative_to_way == None, оставляем is_left из пиксельной эвристики (fallback)
            
            # Сохраняем информацию о дороге в знаке для метрики уверенности
            sign.snap_distance = snap_result.distance_m
            sign.road_lanes = snap_result.lanes
            sign.road_width_m = snap_result.width
            
            sign.calc_confidence(
                snap_dist_m=snap_result.distance_m,
                osm_azimuth=snap_result.azimuth,
                gpx_azimuth=gpx_azimuth
            )
        else:
            # Snap не удался - используем GPX данные
            sign.calc_confidence(
                snap_dist_m=-1.0,
                osm_azimuth=None,
                gpx_azimuth=sign.azimuth
            )
        
        # Остальная логика как раньше
        try:
            x1, y1, x2, y2 = self._calc.get_line(sign, effective_coefficient)
        except Exception as e:
            logger.info(f"[FinalHandler] get_line error: {e}")
            return None

        # Корректируем азимут для боковых знаков
        if sign.best_side:
            sign.azimuth = (
                (sign.azimuth - 90) % 360
                if sign.is_left
                else (sign.azimuth + 90) % 360
            )

        # Строим Feature
        return self._build_feature(x1, y1, x2, y2, sign)
    
    def _estimate_road_width(self, snap_result, settings) -> float:
        """
        ЗАДАЧА 1.1: Оценивает ширину дороги на основе OSM данных или дефолтов.
        
        Returns:
            Ширина дороги в метрах
        """
        # Приоритет 1: Если есть явная ширина в OSM
        if snap_result and snap_result.width:
            return snap_result.width
        
        # Приоритет 2: Вычисляем из количества полос
        if snap_result and snap_result.lanes:
            return snap_result.lanes * settings.default_lane_width_m
        
        # Приоритет 3: Дефолтная оценка
        return settings.default_lanes_count * settings.default_lane_width_m
    
    def _calc_max_coefficient(self, road_width_m: float, settings) -> int:
        """
        ЗАДАЧА 1.1: Вычисляет максимально допустимый coefficient на основе ширины дороги.
        
        coefficient определяет смещение знака перпендикулярно треку.
        Каждый следующий coefficient добавляет примерно 5м смещения (см. coordinate_calculation.py).
        
        Returns:
            Максимальное значение coefficient
        """
        # Максимальное смещение = половина ширины дороги * multiplier
        # (половина т.к. знаки могут быть с обеих сторон)
        max_offset_m = (road_width_m / 2.0) * settings.max_offset_multiplier
        
        # Каждый coefficient ~= 5м смещения (из _line_straight → point_at_distance = 5м)
        approx_offset_per_coef = 5.0
        
        # coefficient начинается с 2, поэтому макс = 2 + число дополнительных офсетов
        max_coef = 2 + int(max_offset_m / approx_offset_per_coef)
        
        # Минимум 2 (хотя бы один знак в группе)
        return max(2, max_coef)

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
        Вызывает calc_confidence() для вычисления метрик уверенности.
        
        С таймаутом 2 секунды для предотвращения зависаний.
        """
        if not sign.car_x:
            return
        
        # Сохраняем оригинальный GPX азимут ДО snap
        gpx_azimuth = sign.azimuth
        
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
                # Вызываем calc_confidence с данными snap
                sign.calc_confidence(
                    snap_dist_m=result.distance_m,
                    osm_azimuth=result.azimuth,
                    gpx_azimuth=gpx_azimuth
                )
            else:
                # Snap не удался - используем GPX данные
                sign.calc_confidence(
                    snap_dist_m=-1.0,
                    osm_azimuth=None,
                    gpx_azimuth=gpx_azimuth
                )
        except Exception as e:
            # При ошибке snap - вычисляем уверенность без snap данных
            sign.calc_confidence(
                snap_dist_m=-1.0,
                osm_azimuth=None,
                gpx_azimuth=gpx_azimuth
            )

    def _sign_to_feature(
        self, sign: TrackedSign, coefficient: int
    ) -> Optional[Feature]:
        """Строит GeoJSON Feature для одного знака."""
        self._snap_sign_coords(sign)
        try:
            x1, y1, x2, y2 = self._calc.get_line(sign, coefficient)
        except Exception as e:
            logger.info(f"[FinalHandler] get_line error: {e}")
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

    def _process_turn_signs(self, turns: list, progress_cb=None, offset=0, total_signs=0) -> list[Feature]:
        """
        Обрабатывает знаки на поворотах/перекрёстках.
        
        Поддерживает два режима (настройка turn_use_bearing_geometry):
          - True (новый): Bearing-based geometry (raycast через OSM ways)
          - False (legacy): Эвристика через calculation_four_dots()
        """
        from configs.settings import get_app_settings
        settings = get_app_settings()
        
        if settings.turn_use_bearing_geometry:
            return self._process_turn_signs_bearing(turns, progress_cb, offset, total_signs)
        else:
            return self._process_turn_signs_legacy(turns, progress_cb, offset, total_signs)

    def _process_turn_signs_bearing(
        self, turns: list, progress_cb=None, offset=0, total_signs=0
    ) -> list[Feature]:
        """
        Bearing-based обработка знаков на поворотах (BLOCK H).
        
        Использует:
          - compute_sign_bearing() для вычисления азимута на знак
          - raycast_to_ways() для определения way через пересечение луча с OSM
          - aggregate_observations() для устойчивости к шуму
        """
        from core.intersection_geometry import (
            compute_sign_bearing,
            raycast_to_ways,
            aggregate_observations,
        )
        from core.osm_snap import OSMSnapper
        from configs.settings import get_app_settings
        
        settings = get_app_settings()
        features: list[Feature] = []
        processed_count = 0
        
        # BLOCK 2.3.3: Счётчики для статистики
        stats_bearing_success = 0  # Знаков определено геометрически
        stats_bearing_low_consistency = 0  # Низкая consistency
        stats_legacy_fallback = 0  # Через эвристику
        
        # Собираем все знаки из всех turns
        all_turn_signs = []
        for turn in turns:
            all_turn_signs.extend(turn.signs)
        
        if not all_turn_signs:
            return features
        
        logger.info(f"[FinalHandler] Обработка {len(all_turn_signs)} знаков на поворотах (bearing-based)")
        
        # Batch загрузка OSM ways для всех знаков
        # (переиспользуем snapper из straight signs если возможно)
        snapper = OSMSnapper()
        
        # BLOCK 2.3.1: Устанавливаем путь к персистентному кешу OSM
        if config.PATH_TO_VIDEO:
            snapper.set_cache_path(config.PATH_TO_VIDEO)
        
        # Вычисляем bbox всех знаков
        lats, lons = [], []
        for sign in all_turn_signs:
            if sign.car_x and sign.car_y:
                try:
                    lat, lon = self._converter.coordinateConverter(
                        sign.car_x[-1], sign.car_y[-1],
                        "epsg:32635", "epsg:4326",
                    )
                    lats.append(lat)
                    lons.append(lon)
                except Exception:
                    pass
        
        if not lats:
            # Нет валидных координат — fallback
            stats_legacy_fallback = len(all_turn_signs)  # Все знаки через legacy
            logger.info("[FinalHandler] Нет координат для turn signs, используем legacy")
            logger.info(f"[FinalHandler] Legacy фоллбэк: {stats_legacy_fallback}/{len(all_turn_signs)} знаков")
            return self._process_turn_signs_legacy(turns, progress_cb, offset, total_signs)
        
        # Загружаем OSM ways для bbox
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)
        
        # Добавляем буфер
        buffer_deg = settings.turn_ray_max_distance_m / 111000.0
        ways = snapper._get_ways_bbox(
            min_lat - buffer_deg,
            max_lat + buffer_deg,
            min_lon - buffer_deg,
            max_lon + buffer_deg,
        )
        
        if not ways:
            stats_legacy_fallback = len(all_turn_signs)  # Все знаки через legacy
            logger.info("[FinalHandler] Нет OSM ways в области, используем legacy")
            logger.info(f"[FinalHandler] Legacy фоллбэк: {stats_legacy_fallback}/{len(all_turn_signs)} знаков")
            return self._process_turn_signs_legacy(turns, progress_cb, offset, total_signs)
        
        logger.info(f"[FinalHandler] Загружено {len(ways)} OSM ways для turn signs")
        
        # Обрабатываем каждый знак
        for turn in turns:
            for sign in turn.signs:
                if sign.best_yolo == "5.8":
                    continue
                
                # Пропускаем если нет bbox centers (старые данные)
                if not sign.bbox_centers_x or not sign.car_x:
                    # Fallback: используем legacy логику для этого знака
                    continue
                
                # Вычисляем bearing для каждого наблюдения
                hits = []
                for i in range(len(sign.bbox_centers_x)):
                    try:
                        # Bearing на знак
                        bbox_center_x = sign.bbox_centers_x[i]
                        frame_width = config.FRAME_WIDTH  # Реальная ширина из метаданных видео
                        gpx_azimuth = sign.azimuth  # азимут машины в момент кадра
                        
                        bearing = compute_sign_bearing(
                            gpx_azimuth=gpx_azimuth,
                            bbox_center_x=bbox_center_x,
                            frame_width=frame_width,
                            hfov_deg=settings.camera_hfov_deg,
                        )
                        
                        # GPS позиция машины в этот момент
                        car_lat, car_lon = self._converter.coordinateConverter(
                            sign.car_x[min(i, len(sign.car_x) - 1)],
                            sign.car_y[min(i, len(sign.car_y) - 1)],
                            "epsg:32635", "epsg:4326",
                        )
                        
                        # Raycast
                        hit = raycast_to_ways(
                            origin_lat=car_lat,
                            origin_lon=car_lon,
                            bearing_deg=bearing,
                            ways=ways,
                            max_distance_m=settings.turn_ray_max_distance_m,
                        )
                        
                        if hit:
                            hits.append(hit)
                    
                    except Exception as e:
                        # Пропускаем проблемное наблюдение
                        continue
                
                # Агрегируем наблюдения
                if hits:
                    way_id, consistency, representative = aggregate_observations(hits)
                    
                    if representative:
                        # BLOCK 2.3.3: Проверяем consistency для статистики
                        if consistency >= 0.5:
                            stats_bearing_success += 1
                        else:
                            stats_bearing_low_consistency += 1
                        
                        # Используем way_azimuth из representative hit
                        sign.azimuth = representative.way_azimuth
                        
                        # conf_placement учитывает consistency
                        sign.calc_confidence(
                            snap_dist_m=representative.distance_m,
                            osm_azimuth=representative.way_azimuth,
                            gpx_azimuth=gpx_azimuth,
                        )
                        
                        # Умножаем conf_placement на consistency для устойчивости
                        sign.conf_placement *= consistency
                        sign.conf_total = (sign.conf_cnn + sign.conf_placement) / 2.0
                
                # Строим Feature (используем get_line из текущего кода)
                try:
                    coefficient = 2
                    x1, y1, x2, y2 = self._calc.get_line(sign, coefficient)
                    
                    # Корректируем азимут для боковых знаков
                    if sign.best_side:
                        sign.azimuth = (
                            (sign.azimuth - 90) % 360
                            if sign.is_left
                            else (sign.azimuth + 90) % 360
                        )
                    
                    feat = self._build_feature(x1, y1, x2, y2, sign)
                    if feat:
                        features.append(feat)
                    
                    processed_count += 1
                    if progress_cb and processed_count % 10 == 0:
                        progress_cb(
                            offset + processed_count,
                            total_signs,
                            f"Обработка поворотов (bearing)... {processed_count}"
                        )
                
                except Exception as e:
                    logger.info(f"[FinalHandler] Ошибка построения feature для знака {sign.best_cnn}: {e}")
        
        # BLOCK 2.3.3: Выводим статистику bearing vs legacy
        total_turn_signs = len(all_turn_signs)
        logger.info(f"[FinalHandler] ═══ Статистика обработки знаков на поворотах ═══")
        logger.info(f"[FinalHandler] Всего знаков: {total_turn_signs}")
        logger.info(f"[FinalHandler] Геометрия (bearing): {stats_bearing_success} ({100*stats_bearing_success/max(total_turn_signs,1):.1f}%)")
        logger.info(f"[FinalHandler] Низкая consistency: {stats_bearing_low_consistency} ({100*stats_bearing_low_consistency/max(total_turn_signs,1):.1f}%)")
        logger.info(f"[FinalHandler] Legacy фоллбэк: {stats_legacy_fallback} ({100*stats_legacy_fallback/max(total_turn_signs,1):.1f}%)")
        logger.info(f"[FinalHandler] Features создано: {len(features)}")
        logger.info(f"[FinalHandler] ════════════════════════════════════════════════════")
        
        return features

    def _process_turn_signs_legacy(self, turns: list, progress_cb=None, offset=0, total_signs=0) -> list[Feature]:
        """
        Legacy обработка знаков на поворотах (эвристика через calculation_four_dots).
        Сохранена для обратной совместимости и fallback.
        """
        features: list[Feature] = []

        # Позиции на повороте → точка расчёта
        TURN_POSITIONS = {
            "0": "start",  "1": "start",  "2": "start",
            "3": "rev_end","4": "rev_end","5": "rev_start",
            "5.1":"rev_start","6":"rev_start",
            "7": "rev_end","8": "rev_end",
        }
        
        processed_count = 0

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
                    feat = self._build_feature(sign, x1, y1, x2, y2)
                    if feat:
                        features.append(feat)
                    coefficient += 1
                    processed_count += 1
                    
                    # Обновляем прогресс
                    if progress_cb:
                        progress_cb(offset + processed_count, total_signs, f"Обработка поворотов (legacy)... {processed_count}")

        return features

    # ── Дедупликация O(n) ─────────────────────────────────────────

    def _deduplicate(self, features: list[Feature]) -> list[Feature]:
        """
        Убирает дубли используя пространственную сетку.
        O(n) вместо O(n^2) оригинала.

        Два знака считаются дублями если:
          - одинаковый тип
          - одинаковая сторона (left/right)
          - расстояние < DEDUP_RADIUS_M
          - разница азимутов < DEDUP_AZIMUTH_DEG
        """
        logger.info(f"[FinalHandler] _deduplicate начат, features: {len(features)}")
        start_time = __import__('time').time()
        
        # Таймаут 60 секунд - если дольше, прерываем
        TIMEOUT_SECONDS = 60
        
        # Словарь: (cell_x, cell_y, type, side) → Feature
        grid: dict[tuple, Feature] = {}
        result: list[Feature] = []

        for idx, feat in enumerate(features):
            # Проверяем таймаут каждые 100 features
            if idx % 100 == 0:
                elapsed = __import__('time').time() - start_time
                if idx > 0:
                    logger.info(f"[FinalHandler] _deduplicate прогресс: {idx}/{len(features)} ({elapsed:.1f}s)")
                
                if elapsed > TIMEOUT_SECONDS:
                    logger.warning(f"[FinalHandler] ВНИМАНИЕ: дедупликация превысила таймаут {TIMEOUT_SECONDS}s")
                    logger.info(f"[FinalHandler] Обработано {idx}/{len(features)}, возвращаем что есть")
                    # Добавляем оставшиеся features без дедупликации
                    result.extend(features[idx:])
                    break
            
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

            # BLOCK N.1: Динамический расчёт окна проверки соседних ячеек
            # Гарантирует, что окно покрывает весь DEDUP_RADIUS_M
            import math
            cells_to_check = max(1, math.ceil(self.DEDUP_RADIUS_M / self.GRID_CELL_M))

            # Проверяем текущую и соседние ячейки
            is_dup = False
            for dx in range(-cells_to_check, cells_to_check + 1):
                for dy in range(-cells_to_check, cells_to_check + 1):
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

        elapsed = __import__('time').time() - start_time
        logger.info(f"[FinalHandler] _deduplicate завершён: {len(result)} знаков ({elapsed:.1f}s)")
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
        """
        Task C: Создаёт GeoJSON Feature из знака и координат линии.
        Использует resolve_video_and_frame() для корректного определения video_idx/frame_local.
        """
        type_sign = sign.best_cnn
        if type_sign not in CODES_SIGNS:
            return None

        # Видео и время - Task C: используем resolve_video_and_frame
        avg_frame = (
            sum(sign.abs_frame_numbers) / len(sign.abs_frame_numbers)
            if sign.abs_frame_numbers else 0
        )
        
        try:
            from core.video_index import resolve_video_and_frame
            video_idx, frame_local = resolve_video_and_frame(int(avg_frame))
        except (ValueError, ImportError) as e:
            # Fallback к старой логике при ошибке
            print(f"[FinalHandler] ВНИМАНИЕ: resolve_video_and_frame не сработал ({e}), используем fallback")
            video_idx = int(avg_frame // config.FRAMES_PER_VIDEO)
            frame_local = int(avg_frame % config.FRAMES_PER_VIDEO)
        
        video_name = (
            config.VIDEOS[video_idx]
            if config.VIDEOS and video_idx < len(config.VIDEOS)
            else "unknown"
        )
        minute = frame_local // 3600
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
            "cnn_count":             str(sign.cnn_count),
            "observation_count":     str(sign.observation_count),
            "conf_cnn":              f"{sign.conf_cnn:.3f}",
            "conf_placement":        f"{sign.conf_placement:.3f}",
            "conf_side":             f"{sign.conf_side:.3f}",  # ЗАДАЧА 2
            "conf_total":            f"{sign.conf_total:.3f}",
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
            # FIX: Сохраняем как настоящий JSON массив, не строку
            "absolute_frame_numbers":sign.abs_frame_numbers if sign.abs_frame_numbers else [],
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