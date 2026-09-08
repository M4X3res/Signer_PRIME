"""
MapServer — Flask-сервер карты.
Запускается в отдельном QThread, общается с UI через pyqtSignal.
Не импортирует ничего из PyQt напрямую — только через сигналы.
"""
import os
import uuid
import json
import logging
from datetime import timedelta

import flask
import geojson
import gpxpy
from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS
from flask_socketio import SocketIO

from configs import config
# BLOCK P.2: Прямой импорт из sign_data вместо легаси-шима sign_config
from configs.sign_data import (
    TYPE_SIGNS_WITH_TEXT as type_signs_with_text,
    CODES_SIGNS as codes_signs,
    SIGNS_WITH_TEXT as signs_with_various_text,  # BLOCK FIX-1.1: было SIGNS_WITH_VARIOUS_TEXT
    TYPE_SIGNS_CITY as type_signs_city,
)
from utils import resource_path

logger = logging.getLogger(__name__)

# ── Пути к ресурсам ────────────────────────────────────────────────────────
TEMPLATES_DIR  = resource_path("templates")
STATIC_DIR     = resource_path("static")
SIGNS_DIR      = resource_path("sings")
SIGNS_TEXT_DIR = resource_path("sings_text")

# ── Приложение ─────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder=TEMPLATES_DIR, static_folder=STATIC_DIR)
CORS(app)

# Используем eventlet для более стабильной работы в Windows с Qt
# threading может вызывать конфликты с Qt WebEngine и OpenMP
socketio = SocketIO(
    app, 
    cors_allowed_origins="*", 
    async_mode="threading",
    logger=False,  # Отключаем логгер для избежания конфликтов I/O
    engineio_logger=False,  # Отключаем engineio логгер
    ping_timeout=60,
    ping_interval=25
)

# Колбэки — устанавливаются снаружи через set_callbacks()
_on_jump_to_second: callable = None   # (seconds: int) → None
_on_sign_updated:   callable = None   # (sign_id: str)  → None

# Флаги состояния
_processing_active = False
_data_ready = False


def set_callbacks(on_jump=None, on_sign_updated=None):
    global _on_jump_to_second, _on_sign_updated
    _on_jump_to_second  = on_jump
    _on_sign_updated    = on_sign_updated


def set_processing_state(active: bool):
    """Устанавливает состояние обработки."""
    global _processing_active
    _processing_active = active
    socketio.emit("processing_state", {"active": active})


def emit_processing_finished(sign_count: int):
    """Уведомляет клиентов о завершении обработки."""
    global _processing_active, _data_ready
    _processing_active = False
    _data_ready = True
    logger.info(f"[MapServer] Отправляем processing_finished: {sign_count} знаков")
    socketio.emit("processing_finished", {"count": sign_count, "ready": True})


def notify_data_ready():
    """Уведомляет клиентов о готовности данных."""
    global _data_ready
    _data_ready = True
    socketio.emit("data_ready", {"ready": True})


# ── Утилиты ────────────────────────────────────────────────────────────────

def _load_geojson() -> dict:
    with open(config.PATH_TO_GEOJSON, encoding="utf-8") as f:
        return geojson.load(f)


def _save_geojson(data: dict):
    with open(config.PATH_TO_GEOJSON, "w", encoding="utf-8") as f:
        geojson.dump(data, f, ensure_ascii=False)


def _sign_img_path(sign_type: str, description: str = "") -> str:
    """Возвращает путь к PNG иконке знака (с текстом если нужно)."""
    if description and sign_type in signs_with_various_text:
        fname   = f"V{sign_type}-{description}.png"
        fpath   = os.path.join(SIGNS_TEXT_DIR, fname)
        if not os.path.exists(fpath):
            _render_text_sign(sign_type, description, fpath)
        return fpath
    return os.path.join(SIGNS_DIR, f"V{sign_type}.png")


def _render_text_sign(sign_type: str, description: str, out_path: str):
    """Рисует текст поверх базового изображения знака."""
    from PIL import Image, ImageDraw, ImageFont
    base_path = os.path.join(SIGNS_TEXT_DIR, f"V{sign_type}.png")
    if not os.path.exists(base_path):
        return
    img  = Image.open(base_path)
    draw = ImageDraw.Draw(img)
    font_size = 12 if sign_type in type_signs_city else 20
    font_path = resource_path("assets/fonts/arial.ttf")
    font = ImageFont.truetype(font_path, font_size)
    w, h = img.size
    tx = w // 8 if sign_type == "8.2.2" else w // 3
    ty = h // 5 if sign_type in type_signs_city else h // 3
    draw.text((tx, ty), description, fill="black", font=font)
    img.save(out_path)


