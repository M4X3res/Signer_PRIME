"""
Тестовый сервер с подробными логами запросов к стилям.
"""
import os
import json
import logging

# Настраиваем детальное логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)

# Создаём тестовые данные
from configs import config

os.makedirs("test_data", exist_ok=True)
config.PATH_TO_GEOJSON = "test_data/signs.geojson"
config.PATH_TO_GPX = "test_data/track.gpx"
config.PATH_TO_VIDEO = "test_data/videos"
config.VIDEOS = []

if not os.path.exists(config.PATH_TO_GEOJSON):
    test_geojson = {
        "type": "FeatureCollection",
        "features": [{
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
            }
        }]
    }
    with open(config.PATH_TO_GEOJSON, "w", encoding="utf-8") as f:
        json.dump(test_geojson, f)

if not os.path.exists(config.PATH_TO_GPX):
    test_gpx = """<?xml version="1.0"?>
<gpx version="1.1"><trk><trkseg>
<trkpt lat="53.9045" lon="27.5615"><ele>0</ele></trkpt>
<trkpt lat="53.9050" lon="27.5620"><ele>0</ele></trkpt>
</trkseg></trk></gpx>"""
    with open(config.PATH_TO_GPX, "w") as f:
        f.write(test_gpx)

# Импортируем сервер
from server.map_server import app, socketio

print(f"\n{'='*70}")
print(f"  🗺️  ТЕСТОВЫЙ СЕРВЕР С ЛОГАМИ СТИЛЕЙ")
print(f"{'='*70}\n")
print(f"  📍 URL: http://127.0.0.1:3000")
print(f"  🔍 Откройте DevTools (F12) → вкладка Console")
print(f"  📋 Следите за логами здесь в терминале\n")
print(f"  ⏳ Ожидание запросов...\n")

if __name__ == "__main__":
    socketio.run(
        app,
        host='127.0.0.1',
        port=3000,
        debug=False,
        use_reloader=False,
        allow_unsafe_werkzeug=True,
        log_output=True
    )
