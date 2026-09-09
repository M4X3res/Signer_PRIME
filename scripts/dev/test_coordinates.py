# -*- coding: utf-8 -*-
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processing.detector_process_pool import ResultAggregatorThread

class FakeGPX:
    def get_current_coordinate(self, idx):
        return (53.9021, 27.5612)  # Минск, WGS84

# Создаём минимальный экземпляр без вызова QThread.__init__
agg = ResultAggregatorThread.__new__(ResultAggregatorThread)
from core.converter import Converter
agg._gpx = FakeGPX()
agg._converter = Converter()

frame_data = {
    "frame_idx": 100,
    "frame_number": 100,
    "gps_data": {"gps_index": 5},
    "detections": [
        {"box": [10, 10, 20, 20], "yolo_class": "krug", "cnn_class": "3.24",
         "text": "", "is_side": False}
    ],
}

print("Testing coordinate conversion...")
signs = agg._build_detected_signs(frame_data)
assert len(signs) == 1, f"Expected 1 sign, got {len(signs)}"

lat, lon = signs[0].latitude, signs[0].longitude
print(f"Coordinates: lat={lat}, lon={lon}")

# WGS84 координаты всегда в диапазоне [-180, 180]; EPSG:32635 (UTM, зона 35N)
# для Беларуси — это величины порядка 300000-700000 (X) и 5900000-6200000 (Y).
assert abs(lat) > 1000 or abs(lon) > 1000, (
    f"Координаты ({lat}, {lon}) похожи на WGS84 градусы — конвертация "
    f"в EPSG:32635 не сработала (снова 'Африка-баг')"
)

print(f"[OK] Coordinate conversion works: {lat:.1f}, {lon:.1f} (EPSG:32635)")
