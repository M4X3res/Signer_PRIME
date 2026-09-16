"""
Тестовый сервер для проверки стилей карты в браузере.
Запускает только Flask-сервер без PyQt для быстрой итерации по стилям.
"""
import logging
import os

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s'
)

# Инициализируем минимальную конфигурацию
from configs import config

# Устанавливаем тестовые пути (если есть реальные данные - замените)
config.PATH_TO_GEOJSON = "test_data/signs.geojson"
config.PATH_TO_GPX = "test_data/track.gpx"
config.PATH_TO_VIDEO = "test_data/videos"
config.VIDEOS = []

# Создаём тестовые данные если их нет
os.makedirs("test_data", exist_ok=True)

if not os.path.exists(config.PATH_TO_GEOJSON):
    import json
    test_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[27.5615, 53.9045], [27.5617, 53.9047]]
                },
                "properties": {
                    "id": "test-1",
                    "type": "3.24",
                    "code": 324,
                    "azimuth": 90,
                    "SEM250": "50",
                    "side": False,
                    "time": "00:00:10",
                }
            }
        ]
    }
    with open(config.PATH_TO_GEOJSON, "w", encoding="utf-8") as f:
        json.dump(test_geojson, f, ensure_ascii=False, indent=2)
    print(f"✓ Создан тестовый GeoJSON: {config.PATH_TO_GEOJSON}")

if not os.path.exists(config.PATH_TO_GPX):
    test_gpx = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test">
  <trk>
    <trkseg>
      <trkpt lat="53.9045" lon="27.5615"><ele>0</ele></trkpt>
      <trkpt lat="53.9050" lon="27.5620"><ele>0</ele></trkpt>
      <trkpt lat="53.9055" lon="27.5625"><ele>0</ele></trkpt>
    </trkseg>
  </trk>
</gpx>"""
    with open(config.PATH_TO_GPX, "w", encoding="utf-8") as f:
        f.write(test_gpx)
    print(f"✓ Создан тестовый GPX: {config.PATH_TO_GPX}")

# Импортируем и запускаем сервер
from server.map_server import app, socketio

if __name__ == "__main__":
    PORT = 3000
    print(f"\n{'='*60}")
    print(f"  🗺️  Тестовый сервер карты запущен")
    print(f"{'='*60}")
    print(f"\n  📍 Откройте в браузере: http://127.0.0.1:{PORT}\n")
    print(f"  Для остановки: Ctrl+C\n")
    
    # Запускаем сервер
    socketio.run(
        app,
        host='127.0.0.1',
        port=PORT,
        debug=True,
        use_reloader=False,  # Отключаем reloader для стабильности
        allow_unsafe_werkzeug=True
    )
