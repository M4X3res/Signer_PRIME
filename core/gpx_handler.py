"""
core/gpx_handler.py
GPXHandler — чтение и работа с GPS-треком из GPX файла.
Заменяет старый GPXHandler.py.
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional

import gpxpy
import gpxpy.gpx

from configs import config


@dataclass
class GPSPoint:
    latitude:  float
    longitude: float
    course:    float   # азимут движения (градусы)
    speed:     float   # скорость (км/ч или м/с — как в GPX)
    elevation: float = 0.0
    time_offset_s: float = 0.0  # BLOCK J.1: секунды от начала трека


class GPXHandler:
    """
    Загружает GPX трек и предоставляет доступ к точкам по индексу.
    Индекс GPS точки ≈ abs_frame_number / 60
    (одна GPS точка примерно каждые 60 кадров при 60fps).
    """

    def __init__(self):
        self._points: list[GPSPoint] = []
        self._load()

    def _load(self) -> None:
        if not config.PATH_TO_GPX:
            return
        try:
            with open(config.PATH_TO_GPX, "r", encoding="utf-8") as f:
                gpx = gpxpy.parse(f)
            
            first_time = None
            point_index = 0
            raw_points = []
            
            for track in gpx.tracks:
                for segment in track.segments:
                    for pt in segment.points:
                        # BLOCK J.1: Вычисляем time_offset_s
                        if pt.time:
                            if first_time is None:
                                first_time = pt.time
                                time_offset = 0.0
                            else:
                                time_offset = (pt.time - first_time).total_seconds()
                        else:
                            time_offset = float(point_index)
                        
                        raw_points.append(GPSPoint(
                            latitude  = pt.latitude,
                            longitude = pt.longitude,
                            course    = float(pt.course or 0),
                            speed     = float(pt.speed or 0),
                            elevation = float(pt.elevation or 0),
                            time_offset_s = time_offset,
                        ))
                        point_index += 1
            
            # BLOCK J.3: Сглаживание курса (скользящее окно 5 точек)
            self._points = self._smooth_course(raw_points)
            
        except Exception as e:
            print(f"[GPXHandler] Ошибка загрузки GPX: {e}")
    
    def _smooth_course(self, points: list[GPSPoint], window_size: int = 5) -> list[GPSPoint]:
        """
        BLOCK J.3: Сглаживание курса через скользящее окно с угловым усреднением.
        
        Использует sin/cos усреднение для корректной обработки углов (избегает 359°->1°).
        
        Args:
            points: Список сырых GPS точек
            window_size: Размер окна сглаживания (нечётное число)
        
        Returns:
            Список точек со сглаженным курсом
        """
        if len(points) < window_size:
            return points
        
        smoothed = []
        half_window = window_size // 2
        
        for i in range(len(points)):
            # Определяем границы окна
            start = max(0, i - half_window)
            end = min(len(points), i + half_window + 1)
            
            # Собираем углы в окне
            angles = [points[j].course for j in range(start, end)]
            
            # Угловое усреднение через sin/cos
            smoothed_angle = self._average_angles(angles)
            
            # Создаём новую точку с сглаженным курсом
            smoothed.append(GPSPoint(
                latitude=points[i].latitude,
                longitude=points[i].longitude,
                course=smoothed_angle,
                speed=points[i].speed,
                elevation=points[i].elevation,
                time_offset_s=points[i].time_offset_s,
            ))
        
        return smoothed
    
    @staticmethod
    def _average_angles(angles: list[float]) -> float:
        """
        BLOCK J.3: Усреднение углов через sin/cos компоненты.
        
        Корректно обрабатывает переход 359°->1° (не усредняет через 180°).
        """
        import math
        
        if not angles:
            return 0.0
        
        # Преобразуем в sin/cos компоненты
        sin_sum = sum(math.sin(math.radians(a)) for a in angles)
        cos_sum = sum(math.cos(math.radians(a)) for a in angles)
        
        # Усредняем
        sin_avg = sin_sum / len(angles)
        cos_avg = cos_sum / len(angles)
        
        # Обратное преобразование
        avg_angle = math.degrees(math.atan2(sin_avg, cos_avg))
        
        # Нормализация в [0..360)
        return (avg_angle + 360) % 360

    # ── Доступ к данным ───────────────────────────────────────────

    def get_point(self, index: int) -> Optional[GPSPoint]:
        """Возвращает GPS точку по индексу, None если вне диапазона."""
        idx = min(index + 1, len(self._points) - 1)
        if idx < 0 or not self._points:
            return None
        return self._points[idx]

    def get_azimuth(self, index: int) -> float:
        pt = self.get_point(index)
        return pt.course if pt else 0.0

    def get_current_coordinate(self, index: int) -> tuple[float, float]:
        """Возвращает (latitude, longitude)."""
        pt = self.get_point(index)
        if pt is None:
            return (0.0, 0.0)
        return (pt.latitude, pt.longitude)

    def get_prew_coordinate(self, index: int) -> tuple[float, float]:
        idx = max(0, index)
        if idx >= len(self._points):
            return (0.0, 0.0)
        pt = self._points[idx]
        return (pt.latitude, pt.longitude)

    def get_speed(self, index: int) -> float:
        pt = self.get_point(index)
        return pt.speed if pt else 0.0

    def get_count_dot(self) -> int:
        return len(self._points)

    def get_all_points(self) -> list[tuple[float, float]]:
        """Все точки трека как [(lat, lon), ...]."""
        return [(p.latitude, p.longitude) for p in self._points]
    
    def get_interpolated(self, abs_frame: int, fps: float) -> Optional[GPSPoint]:
        """
        BLOCK J.1: Возвращает GPSPoint с линейно интерполированными координатами.
        
        Вычисляет положение между двумя ближайшими GPS-точками по фактическому времени кадра.
        
        Args:
            abs_frame: Абсолютный номер кадра от начала видео
            fps: Частота кадров видео (например, 60.0)
        
        Returns:
            Интерполированный GPSPoint или None если трек пуст
        """
        if not self._points:
            return None
        
        # Вычисляем время кадра в секундах от начала
        t = abs_frame / fps
        
        # Находим две соседние точки трека между которыми попадает время t
        # Точки отсортированы по time_offset_s по возрастанию
        
        # Граничные случаи
        if t <= self._points[0].time_offset_s:
            return self._points[0]
        if t >= self._points[-1].time_offset_s:
            return self._points[-1]
        
        # Бинарный поиск или линейный (для небольших треков линейный достаточно быстр)
        for i in range(len(self._points) - 1):
            p1 = self._points[i]
            p2 = self._points[i + 1]
            
            if p1.time_offset_s <= t <= p2.time_offset_s:
                # Линейная интерполяция
                dt = p2.time_offset_s - p1.time_offset_s
                if dt == 0:
                    return p1
                
                # Коэффициент интерполяции [0..1]
                alpha = (t - p1.time_offset_s) / dt
                
                # Интерполируем координаты
                lat = p1.latitude + alpha * (p2.latitude - p1.latitude)
                lon = p1.longitude + alpha * (p2.longitude - p1.longitude)
                speed = p1.speed + alpha * (p2.speed - p1.speed)
                elevation = p1.elevation + alpha * (p2.elevation - p1.elevation)
                
                # Интерполируем курс через sin/cos (правильная угловая интерполяция)
                course = self._interpolate_angle(p1.course, p2.course, alpha)
                
                return GPSPoint(
                    latitude=lat,
                    longitude=lon,
                    course=course,
                    speed=speed,
                    elevation=elevation,
                    time_offset_s=t,
                )
        
        # Если не нашли (не должно происходить) — возвращаем ближайшую
        return self._points[0]
    
    @staticmethod
    def _interpolate_angle(angle1: float, angle2: float, alpha: float) -> float:
        """
        BLOCK J.1: Интерполяция угла через sin/cos (правильный способ).
        
        Избегает проблемы перехода 359° -> 1° (не интерполирует через 180°).
        
        Args:
            angle1, angle2: Углы в градусах [0..360)
            alpha: Коэффициент интерполяции [0..1]
        
        Returns:
            Интерполированный угол в градусах [0..360)
        """
        import math
        
        # Конвертируем в радианы
        rad1 = math.radians(angle1)
        rad2 = math.radians(angle2)
        
        # Разложение на sin/cos компоненты
        sin1, cos1 = math.sin(rad1), math.cos(rad1)
        sin2, cos2 = math.sin(rad2), math.cos(rad2)
        
        # Линейная интерполяция компонент
        sin_interp = sin1 + alpha * (sin2 - sin1)
        cos_interp = cos1 + alpha * (cos2 - cos1)
        
        # Обратное преобразование в угол
        angle_interp = math.degrees(math.atan2(sin_interp, cos_interp))
        
        # Нормализация в [0..360)
        return (angle_interp + 360) % 360

    # ── Редактирование GPX ────────────────────────────────────────

    def transform_file(self, number_offset: int) -> None:
        """Сдвигает трек на number_offset точек (для синхронизации)."""
        try:
            tree = ET.parse(config.PATH_TO_GPX)
            root = tree.getroot()
            if number_offset > 0:
                self._add_points(number_offset, root)
            else:
                for _ in range(abs(number_offset)):
                    self._remove_first_point(root)
            tree.write(
                config.PATH_TO_GPX,
                encoding="utf-8",
                xml_declaration=True,
            )
            # Перезагружаем
            self._points.clear()
            self._load()
        except Exception as e:
            print(f"[GPXHandler] transform_file error: {e}")

    def _remove_first_point(self, root: ET.Element) -> None:
        try:
            trkpt = root[2][0][0]
            root[2][0].remove(trkpt)
        except (IndexError, TypeError):
            pass

    def _add_points(self, count: int, root: ET.Element) -> None:
        try:
            coords     = root[2][0][0].attrib
            properties = root[2][0][0]
            trkpt      = self._make_trkpt(coords, properties)
            for _ in range(count):
                root[2][0].insert(0, trkpt)
        except (IndexError, TypeError):
            pass

    def _make_trkpt(
        self, coords: dict, props: ET.Element
    ) -> ET.Element:
        trkpt = ET.Element(
            "trkpt",
            lat=str(coords.get("lat", 0)),
            lon=str(coords.get("lon", 0)),
        )
        tags = ["ele", "time", "course", "speed",
                "geoidheight", "fix", "sat",
                "hdop", "vdop", "pdop"]
        for i, tag in enumerate(tags):
            try:
                ET.SubElement(trkpt, tag).text = str(props[i].text)
            except IndexError:
                ET.SubElement(trkpt, tag).text = "0"
        return trkpt