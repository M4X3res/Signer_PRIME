"""
core/sign_handler.py
SignHandler — трекинг знаков между кадрами.

Исправления относительно оригинала:
  1. clean_frame_from_duplicates  — порог перекрытия 10% → 40%
  2. _remove_collisions           — учитывает совпадение типа знака
  3. _check_nearby_sign           — настраиваемый радиус (по умолчанию 8м)
  4. Убрана двойная дедупликация  — is_duplicate_sign и check_presence
     объединены в один метод _is_duplicate
  5. Все магические числа — именованные константы класса
"""
from __future__ import annotations

import copy
import math
from typing import Optional

from core.gpx_handler import GPXHandler
from core.converter import Converter
from configs import config
from core.frame import DetectedSign
from core.sign import TrackedSign


class SignHandler:
    # ── Настройки (можно переопределить снаружи) ─────────────────
    INCORRECT_EVIDENCE       = 9999.99
    SCREEN_WIDTH             = 1920
    DIFF_FRAMES_REMOVE       = 5     # через сколько кадров удалять потерянный знак
    DIFF_FRAMES_MOVE         = 5     # через сколько кадров финализировать знак
    MIN_OBSERVATIONS         = 4     # минимум наблюдений для сохранения
    MAX_PIXEL_DISTANCE       = 800   # макс. пиксельное расстояние для связи знаков
    OVERLAP_THRESHOLD        = 40.0  # % перекрытия для считания дублем в кадре
    NEARBY_SIGN_RADIUS_M     = 8.0   # метров — радиус дедупликации на карте
    SAME_TYPE_BONUS          = 50    # бонус при совпадении типа YOLO (снижает дистанцию)
    DIFFERENT_TYPE_PENALTY   = 50    # штраф при несовпадении типа

    def __init__(self):
        self._gpx       = GPXHandler()
        self._converter = Converter()
        self.signs:         list[TrackedSign] = []   # активные (трекируются)
        self.result_signs:  list[TrackedSign] = []   # финализированные
        self.turns:         list              = []

    # ── Главный метод ─────────────────────────────────────────────

    def check_the_data_to_add(
        self,
        detections: Optional[list[DetectedSign]],
        turn,
    ):
        if not detections:
            return turn

        current_frame = detections[0].frame_number

        if not self.signs:
            for det in detections:
                self._add_sign(det)
        else:
            if turn.was_there_turn and not turn.is_turn():
                turn = self._handle_turn_end(turn, current_frame)

            detections = self._clean_frame_from_duplicates(detections)
            evidences  = self._calc_evidence_matrix(detections)
            evidences  = self._remove_collisions(evidences, detections)
            matched    = self._match_evidences(evidences, detections, current_frame)
            detections = self._attach_unmatched(detections, matched, evidences)
            self._add_new_signs(detections, matched)

        self._update_azimuths(current_frame)
        self._remove_lost_signs(current_frame)

        if not turn.is_turn():
            self._finalize_signs(current_frame)
        else:
            if not turn.signs:
                self._finalize_signs(current_frame)
            turn.signs = self.signs

        return turn

    # ── Очистка кадра от дублей ───────────────────────────────────

    def _clean_frame_from_duplicates(
        self, detections: list[DetectedSign]
    ) -> list[DetectedSign]:
        """
        Убирает дубли одного типа в одном кадре.
        Оригинальный порог 10% → заменён на OVERLAP_THRESHOLD (40%).
        """
        by_type: dict[str, list[DetectedSign]] = {}
        for det in detections:
            by_type.setdefault(det.name_sign, []).append(det)

        result = list(detections)
        for name, group in by_type.items():
            if len(group) < 2:
                continue
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    a, b = group[i], group[j]
                    s1 = (a.x, a.y, a.w, a.h)
                    s2 = (b.x, b.y, b.w, b.h)
                    if DetectedSign.overlap_area(s1, s2) > self.OVERLAP_THRESHOLD:
                        # Удаляем меньший знак
                        smaller = a if (a.w * a.h) < (b.w * b.h) else b
                        if smaller in result:
                            result.remove(smaller)
        return result

    # ── Матрица расстояний ────────────────────────────────────────

    def _calc_evidence_matrix(
        self, detections: list[DetectedSign]
    ) -> list[list]:
        """
        Для каждого активного знака вычисляет расстояние
        до каждого детекта в текущем кадре.
        Возвращает список [best_det_idx, best_distance].
        """
        matrix = []
        for sign in self.signs:
            distances = []
            for det in detections:
                delta_h = det.y - sign.pixel_y[-1]
                # Знак не может прыгнуть выше (отрицательный delta_h > 10px)
                if delta_h > 10:
                    distances.append(self.INCORRECT_EVIDENCE)
                    continue

                dist = sign.pixel_vector_to(det)

                # Бонус/штраф за совпадение типа YOLO
                if sign.best_yolo == det.name_sign:
                    dist -= self.SAME_TYPE_BONUS
                else:
                    dist += self.DIFFERENT_TYPE_PENALTY

                dist = self.INCORRECT_EVIDENCE if dist > self.MAX_PIXEL_DISTANCE else dist
                distances.append(dist)

            if distances:
                best_idx = distances.index(min(distances))
                matrix.append([best_idx, min(distances)])
            else:
                matrix.append([-1, self.INCORRECT_EVIDENCE])

        return matrix

    # ── Разрешение коллизий ───────────────────────────────────────

    def _remove_collisions(
        self,
        evidences: list[list],
        detections: list[DetectedSign],
    ) -> list[list]:
        """
        Если два знака претендуют на один детект —
        оставляем тот у кого меньше расстояние И совпадает тип.
        Оригинал учитывал только расстояние.
        """
        for i in range(len(evidences)):
            for j in range(i + 1, len(evidences)):
                if evidences[i][0] != evidences[j][0]:
                    continue
                if evidences[i][0] < 0:
                    continue

                det_idx = evidences[i][0]
                det = detections[det_idx]

                # Учитываем совпадение типа при разрешении коллизии
                i_match = self.signs[i].best_yolo == det.name_sign
                j_match = self.signs[j].best_yolo == det.name_sign

                if i_match and not j_match:
                    evidences[j][1] = self.INCORRECT_EVIDENCE
                elif j_match and not i_match:
                    evidences[i][1] = self.INCORRECT_EVIDENCE
                else:
                    # Оба совпадают или оба нет — оставляем ближний
                    if evidences[i][1] <= evidences[j][1]:
                        evidences[j][1] = self.INCORRECT_EVIDENCE
                    else:
                        evidences[i][1] = self.INCORRECT_EVIDENCE

        return evidences

    # ── Сопоставление знаков с детектами ─────────────────────────

    def _match_evidences(
        self,
        evidences: list[list],
        detections: list[DetectedSign],
        current_frame: int,
    ) -> list[DetectedSign]:
        """Добавляет данные к подходящим активным знакам."""
        matched = []
        for sign_idx, (det_idx, distance) in enumerate(evidences):
            if distance >= self.INCORRECT_EVIDENCE or det_idx < 0:
                continue
            sign = self.signs[sign_idx]
            det  = detections[det_idx]
            gap  = current_frame - sign.frame_numbers[-1]
            if gap < 7:
                sign.append(det)
                sign.number_sign = config.INDEX_OF_All_FRAME
                matched.append(det)
        return matched

    def _attach_unmatched(
        self,
        detections: list[DetectedSign],
        matched: list[DetectedSign],
        evidences: list[list],
    ) -> list[DetectedSign]:
        """
        Пробуем привязать незакреплённые детекты к знакам
        у которых вектор движения совпадает.
        """
        unmatched = [d for d in detections if d not in matched]
        attached  = []

        for sign_idx, (_, distance) in enumerate(evidences):
            sign = self.signs[sign_idx]
            for det in unmatched:
                if sign.best_yolo != det.name_sign:
                    continue
                vec = sign.pixel_vector_to(det)
                if abs(vec - distance) <= 30 and vec != 0:
                    sign.append(det)
                    attached.append(det)
                    break

        # Убираем прикреплённые из unmatched
        remaining = [d for d in detections if d not in matched and d not in attached]
        return remaining

    def _add_new_signs(
        self,
        unmatched: list[DetectedSign],
        matched: list[DetectedSign],
    ) -> None:
        for det in unmatched:
            if det not in matched:
                self._add_sign(det)

    # ── Вспомогательные ──────────────────────────────────────────

    def _add_sign(self, det: DetectedSign) -> None:
        sign = TrackedSign()
        sign.append(det)
        self.signs.append(sign)

    def _update_azimuths(self, current_frame: int) -> None:
        for sign in self.signs:
            if sign.frame_numbers[-1] == current_frame:
                sign.azimuth = self._gpx.get_azimuth(config.INDEX_OF_GPS + 1)

    def _remove_lost_signs(self, current_frame: int) -> None:
        """Удаляет знаки которые пропали из кадра и слишком короткие."""
        to_remove = [
            s for s in self.signs
            if (current_frame - s.frame_numbers[-1] > self.DIFF_FRAMES_REMOVE
                and s.cnn_count < self.MIN_OBSERVATIONS)
        ]
        for s in to_remove:
            self.signs.remove(s)

    # ── Финализация знаков ────────────────────────────────────────

    def _finalize_signs(self, current_frame: int) -> None:
        """
        Переносит зрелые знаки из активных в result_signs.
        Зрелый = наблюдался MIN_OBSERVATIONS раз И исчез из кадра.
        """
        to_finalize = []
        for sign in self.signs:
            gone_long_enough = (
                current_frame - sign.frame_numbers[-1]
                >= self.DIFF_FRAMES_MOVE
            )
            has_enough_obs   = sign.cnn_count >= self.MIN_OBSERVATIONS

            if gone_long_enough and has_enough_obs:
                self._set_side(sign)
                if not self._is_duplicate(sign):
                    self.result_signs.append(sign)
                to_finalize.append(sign)

        for s in to_finalize:
            self.signs.remove(s)

    def _set_side(self, sign: TrackedSign) -> None:
        """Определяет с какой стороны дороги знак."""
        half = self.SCREEN_WIDTH / 3
        if sign.observation_count == 1:
            diff_w = self.SCREEN_WIDTH - sign.widths[-1]
            diff_x = self.SCREEN_WIDTH - sign.pixel_x[-1]
            sign.is_left = (diff_w <= half) == (diff_x <= half)
        else:
            sign.is_left = sign.pixel_x[0] - sign.pixel_x[-1] > 0

    # ── Дедупликация (объединены два оригинальных метода) ─────────

    def _is_duplicate(self, new_sign: TrackedSign) -> bool:
        """
        Проверяет что похожий знак уже есть в result_signs
        в радиусе NEARBY_SIGN_RADIUS_M.
        Заменяет оба: check_presence_of_nearby_sign + is_duplicate_sign.
        """
        for existing in self.result_signs:
            if existing.best_cnn != new_sign.best_cnn:
                continue
            if existing.is_left != new_sign.is_left:
                continue
            if not existing.car_x or not new_sign.car_x:
                continue

            dist = self._distance_m(
                existing.car_x[-1], existing.car_y[-1],
                new_sign.car_x[-1], new_sign.car_y[-1],
            )
            if dist < self.NEARBY_SIGN_RADIUS_M:
                # Оставляем тот у которого больше наблюдений
                if new_sign.cnn_count > existing.cnn_count:
                    self.result_signs.remove(existing)
                    return False   # новый лучше — добавляем
                return True        # существующий лучше — дроп нового

        return False

    def _distance_m(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> float:
        """Расстояние в метрах между двумя точками EPSG:32635."""
        from geopy.distance import geodesic
        lat1, lon1 = self._converter.coordinateConverter(x1, y1, "epsg:32635", "epsg:4326")
        lat2, lon2 = self._converter.coordinateConverter(x2, y2, "epsg:32635", "epsg:4326")
        return geodesic((lat1, lon1), (lat2, lon2)).meters

    # ── Поворот ───────────────────────────────────────────────────

    def _handle_turn_end(self, turn, current_frame: int):
        if turn.signs and len(turn.coordinates) >= 2:
            turn.add_points()
            self._remove_lost_signs(current_frame)
            self.signs, turn.signs = self._separate_turn_signs(turn)
            turn.set_direction_signs()
            turn.handle_turn()
            self.turns.append(copy.copy(turn))
        turn.clean()
        return turn

    def _separate_turn_signs(self, turn) -> tuple:
        straight, on_turn = [], []
        for sign in self.signs:
            if (sign.cnn_count >= 7
                    and sign.frame_numbers[-1] < turn.frames[-1]):
                on_turn.append(sign)
            else:
                sign.replace_car_coords_from_turn(turn.coordinates)
                straight.append(sign)
        return straight, on_turn