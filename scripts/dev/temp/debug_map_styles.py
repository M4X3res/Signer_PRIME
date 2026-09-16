"""
Диагностика стилей карты с детальными логами.
Запускает сервер и выводит все запросы к API стилей.
"""
import logging
import os
import json
from flask import Flask, request, jsonify
from configs import config
from configs.settings import get_app_settings

# Настройка детального логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] %(levelname)s [%(name)s]: %(message)s'
)

# Создаём тестовые данные
os.makedirs("test_data", exist_ok=True)
config.PATH_TO_GEOJSON = "test_data/signs.geojson"
config.PATH_TO_GPX = "test_data/track.gpx"

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
        json.dump(test_geojson, f, ensure_ascii=False, indent=2)

if not os.path.exists(config.PATH_TO_GPX):
    test_gpx = """<?xml version="1.0"?>
<gpx version="1.1" creator="test">
  <trk><trkseg>
    <trkpt lat="53.9045" lon="27.5615"><ele>0</ele></trkpt>
    <trkpt lat="53.9050" lon="27.5620"><ele>0</ele></trkpt>
  </trkseg></trk>
</gpx>"""
    with open(config.PATH_TO_GPX, "w", encoding="utf-8") as f:
        f.write(test_gpx)

# Загружаем настройки
settings = get_app_settings()

print(f"\n{'='*70}")
print(f"  🗺️  ДИАГНОСТИКА СТИЛЕЙ КАРТЫ")
print(f"{'='*70}\n")
print(f"Текущие настройки:")
print(f"  - Tile Type: {settings.map_tile_type}")
print(f"  - Tile URL: {settings.map_tile_url[:80]}...")
print(f"  - Use Proxy: {settings.map_tile_use_proxy}")
print(f"  - Max Zoom: {settings.map_tile_max_zoom}")

# Импортируем сервер
from server.map_server import app, socketio

# Добавляем дополнительное логирование для отладки
@app.before_request
def log_request():
    if request.path.startswith('/api/'):
        print(f"\n{'─'*70}")
        print(f"📥 REQUEST: {request.method} {request.path}")
        if request.args:
            print(f"   Query: {dict(request.args)}")

@app.after_request
def log_response(response):
    if request.path.startswith('/api/'):
        print(f"📤 RESPONSE: {response.status_code}")
        
        # Для стилей и конфигурации выводим тело ответа
        if request.path in ['/api/map_config', '/api/vector_tile_style']:
            try:
                if response.content_type and 'json' in response.content_type:
                    data = response.get_json()
                    print(f"   Body: {json.dumps(data, indent=2)[:500]}")
            except:
                pass
        
        print(f"{'─'*70}")
    
    return response

if __name__ == "__main__":
    PORT = 3000
    
    print(f"\n{'='*70}")
    print(f"  🚀 Сервер запущен с детальными логами")
    print(f"{'='*70}\n")
    print(f"  📍 Откройте: http://127.0.0.1:{PORT}")
    print(f"  🔍 Откройте DevTools браузера (F12) и смотрите вкладку Console")
    print(f"\n  ℹ️  В консоли браузера ищите сообщения:")
    print(f"     - [loadTileLayer] Config loaded")
    print(f"     - [loadTileLayer] Attempting to load vector tile styles")
    print(f"     - [loadTileLayer] Styles loaded successfully")
    print(f"     - [VectorGrid] Tile loaded / Tile error")
    print(f"\n  Для остановки: Ctrl+C\n")
    
    socketio.run(
        app,
        host='127.0.0.1',
        port=PORT,
        debug=False,  # Отключаем Flask debug чтобы не было дублей логов
        use_reloader=False,
        allow_unsafe_werkzeug=True
    )