# ── Роуты ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Главная страница карты — Leaflet."""
    return flask.render_template("map.html")


@app.route("/api/track")
def api_track():
    """GPS-трек в виде массива [lat, lon]."""
    try:
        logger.info(f"[API /api/track] Запрос получен")
        logger.info(f"[API /api/track] PATH_TO_GPX = {config.PATH_TO_GPX}")
        
        if not config.PATH_TO_GPX:
            logger.info("[API /api/track] PATH_TO_GPX пустой")
            return jsonify([])
        if not os.path.exists(config.PATH_TO_GPX):
            logger.info(f"[API /api/track] Файл не найден: {config.PATH_TO_GPX}")
            return jsonify([])
        
        logger.info(f"[API /api/track] Загружаем GPX из {config.PATH_TO_GPX}")
        points = []
        with open(config.PATH_TO_GPX, encoding="utf-8") as f:
            gpx = gpxpy.parse(f)
        
        for track in gpx.tracks:
            for segment in track.segments:
                for pt in segment.points:
                    points.append([pt.latitude, pt.longitude])
        
        logger.info(f"[API /api/track] Найдено {len(points)} точек трека")
        return jsonify(points)
    except FileNotFoundError:
        logger.info("[API /api/track] FileNotFoundError")
        return jsonify([])
    except Exception as e:
        logger.error(f"ERROR in /api/track: {e}")
        import traceback
        traceback.print_exc()
        return jsonify([]), 200  # Возвращаем пустой массив вместо ошибки


@app.route("/api/map_config")
def api_map_config():
    """Конфигурация подложки карты (тайловый сервер, атрибуция, zoom)."""
    try:
        from configs.settings import get_app_settings
        settings = get_app_settings()
        return jsonify({
            "tile_url": settings.map_tile_url,
            "attribution": settings.map_tile_attribution,
            "max_zoom": settings.map_tile_max_zoom,
        })
    except Exception as e:
        logger.error(f"ERROR in /api/map_config: {e}")
        # Безопасный fallback на OSM, чтобы карта не осталась совсем без подложки
        return jsonify({
            "tile_url": "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            "attribution": "© OpenStreetMap",
            "max_zoom": 19,
        })


@app.route("/api/signs")
def api_signs():
    """Все знаки из GeoJSON в упрощённом формате для Leaflet."""
    try:
        logger.info(f"[API /api/signs] Запрос получен")
        logger.info(f"[API /api/signs] PATH_TO_GEOJSON = {config.PATH_TO_GEOJSON}")
        
        if not config.PATH_TO_GEOJSON:
            logger.info("[API /api/signs] PATH_TO_GEOJSON пустой")
            return jsonify([])
        if not os.path.exists(config.PATH_TO_GEOJSON):
            logger.info(f"[API /api/signs] Файл не найден: {config.PATH_TO_GEOJSON}")
            return jsonify([])
        
        logger.info(f"[API /api/signs] Загружаем GeoJSON из {config.PATH_TO_GEOJSON}")
        data    = _load_geojson()
        features = data.get("features", [])
        logger.info(f"[API /api/signs] Найдено {len(features)} features в GeoJSON")
        
        result  = []
        for feat in features:
            props = feat.get("properties", {})
            geom = feat.get("geometry", {})
            coords = geom.get("coordinates", [])
            
            if not coords or len(coords) == 0:
                logger.info(f"[API /api/signs] Пропускаем feature без координат: {props.get('id', 'unknown')}")
                continue
            
            # GeoJSON LineString: coordinates = [[lon, lat], [lon, lat], ...]
            # Берём первую точку линии как позицию маркера
            try:
                first_point = coords[0]
                if not isinstance(first_point, (list, tuple)) or len(first_point) < 2:
                    logger.info(f"[API /api/signs] Некорректный формат координат для {props.get('id', 'unknown')}: {first_point}")
                    continue
                    
                lon, lat = first_point[0], first_point[1]
                
                # Проверяем что координаты валидные
                if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                    logger.info(f"[API /api/signs] Невалидные координаты для {props.get('id', 'unknown')}: lon={lon}, lat={lat}")
                    continue
                    
            except (IndexError, TypeError, ValueError) as e:
                logger.info(f"[API /api/signs] Ошибка парсинга координат для {props.get('id', 'unknown')}: {e}")
                continue
            
            # Преобразуем side из строки в bool для удобства на фронтенде
            # Поддерживаем оба формата: "True"/"False" (старый) и bool (новый)
            side_raw = props.get("side", "")
            if isinstance(side_raw, bool):
                side_bool = side_raw
            else:
                side_bool = str(side_raw).strip().lower() in ("true", "1", "yes")
            
            result.append({
                "id":          props.get("id", str(uuid.uuid4())),
                "type":        props.get("type", ""),
                "code":        props.get("code", ""),
                "azimuth":     props.get("azimuth", 0),
                "description": props.get("SEM250", ""),
                "side":        side_bool,  # Теперь bool
                "time":        props.get("time", ""),
                "name_video":  props.get("name_video", ""),
                "abs_frame":   props.get("absolute_frame_numbers", ""),
                "lat":         lat,
                "lon":         lon,
                "line":        coords,          # полная линия для отображения
            })
        logger.info(f"[API /api/signs] Возвращаем {len(result)} знаков клиенту")
        return jsonify(result)
    except FileNotFoundError:
        logger.info("[API /api/signs] FileNotFoundError")
        return jsonify([])
    except Exception as e:
        logger.error(f"ERROR in /api/signs: {e}")
        import traceback
        traceback.print_exc()
        return jsonify([]), 200  # Возвращаем пустой массив вместо ошибки


