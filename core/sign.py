"""
core/sign.py
Трекируемый знак — накапливает данные по всем кадрам где был виден.
Рефакторинг Sign.py: типы, slots, методы разбиты по ответственности.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from core.converter import Converter
from core.frame import DetectedSign


@dataclass
class TrackedSign:
    """
    Знак который детектор видел в нескольких кадрах подряд.
    Накапливает историю позиций, CNN-результаты, координаты.
    """
    # ── Пиксельные координаты (история по кадрам) ─────────────────
    pixel_x:  list[int]   = field(default_factory=list)
    pixel_y:  list[int]   = field(default_factory=list)
    widths:   list[int]   = field(default_factory=list)
    heights:  list[int]   = field(default_factory=list)
    
    # ── Центры bbox (для bearing calculation, BLOCK H) ────────────
    bbox_centers_x: list[int] = field(default_factory=list)
    bbox_centers_y: list[int] = field(default_factory=list)

    # ── Координаты автомобиля (EPSG:32635) ────────────────────────
    car_x:    list[float] = field(default_factory=list)
    car_y:    list[float] = field(default_factory=list)

    # ── Номера кадров ─────────────────────────────────────────────
    frame_numbers:    list[int] = field(default_factory=list)  # внутри видео
    abs_frame_numbers:list[int] = field(default_factory=list)  # глобальные

    # ── Классификация ─────────────────────────────────────────────
    yolo_results: list[str] = field(default_factory=list)  # классы YOLO
    cnn_results:  list[str] = field(default_factory=list)  # классы CNN
    side_results: list[bool]= field(default_factory=list)  # боковой?
    text_results: list[str] = field(default_factory=list)  # текст на знаке
    
    # ── GPS данные (BLOCK J.3) ────────────────────────────────────
    speed_kmh: list[float] = field(default_factory=list)  # скорость автомобиля (км/ч)

    # ── Оптимизация CNN (B.3) ─────────────────────────────────────
    _stable_cnn_class: Optional[str] = None  # стабильный класс после N наблюдений
    _consecutive_same_cnn: int = 0           # счётчик одинаковых CNN результатов подряд
    
    # ── Оптимизация OCR (BLOCK CPU-4) ─────────────────────────────
    _last_ocr_abs_frame: int = -10000  # последний кадр где запускали OCR
    _ocr_call_count: int = 0           # сколько раз запускали OCR для этого знака

    # ── Финальные атрибуты ────────────────────────────────────────
    azimuth:        float = 0.0
    is_left:        bool  = False
    is_turn:        bool  = False
    turn_direction: str   = "straight"
    number:         int   = 0        # позиция на повороте (0–8)
    number_sign:    int   = 0        # глобальный номер кадра фиксации
    distance:       Optional[float] = None

    # ── GPS координаты знака (заполняются после snap к OSM) ───────
    latitude:  Optional[float] = None
    longitude: Optional[float] = None

    # ── Уверенность (заполняется в FinalHandler после snap) ───────
    conf_cnn:      float = 0.0   # cnn_count / observation_count  [0..1]
    conf_placement:float = 0.0   # уверенность постановки на карту [0..1]
    conf_side:     float = 0.0   # уверенность определения стороны [0..1] (ЗАДАЧА 2)
    conf_total:    float = 0.0   # итоговая = 0.5*cnn + 0.5*placement
    snap_distance: float = -1.0  # расстояние до ближайшего ребра дороги (м)
    azimuth_delta: float = 0.0   # расхождение GPX-курса и OSM-азимута (°)
    
    # ── Информация о дороге (ЗАДАЧА 1) ────────────────────────────
    road_lanes: Optional[int] = None     # Количество полос (из OSM)
    road_width_m: Optional[float] = None # Ширина дороги (из OSM или оценка)

    _converter: Converter = field(default_factory=Converter, repr=False)

    # ── Добавление данных из кадра ────────────────────────────────

    def append(self, det: DetectedSign) -> None:
        """Добавить одно обнаружение знака."""
        self.pixel_x.append(det.x)
        self.pixel_y.append(det.y)
        self.widths.append(det.w)
        self.heights.append(det.h)
        
        # Вычисляем и сохраняем центр bbox (BLOCK H)
        bbox_center_x = det.x + det.w // 2
        bbox_center_y = det.y + det.h // 2
        self.bbox_centers_x.append(bbox_center_x)
        self.bbox_centers_y.append(bbox_center_y)
        
        self.yolo_results.append(det.name_sign)
        self.cnn_results.append(det.number_sign)
        self.side_results.append(det.is_side)
        self.frame_numbers.append(det.frame_number)
        self.abs_frame_numbers.append(det.absolute_frame_number)
        if det.text_on_sign:
            self.text_results.append(det.text_on_sign)
        self._append_car_coord(det.latitude, det.longitude)
        
        # Обновляем счётчик стабильности CNN (B.3)
        self._update_cnn_stability(det.number_sign)

    def _append_car_coord(self, x: float, y: float) -> None:
        """Добавляет координату только если она изменилась."""
        if not self.car_x or x != self.car_x[-1]:
            self.car_x.append(x)
            self.car_y.append(y)

    # ── Оптимизация CNN (B.3) ─────────────────────────────────────

    def _update_cnn_stability(self, cnn_class: str) -> None:
        """
        Обновляет счётчик стабильных наблюдений CNN.
        Если класс повторяется N раз подряд, помечаем знак как стабильный.
        """
        STABILITY_THRESHOLD = 5  # порог стабильности
        
        if self._stable_cnn_class is None:
            # Первое наблюдение
            self._stable_cnn_class = cnn_class
            self._consecutive_same_cnn = 1
        elif cnn_class == self._stable_cnn_class:
            # Класс совпадает с текущим стабильным
            self._consecutive_same_cnn += 1
        else:
            # Класс изменился — сбрасываем счётчик
            self._stable_cnn_class = cnn_class
            self._consecutive_same_cnn = 1

    def should_skip_cnn(self) -> bool:
        """
        Проверяет, можно ли пропустить CNN классификацию для этого знака.
        Пропускаем если знак стабильный (N одинаковых результатов подряд).
        
        Returns:
            True если можно пропустить CNN и использовать cached класс
        """
        STABILITY_THRESHOLD = 5
        return self._consecutive_same_cnn >= STABILITY_THRESHOLD

    def get_stable_cnn_class(self) -> Optional[str]:
        """
        Возвращает стабильный CNN класс если знак стабилен.
        Используется вместо вызова CNN модели.
        """
        if self.should_skip_cnn():
            return self._stable_cnn_class
        return None

    def reset_cnn_stability(self) -> None:
        """
        Сбрасывает счётчик стабильности.
        Вызывается при merge или других операциях изменяющих состояние.
        """
        self._stable_cnn_class = None
        self._consecutive_same_cnn = 0
    
    # ── OCR Throttling (BLOCK CPU-4) ──────────────────────────────
    
    # Настройки троттлинга OCR
    OCR_MIN_INTERVAL_FRAMES = 8   # не чаще раза в N обработанных кадров
    OCR_MAX_CALLS_PER_SIGN = 6    # после этого числа успешных вызовов — хватит
    
    def should_run_ocr(self, current_abs_frame: int) -> bool:
        """
        Решает, нужно ли запускать OCR для этого наблюдения.
        
        False если:
        - Уже достаточно непустых text_results
        - Слишком рано после предыдущего вызова OCR
        
        Args:
            current_abs_frame: абсолютный номер текущего кадра
        
        Returns:
            bool: True если нужно запустить OCR, False если пропускаем
        """
        # Считаем непустые текстовые результаты
        non_empty = sum(1 for t in self.text_results if t)
        if non_empty >= self.OCR_MAX_CALLS_PER_SIGN:
            return False  # Уже достаточно успешных распознаваний
        
        # Защита от знака, который постоянно даёт разный/пустой текст
        if self._ocr_call_count >= self.OCR_MAX_CALLS_PER_SIGN * 2:
            return False  # Слишком много попыток
        
        # Проверка временного интервала
        if current_abs_frame - self._last_ocr_abs_frame < self.OCR_MIN_INTERVAL_FRAMES:
            return False  # Слишком рано после предыдущего OCR
        
        return True
    
    def mark_ocr_requested(self, current_abs_frame: int) -> None:
        """
        Отмечает, что OCR был запрошен для этого кадра.
        Обновляет счётчики для троттлинга.
        
        Args:
            current_abs_frame: абсолютный номер текущего кадра
        """
        self._last_ocr_abs_frame = current_abs_frame
        self._ocr_call_count += 1


    def merge(self, other: "TrackedSign") -> None:
        """Объединить два знака в один (concat_two_object)."""
        self.pixel_x          += other.pixel_x
        self.pixel_y          += other.pixel_y
        self.widths           += other.widths
        self.heights          += other.heights
        self.yolo_results     += other.yolo_results
        self.cnn_results      += other.cnn_results
        self.side_results     += other.side_results
        self.text_results     += other.text_results
        self.frame_numbers    += other.frame_numbers
        self.abs_frame_numbers+= other.abs_frame_numbers
        self.car_x            += other.car_x
        self.car_y            += other.car_y
        
        # Сбрасываем стабильность после merge (B.3)
        self.reset_cnn_stability()

    # ── Статистика ────────────────────────────────────────────────

    def most_common(self, results: list[str]) -> tuple[str, int]:
        """Самый частый элемент списка. Возвращает (name, count)."""
        if not results:
            return ("", 0)
        name, count = Counter(results).most_common(1)[0]
        return (name, count)

    @property
    def best_yolo(self) -> str:
        return self.most_common(self.yolo_results)[0]

    @property
    def best_cnn(self) -> str:
        """Лучший CNN класс. Fallback на YOLO если CNN пустой."""
        if not self.cnn_results:
            return self.most_common(self.yolo_results)[0]
        return self.most_common(self.cnn_results)[0]

    @property
    def best_side(self) -> bool:
        """True если знак чаще появлялся как боковой."""
        if not self.side_results:
            return False
        return sum(self.side_results) > len(self.side_results) / 2

    @property
    def cnn_count(self) -> int:
        """Сколько раз лучший CNN-класс встречается."""
        if not self.cnn_results:
            # Если нет CNN результатов, используем YOLO как fallback
            return self.most_common(self.yolo_results)[1]
        return self.most_common(self.cnn_results)[1]

    @property
    def observation_count(self) -> int:
        return len(self.frame_numbers)
    
    @property
    def potential_cnn_savings(self) -> int:
        """
        Количество CNN вызовов, которые можно было бы пропустить
        если использовать механизм стабильности.
        Используется для статистики/мониторинга эффективности B.3.
        """
        STABILITY_THRESHOLD = 5
        
        if self.observation_count < STABILITY_THRESHOLD:
            return 0
        
        # Считаем сколько последовательных одинаковых результатов
        if not self.cnn_results:
            return 0
        
        consecutive = 1
        total_savings = 0
        prev_class = self.cnn_results[0]
        
        for cnn_class in self.cnn_results[1:]:
            if cnn_class == prev_class:
                consecutive += 1
                if consecutive >= STABILITY_THRESHOLD:
                    total_savings += 1  # этот вызов можно было пропустить
            else:
                consecutive = 1
                prev_class = cnn_class
        
        return total_savings

    # ── Геометрия ─────────────────────────────────────────────────

    def pixel_vector_to(self, det: DetectedSign) -> float:
        """Евклидово расстояние от последней позиции до нового знака."""
        if not self.pixel_x:
            return 0.0
        dx = det.x - self.pixel_x[-1]
        dy = det.y - self.pixel_y[-1]
        return round((dx**2 + dy**2) ** 0.5, 1)

    def replace_car_coords_from_turn(self, turn_coords: list[tuple]) -> None:
        """Заменить координаты автомобиля точками поворота."""
        self.car_x.clear()
        self.car_y.clear()
        for lat, lon in turn_coords:
            x, y = self._converter.coordinateConverter(lat, lon, "epsg:4326", "epsg:32635")
            self.car_x.append(x)
            self.car_y.append(y)

    # ── Городские знаки ───────────────────────────────────────────

    def best_city_name(self) -> str:
        """
        Наиболее вероятное название населённого пункта по голосованию OCR-наблюдений.
        Использует тот же механизм most_common, что и для обычных текстовых знаков.
        """
        if not self.text_results:
            return ""
        return self.most_common(self.text_results)[0]

    # ── Уверенность ──────────────────────────────────────────────

    def calc_confidence(
        self,
        snap_dist_m: float = -1.0,
        osm_azimuth: Optional[float] = None,
        gpx_azimuth: Optional[float] = None,
        speed_kmh: Optional[float] = None,  # BLOCK J.3: Скорость автомобиля
    ) -> None:
        """
        Вычисляет все метрики уверенности и записывает в поля.
        Вызывается из FinalHandler после OSM snap.

        conf_cnn:       cnn_count / observation_count
        conf_placement: взвешенная из 5 субметрик (добавлена conf_side в ЗАДАЧЕ 2)
        conf_total:     0.5 * conf_cnn + 0.5 * conf_placement
        
        BLOCK J.3: speed_kmh используется для понижения az_score на низкой скорости.
        """
        # ── 1. CNN уверенность ────────────────────────────────────
        self.conf_cnn = (
            self.cnn_count / self.observation_count
            if self.observation_count > 0 else 0.0
        )

        # ── 2. Уверенность постановки ─────────────────────────────

        # 2a. Стабильность трека (разброс pixel_x по кадрам)
        #     Чем меньше std, тем стабильнее знак → выше уверенность
        track_score = self._calc_track_stability()

        # 2b. Длина трека (наблюдений)
        #     Нормируем: 4 = 0.0, 20+ = 1.0
        obs = self.observation_count
        length_score = min(1.0, max(0.0, (obs - 4) / 16))

        # 2c. OSM snap качество
        #     snap_dist_m = -1 → snap не выполнялся (нейтральный балл 0.5)
        #     0–5м  → 1.0,  5–15м → linear,  >30м → 0.0
        if snap_dist_m < 0:
            snap_score = 0.5
        elif snap_dist_m <= 5:
            snap_score = 1.0
        elif snap_dist_m <= 30:
            snap_score = 1.0 - (snap_dist_m - 5) / 25
        else:
            snap_score = 0.0
        self.snap_distance = snap_dist_m

        # 2d. Расхождение азимутов GPX vs OSM
        #     0° → 1.0,  45°+ → 0.0
        #     BLOCK J.3: Понижаем на низкой скорости (курс GPS ненадёжен)
        if osm_azimuth is not None and gpx_azimuth is not None:
            delta = abs(osm_azimuth - gpx_azimuth) % 360
            if delta > 180:
                delta = 360 - delta
            self.azimuth_delta = delta
            az_score = max(0.0, 1.0 - delta / 45)
            
            # BLOCK J.3: Понижающий коэффициент на низкой скорости
            if speed_kmh is not None and speed_kmh < 10.0:
                # На скорости < 10 км/ч курс GPS ненадёжен
                speed_factor = max(0.3, speed_kmh / 10.0)
                az_score *= speed_factor
        else:
            az_score = 0.5  # нет данных — нейтральный балл
        
        # 2e. ЗАДАЧА 2: Уверенность стороны/полосы
        side_score = self._calc_side_confidence()
        self.conf_side = side_score  # Сохраняем для GeoJSON

        # ЗАДАЧА 2: Перераспределены веса для включения side_score
        self.conf_placement = (
            0.25 * track_score   +
            0.20 * length_score  +
            0.25 * snap_score    +
            0.15 * az_score      +
            0.15 * side_score
        )

        # ── 3. Итоговая ───────────────────────────────────────────
        self.conf_total = 0.50 * self.conf_cnn + 0.50 * self.conf_placement
    
    def _calc_side_confidence(self) -> float:
        """
        ЗАДАЧА 2: Вычисляет уверенность определения стороны знака.
        
        Учитывает:
        - Консистентность is_left между наблюдениями
        - Ширину дороги (на широких дорогах уверенность ниже)
        - Наличие конкурирующих кандидатов рядом (пограничный merge/split)
        
        Returns:
            Скор от 0.0 до 1.0
        """
        # Фактор 1: Консистентность стороны между наблюдениями
        if not self.side_results:
            # Нет данных о side_results (старые данные) - используем нейтральный балл
            consistency_score = 0.5
        else:
            # Доля наблюдений совпадающих с best_side
            matching = sum(1 for s in self.side_results if s == self.best_side)
            consistency_score = matching / len(self.side_results) if self.side_results else 0.5
        
        # Фактор 2: Ширина дороги
        # На узкой дороге (≤2 полосы) уверенность выше
        # На широкой дороге (4+ полосы) уверенность снижается
        width_penalty = 0.0
        if self.road_lanes is not None:
            if self.road_lanes >= 4:
                # Широкая дорога - снижаем уверенность
                width_penalty = min(0.3, (self.road_lanes - 2) * 0.1)
            # Узкая дорога (1-2 полосы) - без штрафа
        elif self.road_width_m is not None:
            # Используем ширину в метрах
            if self.road_width_m >= 14.0:  # ~4 полосы по 3.5м
                width_penalty = min(0.3, (self.road_width_m - 7.0) / 40.0)
        
        width_score = max(0.0, 1.0 - width_penalty)
        
        # Фактор 3: Стабильность пиксельных координат сторона
        # Если знак "прыгает" между левой и правой стороной кадра - уверенность низкая
        pixel_side_score = 1.0
        if len(self.pixel_x) > 2:
            # Вычисляем долю кадров где знак на "правильной" стороне кадра
            # is_left=True → pixel_x < SCREEN_WIDTH/2
            # is_left=False → pixel_x > SCREEN_WIDTH/2
            SCREEN_WIDTH = 1920  # стандартная ширина
            center = SCREEN_WIDTH / 2.0
            
            if self.is_left:
                matching_pixels = sum(1 for x in self.pixel_x if x < center)
            else:
                matching_pixels = sum(1 for x in self.pixel_x if x > center)
            
            pixel_side_score = matching_pixels / len(self.pixel_x)
        
        # Комбинируем факторы
        # Консистентность side_results - основной фактор (50%)
        # Ширина дороги - средний фактор (30%)
        # Пиксельная сторона - дополнительный фактор (20%)
        final_score = (
            0.50 * consistency_score +
            0.30 * width_score +
            0.20 * pixel_side_score
        )
        
        return min(1.0, max(0.0, final_score))

    def _calc_track_stability(self) -> float:
        """
        Стабильность трека по pixel_x.
        std < 5px → 1.0,  std > 150px → 0.0.
        """
        if len(self.pixel_x) < 2:
            return 0.5
        mean = sum(self.pixel_x) / len(self.pixel_x)
        variance = sum((x - mean) ** 2 for x in self.pixel_x) / len(self.pixel_x)
        std = variance ** 0.5
        return max(0.0, 1.0 - std / 150)

    @property
    def confidence_label(self) -> str:
        """Текстовый уровень уверенности для UI."""
        t = self.conf_total
        if t >= 0.75:
            return "высокая"
        if t >= 0.50:
            return "средняя"
        if t >= 0.30:
            return "низкая"
        return "очень низкая"

    # ── Debug ─────────────────────────────────────────────────────

    def __repr__(self) -> str:
        x, y = ("?", "?")
        try:
            x, y = self._converter.coordinateConverter(
                self.car_x[-1], self.car_y[-1], "epsg:32635", "epsg:4326"
            )
            x, y = round(x, 5), round(y, 5)
        except Exception:
            pass
        return (
            f"TrackedSign(type={self.best_cnn!r}, "
            f"obs={self.observation_count}, "
            f"left={self.is_left}, "
            f"frames={self.frame_numbers[:3]}…, "
            f"coord=({x},{y}), az={self.azimuth:.1f})"
        )