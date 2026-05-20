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
            for track in gpx.tracks:
                for segment in track.segments:
                    for pt in segment.points:
                        self._points.append(GPSPoint(
                            latitude  = pt.latitude,
                            longitude = pt.longitude,
                            course    = float(pt.course or 0),
                            speed     = float(pt.speed or 0),
                            elevation = float(pt.elevation or 0),
                        ))
        except Exception as e:
            print(f"[GPXHandler] Ошибка загрузки GPX: {e}")

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