@app.route("/api/sign/<sign_id>")
def api_sign_detail(sign_id: str):
    """Детали одного знака по ID."""
    logger.info(f"[API /api/sign/{sign_id}] Запрос получен")
    
    if not config.PATH_TO_GEOJSON:
        logger.error(f"[API /api/sign/{sign_id}] PATH_TO_GEOJSON не установлен")
        return jsonify({"error": "GeoJSON path not configured"}), 500
        
    if not os.path.exists(config.PATH_TO_GEOJSON):
        logger.error(f"[API /api/sign/{sign_id}] Файл не найден: {config.PATH_TO_GEOJSON}")
        return jsonify({"error": "GeoJSON file not found"}), 404
        
    try:
        data = _load_geojson()
        features = data.get("features", [])
        logger.info(f"[API /api/sign/{sign_id}] Найдено {len(features)} features в GeoJSON")
        
        for feat in features:
            feat_id = feat.get("properties", {}).get("id")
            if feat_id == sign_id:
                logger.info(f"[API /api/sign/{sign_id}] Знак найден")
                return jsonify(feat)
        
        logger.warning(f"[API /api/sign/{sign_id}] Знак не найден в GeoJSON")
        return jsonify({"error": f"Sign with id '{sign_id}' not found"}), 404
        
    except Exception as e:
        logger.error(f"[API /api/sign/{sign_id}] Ошибка при загрузке: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Server error: {str(e)}"}), 500


@app.route("/api/sign", methods=["POST"])
def api_sign_create():
    """
    Создание нового знака (BLOCK S.1).
    Body: {
        "type": "3.24",
        "lat": 53.905,
        "lon": 27.560,
        "azimuth": 90.0,        # Опционально, default=0
        "description": "5"      # Опционально, для знаков с текстом
    }
    """
    body = request.get_json(silent=True) or {}
    
    # Валидация обязательных полей
    if "type" not in body or "lat" not in body or "lon" not in body:
        return jsonify({"error": "Missing required fields: type, lat, lon"}), 400
    
    sign_type = body["type"]
    if sign_type not in codes_signs:
        return jsonify({"error": f"Unknown sign type: {sign_type}"}), 400
    
    try:
        lat = float(body["lat"])
        lon = float(body["lon"])
        azimuth = float(body.get("azimuth", 0.0))
        description = body.get("description", "")
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Invalid coordinate format: {e}"}), 400
    
    # Загружаем существующий GeoJSON
    if not os.path.exists(config.PATH_TO_GEOJSON):
        # Если файла нет, создаём пустой FeatureCollection
        data = {"type": "FeatureCollection", "features": []}
    else:
        data = _load_geojson()
    
    # Генерируем уникальный ID
    import uuid
    sign_id = str(uuid.uuid4())
    
    # Создаём вторую точку линии через азимут (для визуализации направления)
    from core.coordinate_calculation import CoordinateCalculation
    calc = CoordinateCalculation()
    lat2, lon2 = calc.point_at_distance(lat, lon, azimuth, 5.0)  # 5м - стандартная длина
    
    # Создаём Feature
    feature = {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [[lon, lat], [lon2, lat2]]
        },
        "properties": {
            "id": sign_id,
            "type": sign_type,
            "code": int(codes_signs[sign_type]),
            "azimuth": azimuth,
            "left": "manually_added",  # Маркер что знак добавлен вручную
            "conf_cnn": 1.0,           # Максимальная уверенность для ручных знаков
            "conf_total": 1.0,
            "length": 1,               # Одно наблюдение
        }
    }
    
    # Добавляем описание для знаков с текстом
    if sign_type in type_signs_with_text and description:
        feature["properties"]["SEM250"] = description
        feature["properties"]["MVALUE"] = description
    
    # Добавляем в коллекцию
    data["features"].append(feature)
    
    # Сохраняем
    _save_geojson(data)
    
    # Уведомляем клиентов
    socketio.emit("new_sign", {"id": sign_id, "feature": feature})
    
    logger.info(f"[API POST /api/sign] Создан новый знак: {sign_id}, type={sign_type}, lat={lat}, lon={lon}")
    
    return jsonify({"ok": True, "id": sign_id, "feature": feature}), 201


