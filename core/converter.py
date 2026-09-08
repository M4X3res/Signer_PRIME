"""
core/converter.py
Конвертация координат между проекциями.
Заменяет старый Converter.py.
"""
from __future__ import annotations
from pyproj import Transformer
from functools import lru_cache


@lru_cache(maxsize=16)
def _get_transformer(epsg1: str, epsg2: str) -> Transformer:
    """Кешируем трансформеры — создание стоит ~10мс."""
    return Transformer.from_crs(epsg1, epsg2, always_xy=False)


class Converter:
    def coordinateConverter(
        self,
        lat: float,
        lon: float,
        epsg1: str,
        epsg2: str,
    ) -> tuple[float, float]:
        """
        Конвертирует координаты из epsg1 в epsg2.
        Порядок аргументов совпадает с оригинальным Converter.py.
        """
        transformer = _get_transformer(epsg1, epsg2)
        return transformer.transform(lat, lon)

    @staticmethod
    def convert(
        lat: float, lon: float,
        epsg1: str, epsg2: str,
    ) -> tuple[float, float]:
        """Статический вариант для удобства."""
        transformer = _get_transformer(epsg1, epsg2)
        return transformer.transform(lat, lon)