@app.route("/api/sign/<sign_id>", methods=["PATCH"])
def api_sign_update(sign_id: str):
    """
    Обновление знака.
    Body: { 
        "type": "3.24", 
        "description": "5",
        "lat": 53.905,        # Опционально (BLOCK S.2)
        "lon": 27.560,        # Опционально (BLOCK S.2)
        "azimuth": 90.0       # Опционально (BLOCK S.2)
    }
    """
    body = request.get_json(silent=True) or {}
    if not os.path.exists(config.PATH_TO_GEOJSON):
        return jsonify({"error": "no geojson"}), 404

    data    = _load_geojson()
    updated = False
    for feat in data.get("features", []):
        if feat["properties"].get("id") == sign_id:
            # Обновление типа и описания (существующий функционал)
            new_type = body.get("type", feat["properties"]["type"])
            new_desc = body.get("description", feat["properties"].get("SEM250", ""))

            feat["properties"]["type"] = new_type
            if new_type in codes_signs:
                feat["properties"]["code"] = int(codes_signs[new_type])
            if new_type in type_signs_with_text:
                feat["properties"]["SEM250"]  = new_desc
                feat["properties"]["MVALUE"]  = new_desc
            else:
                feat["properties"].pop("SEM250", None)
                feat["properties"].pop("MVALUE", None)
            
            # BLOCK S.2: Обновление координат (draggable markers)
            if "lat" in body and "lon" in body:
                new_lat = float(body["lat"])
                new_lon = float(body["lon"])
                
                # Обновляем геометрию (LineString с двумя точками)
                if feat["geometry"]["type"] == "LineString":
                    coords = feat["geometry"]["coordinates"]
                    if len(coords) >= 2:
                        # Обновляем первую точку
                        coords[0][0] = new_lon
                        coords[0][1] = new_lat
                        
                        # Если есть азимут, пересчитываем вторую точку
                        if "azimuth" in body or "azimuth" in feat["properties"]:
                            azimuth = float(body.get("azimuth", feat["properties"].get("azimuth", 0)))
                            # Используем CoordinateCalculation для точного расчёта
                            from core.coordinate_calculation import CoordinateCalculation
                            calc = CoordinateCalculation()
                            # Длина линии ~5м (стандартная для визуализации направления)
                            new_lat2, new_lon2 = calc.point_at_distance(new_lat, new_lon, azimuth, 5.0)
                            coords[1][0] = new_lon2
                            coords[1][1] = new_lat2
                            feat["properties"]["azimuth"] = azimuth
            
            updated = True
            break

    if not updated:
        return jsonify({"error": "not found"}), 404

    _save_geojson(data)
    if _on_sign_updated:
        _on_sign_updated(sign_id)
    socketio.emit("sign_updated", {"id": sign_id})
    return jsonify({"ok": True})


@app.route("/api/sign/<sign_id>", methods=["DELETE"])
def api_sign_delete(sign_id: str):
    """Удаление знака по ID."""
    if not os.path.exists(config.PATH_TO_GEOJSON):
        return jsonify({"error": "no geojson"}), 404
    data = _load_geojson()
    before = len(data["features"])
    data["features"] = [
        f for f in data["features"]
        if f["properties"].get("id") != sign_id
    ]
    if len(data["features"]) == before:
        return jsonify({"error": "not found"}), 404
    _save_geojson(data)
    socketio.emit("sign_deleted", {"id": sign_id})
    return jsonify({"ok": True})


@app.route("/api/jump")
def api_jump():
    """Прыжок к секунде видео. ?seconds=120"""
    try:
        seconds = int(request.args.get("seconds", 0))
        config.SECONDS_ALL_VIDEO = seconds
        if _on_jump_to_second:
            _on_jump_to_second(seconds)
        socketio.emit("jump", seconds)
        return jsonify({"seconds": seconds, "ok": True})
    except Exception as e:
        logger.error(f"ERROR in /api/jump: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/sign_types")
def api_sign_types():
    """Все доступные типы знаков (для dropdown в редакторе)."""
    from configs.sign_config import names_signs_by_type
    result = [
        {"type": k, "name": v}
        for k, v in names_signs_by_type.items()
        if k in codes_signs
    ]
    result.sort(key=lambda x: x["type"])
    return jsonify(result)


@app.route("/api/img/<path:image_id>")
def api_img(image_id: str):
    """Иконка знака. /api/img/3.24 или /api/img/3.24-5"""
    if "-" in image_id:
        sign_type, desc = image_id.split("-", 1)
    else:
        sign_type, desc = image_id, ""
    path = _sign_img_path(sign_type, desc)
    
    # Нормализуем путь для Windows
    path = os.path.normpath(os.path.abspath(path))
    
    if not os.path.exists(path):
        # fallback — пустой PNG
        fallback_path = os.path.normpath(os.path.abspath(os.path.join(SIGNS_DIR, "V1.1.png")))
        return send_file(fallback_path, mimetype="image/png")
    
    return send_file(path, mimetype="image/png")


@app.route("/api/video_clip/<int:video_idx>")
def api_video_clip(video_idx: int):
    """
    ЗАДАЧА 3 (Путь A): Раздача короткого WebM-клипа для плеера на карте.
    Транскодирует H.264 → VP9+Opus через ffmpeg с кэшированием на диске.
    
    Query params:
        start (float): секунда начала клипа (default: 0)
        duration (float): длина клипа в секундах (default: 15)
    """
    import shutil
    import subprocess
    
    start = float(request.args.get('start', 0))
    duration = float(request.args.get('duration', 15))
    
    logger.info(f"[API /api/video_clip/{video_idx}] start={start}, duration={duration}")
    
    # Проверяем индекс видео
    if not config.VIDEOS or video_idx >= len(config.VIDEOS):
        return jsonify({"error": "video not found"}), 404
    
    # Получаем путь к исходному видео
    if config.PATH_TO_VIDEO:
        video_path = os.path.join(config.PATH_TO_VIDEO, config.VIDEOS[video_idx])
    else:
        video_path = config.VIDEOS[video_idx]
    
    video_path = os.path.normpath(os.path.abspath(video_path))
    
    if not os.path.exists(video_path):
        return jsonify({"error": "video file not found"}), 404
    
    # Проверяем наличие ffmpeg
    if not shutil.which("ffmpeg"):
        logger.error("[API /api/video_clip] ffmpeg не найден в PATH")
        return jsonify({
            "error": "ffmpeg not found",
            "message": "Для воспроизведения видео требуется ffmpeg. Установите его и добавьте в PATH.",
            "install_url": "https://ffmpeg.org/download.html"
        }), 503
    
    # Формируем путь к кэшу рядом с видео
    video_dir = os.path.dirname(video_path)
    video_base = os.path.splitext(os.path.basename(video_path))[0]
    
    # duration=0 означает "всё видео от start до конца"
    if duration == 0:
        cache_filename = f"{video_base}_full.webm"
    else:
        cache_filename = f"{video_base}_clip_{int(round(start))}_{int(duration)}.webm"
    
    cache_path = os.path.join(video_dir, cache_filename)
    
    # Если кэш существует - отдаем его
    if os.path.exists(cache_path):
        logger.info(f"[API /api/video_clip] Cache hit: {cache_path}")
        return send_file(cache_path, mimetype='video/webm', as_attachment=False)
    
    # Транскодируем через ffmpeg
    logger.info(f"[API /api/video_clip] Транскодирование: {video_path} -> {cache_path}")
    
    try:
        # Параметры ffmpeg (Task D):
        # -ss перед -i для быстрого seek по ключевым кадрам (только если start > 0)
        # -t <duration> - длина клипа (если задана)
        # -c:v libvpx-vp9 - VP9 видеокодек
        # -deadline realtime - БЫСТРЫЙ кодинг (для коротких клипов)
        # -cpu-used 8 - максимальная скорость (минимальное качество, но приемлемое для превью)
        # -b:v 1M - битрейт видео 1 Мбит/с (компромисс скорость/качество)
        # -c:a libopus - Opus аудиокодек
        # -f webm - контейнер WebM
        cmd = ['ffmpeg']
        
        # Добавляем -ss только если start > 0
        if start > 0:
            cmd.extend(['-ss', str(start)])
        
        cmd.extend(['-i', video_path])
        
        # Добавляем -t только если duration > 0
        if duration > 0:
            cmd.extend(['-t', str(duration)])
        
        cmd.extend([
            '-c:v', 'libvpx-vp9',
            '-deadline', 'realtime',  # Task D: быстрый кодинг
            '-cpu-used', '8',          # Task D: максимальная скорость
            '-b:v', '1M',
            '-c:a', 'libopus',
            '-f', 'webm',
            '-y',  # overwrite output
            cache_path
        ])
        
        logger.info(f"[API /api/video_clip] Запуск ffmpeg: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60  # таймаут 60 секунд
        )
        
        if result.returncode != 0:
            stderr_output = result.stderr.decode('utf-8', errors='ignore')
            logger.error(f"[API /api/video_clip] ffmpeg failed: {stderr_output}")
            return jsonify({
                "error": "ffmpeg transcoding failed",
                "details": stderr_output[-500:]  # последние 500 символов
            }), 500
        
        logger.info(f"[API /api/video_clip] Транскодирование завершено: {cache_path}")
        
        if not os.path.exists(cache_path):
            logger.error("[API /api/video_clip] Кэш-файл не создан")
            return jsonify({"error": "transcode completed but cache file not found"}), 500
        
        return send_file(cache_path, mimetype='video/webm', as_attachment=False)
        
    except subprocess.TimeoutExpired:
        logger.error("[API /api/video_clip] ffmpeg timeout")
        return jsonify({"error": "transcode timeout (60s)"}), 504
    except Exception as e:
        logger.error(f"[API /api/video_clip] Unexpected error: {e}", exc_info=True)
        return jsonify({"error": f"transcode error: {str(e)}"}), 500


@app.route("/api/video/<int:video_idx>")
def api_video(video_idx: int):
    """
    ЗАДАЧА 3: Раздача видеофайла для встроенного плеера на карте.
    Поддерживает Range-запросы для перемотки.
    Используется для диагностики кодеков (testVideoCodec).
    """
    logger.info(f"[API /api/video/{video_idx}] Запрос видео")
    
    if not config.VIDEOS or video_idx >= len(config.VIDEOS):
        logger.info(f"[API /api/video/{video_idx}] Видео не найдено: idx={video_idx}, len={len(config.VIDEOS) if config.VIDEOS else 0}")
        return jsonify({"error": "video not found"}), 404
    
    # Формируем полный путь к видеофайлу
    if config.PATH_TO_VIDEO:
        video_path = os.path.join(config.PATH_TO_VIDEO, config.VIDEOS[video_idx])
    else:
        video_path = config.VIDEOS[video_idx]
    
    # Нормализуем путь для Windows
    video_path = os.path.normpath(os.path.abspath(video_path))
    
    if not os.path.exists(video_path):
        logger.info(f"[API /api/video/{video_idx}] Файл не существует: {video_path}")
        return jsonify({"error": "video file not found"}), 404
    
    logger.info(f"[API /api/video/{video_idx}] Раздаём: {video_path}")
    
    # Определяем mimetype по расширению
    ext = os.path.splitext(video_path)[1].lower()
    mimetype_map = {
        '.mp4': 'video/mp4',
        '.avi': 'video/x-msvideo',
        '.mov': 'video/quicktime',
        '.mkv': 'video/x-matroska',
        '.webm': 'video/webm',
    }
    mimetype = mimetype_map.get(ext, 'video/mp4')
    
    # Получаем размер файла
    file_size = os.path.getsize(video_path)
    
    # Обрабатываем Range-запросы для поддержки перемотки
    range_header = request.headers.get('Range')
    
    if range_header:
        # BLOCK VIDEO-FIX: Корректный парсинг Range согласно RFC 7233
        # Поддержка всех трёх форм: bytes=start-end, bytes=start-, bytes=-suffix
        range_spec = range_header.replace('bytes=', '').strip()
        if '-' not in range_spec:
            return jsonify({"error": "Malformed Range header"}), 416
        
        range_start_str, range_end_str = range_spec.split('-', 1)
        
        if range_start_str == '':
            # Suffix range: "bytes=-500" = последние 500 байт файла
            if range_end_str == '':
                return jsonify({"error": "Malformed Range header"}), 416
            suffix_length = int(range_end_str)
            start = max(0, file_size - suffix_length)
            end = file_size - 1
        else:
            start = int(range_start_str)
            end = int(range_end_str) if range_end_str != '' else file_size - 1
        
        # Валидация границ (RFC 7233: невалидный диапазон -> 416)
        if start >= file_size or start > end:
            response = Response(status=416)
            response.headers.set('Content-Range', f'bytes */{file_size}')
            return response
        end = min(end, file_size - 1)
        
        # Увеличиваем лимит на чанк (было 10MB — для больших файлов это много round-trip'ов)
        MAX_CHUNK = 50 * 1024 * 1024
        if end - start + 1 > MAX_CHUNK:
            end = start + MAX_CHUNK - 1
        
        logger.info(f"[API /api/video/{video_idx}] Range request: {start}-{end}/{file_size}")
        
        def generate():
            with open(video_path, 'rb') as f:
                f.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = f.read(min(8192, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk
        
        response = Response(generate(), 206, mimetype=mimetype)
        response.headers.set('Content-Range', f'bytes {start}-{end}/{file_size}')
        response.headers.set('Accept-Ranges', 'bytes')
        response.headers.set('Content-Length', str(end - start + 1))
        response.headers.set('Access-Control-Allow-Origin', '*')
        response.headers.set('Access-Control-Expose-Headers', 'Content-Range, Content-Length, Accept-Ranges')
        return response
    else:
        # Полная отдача файла (без Range)
        logger.info(f"[API /api/video/{video_idx}] Полная отдача файла: {file_size} bytes")
        response = send_file(video_path, mimetype=mimetype, as_attachment=False, conditional=False)
        response.headers.set('Accept-Ranges', 'bytes')
        response.headers.set('Content-Length', str(file_size))
        response.headers.set('Cache-Control', 'public, max-age=3600')
        response.headers.set('Access-Control-Allow-Origin', '*')
        response.headers.set('Access-Control-Expose-Headers', 'Content-Range, Content-Length, Accept-Ranges')
        return response


@app.route("/api/video_codec/<int:video_idx>")
def api_video_codec(video_idx: int):
    """
    Диагностика: Возвращает информацию о кодеках видео.
    """
    if not config.VIDEOS or video_idx >= len(config.VIDEOS):
        return jsonify({"error": "video not found"}), 404
    
    # Формируем полный путь к видеофайлу
    if config.PATH_TO_VIDEO:
        video_path = os.path.join(config.PATH_TO_VIDEO, config.VIDEOS[video_idx])
    else:
        video_path = config.VIDEOS[video_idx]
    
    if not os.path.exists(video_path):
        return jsonify({"error": "video file not found"}), 404
    
    try:
        import cv2
        import subprocess
        
        # Получаем информацию через cv2
        cap = cv2.VideoCapture(video_path)
        cv2_info = {
            "fps": cap.get(cv2.CAP_PROP_FPS),
            "frame_count": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fourcc": int(cap.get(cv2.CAP_PROP_FOURCC)),
        }
        cap.release()
        
        # Пытаемся получить детальную информацию через ffprobe
        ffprobe_info = None
        try:
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 
                 'stream=codec_name,codec_type,profile,level', 
                 '-of', 'json', video_path],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                import json as json_lib
                ffprobe_data = json_lib.loads(result.stdout)
                ffprobe_info = ffprobe_data.get('streams', [])
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
            logger.info(f"[API /api/video_codec/{video_idx}] ffprobe недоступен: {e}")
        
        return jsonify({
            "video_idx": video_idx,
            "path": os.path.basename(video_path),
            "size_mb": round(os.path.getsize(video_path) / (1024 * 1024), 2),
            "cv2": cv2_info,
            "ffprobe": ffprobe_info,
        })
        
    except Exception as e:
        logger.info(f"[API /api/video_codec/{video_idx}] Ошибка: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/video_info/<int:video_idx>")
def api_video_info(video_idx: int):
    """
    Task C: Возвращает метаинформацию о видео (FPS, длительность).
    ИСПРАВЛЕН: frames_per_video_hint теперь возвращает РЕАЛЬНОЕ frame_count этого видео,
    а не захардкоженную константу config.FRAMES_PER_VIDEO.
    """
    if not config.VIDEOS or video_idx >= len(config.VIDEOS):
        return jsonify({"error": "video not found"}), 404
    
    # Формируем полный путь к видеофайлу
    if config.PATH_TO_VIDEO:
        video_path = os.path.join(config.PATH_TO_VIDEO, config.VIDEOS[video_idx])
    else:
        video_path = config.VIDEOS[video_idx]
    
    try:
        import cv2
        cap = cv2.VideoCapture(video_path)
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration_sec = frame_count / fps if fps > 0 else 0
        
        cap.release()
        
        # Task C: ИСПРАВЛЕН БАГ - возвращаем реальный frame_count вместо константы
        return jsonify({
            "video_idx": video_idx,
            "fps": fps,
            "frame_count": frame_count,
            "duration_sec": duration_sec,
            "frames_per_video_hint": frame_count,  # БЫЛО: config.FRAMES_PER_VIDEO (неверно!)
        })
    except Exception as e:
        logger.info(f"[API /api/video_info/{video_idx}] Ошибка: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/geojson_export")
def api_geojson_export():
    """Отдаёт весь GeoJSON файл для скачивания."""
    if not config.PATH_TO_GEOJSON:
        return jsonify({"error": "GeoJSON path not configured"}), 404
    
    # Нормализуем путь для Windows
    geojson_path = os.path.normpath(os.path.abspath(config.PATH_TO_GEOJSON))
    
    if not os.path.exists(geojson_path):
        return jsonify({"error": "GeoJSON file not found"}), 404
    
    try:
        # Используем абсолютный путь с правильной кодировкой для Windows
        return send_file(
            geojson_path,
            mimetype="application/geo+json",
            as_attachment=True,
            download_name="signs.geojson",
        )
    except Exception as e:
        logger.info(f"[MapServer] Ошибка при отправке GeoJSON: {e}")
        return jsonify({"error": f"Failed to send file: {str(e)}"}), 500


@app.route("/api/gps_at_time")
def api_gps_at_time():
    """Возвращает GPS координаты по секундам видео. ?seconds=120"""
    try:
        seconds = int(request.args.get("seconds", 0))
        if not config.PATH_TO_GPX or not os.path.exists(config.PATH_TO_GPX):
            return jsonify({"error": "no gpx file"}), 404
        
        # Простая аппроксимация: считаем что GPS точки идут равномерно
        with open(config.PATH_TO_GPX, encoding="utf-8") as f:
            gpx = gpxpy.parse(f)
        
        all_points = []
        for track in gpx.tracks:
            for segment in track.segments:
                for pt in segment.points:
                    all_points.append({
                        "lat": pt.latitude,
                        "lon": pt.longitude,
                        "time": pt.time
                    })
        
        if not all_points:
            return jsonify({"error": "no gps points"}), 404
        
        # Если есть временные метки, используем их
        if all_points[0]["time"]:
            # Ищем ближайшую точку по времени
            target_time = all_points[0]["time"] + timedelta(seconds=seconds)
            closest = min(all_points, 
                         key=lambda p: abs((p["time"] - target_time).total_seconds()) 
                         if p["time"] else float('inf'))
            return jsonify({
                "lat": closest["lat"],
                "lon": closest["lon"],
                "seconds": seconds
            })
        else:
            # Без временных меток — аппроксимируем по индексу
            # Предполагаем видео длительностью в 1 час и равномерное распределение точек
            total_duration = 3600  # секунды
            idx = int((seconds / total_duration) * len(all_points))
            idx = min(idx, len(all_points) - 1)
            pt = all_points[idx]
            return jsonify({
                "lat": pt["lat"],
                "lon": pt["lon"],
                "seconds": seconds
            })
    except Exception as e:
        logger.error(f"ERROR in /api/gps_at_time: {e}")
        return jsonify({"error": str(e)}), 500


# ── SocketIO события ───────────────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    """При подключении клиента отправляем текущее состояние."""
    socketio.emit("processing_state", {"active": _processing_active})
    socketio.emit("data_ready", {"ready": _data_ready})


def emit_position(seconds: int):
    """Вызывается из VideoThread чтобы двигать маркер позиции на карте."""
    try:
        socketio.emit("position", seconds)
    except Exception as e:
        logger.error(f"ERROR in emit_position: {e}")


def emit_theme_changed(theme: str):
    """Уведомляет веб-страницу о смене темы (light / dark)."""
    try:
        socketio.emit("theme_changed", {"theme": theme})
        logger.info(f"[MapServer] emit_theme_changed: {theme}")
    except Exception as e:
        logger.error(f"ERROR in emit_theme_changed: {e}")


def emit_new_sign(sign_dict: dict):
    """Вызывается из FinalHandler когда появился новый знак."""
    try:
        socketio.emit("new_sign", sign_dict)
    except Exception as e:
        logger.error(f"ERROR in emit_new_sign: {e}")


def emit_processing_finished():
    """Уведомляет клиентов о завершении обработки."""
    try:
        global _processing_active, _data_ready
        _processing_active = False
        _data_ready = True
        logger.info("[MapServer] emit_processing_finished вызван")
        logger.info(f"[MapServer] PATH_TO_GEOJSON = {config.PATH_TO_GEOJSON}")
        logger.info(f"[MapServer] Файл существует: {os.path.exists(config.PATH_TO_GEOJSON) if config.PATH_TO_GEOJSON else False}")
        socketio.emit("processing_finished", {"finished": True})
        socketio.emit("data_ready", {"ready": True})
        logger.info("[MapServer] События отправлены клиентам")
    except Exception as e:
        logger.error(f"ERROR in emit_processing_finished: {e}")
        import traceback
        traceback.print_exc()


# ── Запуск ─────────────────────────────────────────────────────────────────

def run(port: int = 3000):
    """
    Запускает Flask-сервер с SocketIO.
    
    Важные настройки для стабильности на Windows:
    - use_reloader=False: отключает автоперезагрузку (конфликты с Qt)
    - log_output=False: отключает вывод логов (может вызывать конфликты I/O)
    - allow_unsafe_werkzeug=True: для dev-режима
    """
    socketio.run(
        app, 
        host='127.0.0.1',
        port=port, 
        debug=False,
        use_reloader=False,
        log_output=False, 
        allow_unsafe_werkzeug=True
    )