"""
MapServer — Flask-сервер карты.
Запускается в отдельном QThread, общается с UI через pyqtSignal.
Не импортирует ничего из PyQt напрямую — только через сигналы.
"""
import os
import uuid
import json
import logging
from app.json_store import atomic_write_json, serialized_edit
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
from app.utils import resource_path

logger = logging.getLogger(__name__)


def _map_azimuth(props: dict):
    from configs.settings import get_app_settings
    from core.sign_orientation import display_azimuth
    return display_azimuth(props, get_app_settings().panorama_perpendicular_azimuth)


# ── Константы кэша видео-клипов ────────────────────────────────────────────
CLIP_CACHE_DIRNAME = ".signer_clip_cache"


def _get_clip_cache_dir(video_path: str) -> str:
    """
    Возвращает путь к директории кэша клипов для указанного видео.
    Создаёт директорию если её нет.
    """
    video_dir = os.path.dirname(video_path)
    cache_dir = os.path.join(video_dir, CLIP_CACHE_DIRNAME)
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def clear_clip_cache(video_dir: str) -> tuple[int, int]:
    """
    Удаляет папку кэша клипов для указанной директории с видео.
    
    Args:
        video_dir: путь к директории с видео
    
    Returns:
        (количество удалённых файлов, освобождено байт)
    """
    cache_dir = os.path.join(video_dir, CLIP_CACHE_DIRNAME)
    
    # Безопасная проверка: удаляем только если папка называется именно CLIP_CACHE_DIRNAME
    if not os.path.exists(cache_dir):
        return 0, 0
    
    if not cache_dir.endswith(CLIP_CACHE_DIRNAME):
        logger.warning(f"[clear_clip_cache] Отказано: путь не заканчивается на {CLIP_CACHE_DIRNAME}: {cache_dir}")
        return 0, 0
    
    files_removed = 0
    bytes_freed = 0
    
    try:
        import shutil
        
        # Подсчитываем размер перед удалением
        for root, dirs, files in os.walk(cache_dir):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    bytes_freed += os.path.getsize(file_path)
                    files_removed += 1
                except OSError:
                    pass
        
        # Удаляем директорию
        shutil.rmtree(cache_dir, ignore_errors=True)
        logger.info(f"[clear_clip_cache] Удалено {files_removed} файлов, освобождено {bytes_freed} байт из {cache_dir}")
        
    except Exception as e:
        logger.error(f"[clear_clip_cache] Ошибка при удалении кэша: {e}")
        return 0, 0
    
    return files_removed, bytes_freed


# ── Пути к ресурсам ────────────────────────────────────────────────────────
TEMPLATES_DIR  = resource_path("templates")
STATIC_DIR     = resource_path("static")
SIGNS_DIR      = resource_path("sings")
SIGNS_TEXT_DIR = resource_path("sings_text")

# ── Приложение ─────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder=TEMPLATES_DIR, static_folder=STATIC_DIR)
from server.local_background_routes import blueprint as local_background_blueprint
app.register_blueprint(local_background_blueprint)


@app.before_request
def require_license_access():
    from licensing.access import get_manager
    from licensing.license_manager import LicenseStatus
    manager = get_manager()
    if manager is None:
        return jsonify(error='Онлайн-проверка лицензии недоступна'), 403
    if not manager.has_online_access():
        return jsonify(error='Работа заблокирована: требуется проверка лицензии'), 403
@app.after_request
def verify_license_after_action(response):
    from licensing.access import get_manager
    manager = get_manager()
    if (manager is not None and response.status_code < 400 and
            (request.method in ('POST', 'PATCH', 'DELETE', 'PUT') or
             request.path == '/api/geojson_export')):
        # Preserve the actual result: a completed mutation must not look failed.
        # The verification emits access_changed and blocks subsequent work on failure.
        manager._verify_access_internal()
    return response


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


def emit_processing_finished(sign_count: int = 0):
    """Уведомляет клиентов о завершении обработки."""
    global _processing_active, _data_ready
    _processing_active = False
    _data_ready = True
    logger.info(f"[MapServer] Отправляем processing_finished: {sign_count} знаков")
    socketio.emit("processing_finished", {"count": sign_count, "ready": True, "finished": True})
    socketio.emit("data_ready", {"ready": True})


def notify_data_ready():
    """Уведомляет клиентов о готовности данных."""
    global _data_ready
    _data_ready = True
    socketio.emit("data_ready", {"ready": True})


# ── Утилиты ────────────────────────────────────────────────────────────────

def _load_geojson() -> dict:
    with open(config.PATH_TO_GEOJSON, encoding="utf-8-sig") as f:
        return geojson.load(f)


def _save_geojson(data: dict):
    atomic_write_json(config.PATH_TO_GEOJSON, data)


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


def _build_upstream_tile_url(template: str, z: int, x: int, y: int) -> str:
    """
    Построение upstream URL для векторного тайла с сохранением query string.
    
    ВАЖНО: Leaflet.VectorGrid отправляет координаты в стандартном порядке OSM/Mapbox: z/x/y
    Но api.maps.by (Esri/ArcGIS) использует порядок: z/y/x
    
    Эта функция получает координаты от Leaflet (z, x, y) и подставляет их в template,
    который содержит плейсхолдеры {z}/{y}/{x}.
    
    Пример:
      template: "https://api.maps.by/.../tile/{z}/{y}/{x}.pbf?token=ABC"
      Leaflet отправляет: z=9, x=291, y=163
      Результат: "https://api.maps.by/.../tile/9/163/291.pbf?token=ABC"
                                                    z  y    x
    
    Критично: не потерять параметры (токен!) при подстановке.
    """
    original_template = template
    
    # Подставляем координаты
    # ВАЖНО: Не меняем порядок подстановки - просто заменяем плейсхолдеры
    # Template определяет порядок: если там {z}/{y}/{x}, то так и будет
    url = (
        template
        .replace("{z}", str(z))
        .replace("{x}", str(x))
        .replace("{y}", str(y))
        .replace("{s}", "a")  # Поддомены (если есть)
    )
    
    # DEFENSIVE CHECK: Подстановка должна была изменить URL
    # Если итоговый URL идентичен исходному шаблону → плейсхолдеры отсутствуют
    if url == original_template:
        # Это означает что в template НЕТ {z}/{x}/{y} вообще
        # Такое возможно если пользователь вставил URL конкретного тайла вместо шаблона
        raise ValueError(
            f"Vector tile template does not contain placeholders {{z}}/{{x}}/{{y}} or {{z}}/{{y}}/{{x}}. "
            f"Template appears to be a URL of a single specific tile, not a template. "
            f"All tile requests will return the same tile, resulting in a 'mosaic' pattern on the map."
        )
    
    return url


def _mask_token_for_log(url: str) -> str:
    """
    Маскирует значения параметра token= в URL для безопасного логирования.
    
    Пример: "...?token=ABC123XYZ&..." → "...?token=****XYZ&..."
    Показывает только последние 3 символа токена.
    """
    import re
    
    def mask_match(match):
        token_value = match.group(1)
        if len(token_value) <= 4:
            return f"token=****"
        return f"token=****{token_value[-3:]}"
    
    # Маскируем все вхождения token=...
    masked = re.sub(r'token=([^&\s]+)', mask_match, url)
    return masked


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
        
        # Для векторных тайлов можно использовать прокси для обхода CORS
        # По умолчанию прокси включён (map_tile_use_proxy = True)
        tile_url = settings.map_tile_url
        use_proxy = False
        
        # Если векторный режим И прокси включён в настройках
        if settings.map_tile_type == "vector" and settings.map_tile_use_proxy:
            # Отдаём относительный путь прокси вместо прямого URL
            # Это устраняет CORS (запрос идёт на тот же origin) И скрывает токен от клиента
            tile_url = "/api/vector_tile_proxy/{z}/{x}/{y}"
            use_proxy = True
            logger.info("[api_map_config] Vector tiles via proxy (CORS bypass)")
        elif settings.map_tile_type == "vector":
            logger.info("[api_map_config] Vector tiles direct (proxy disabled in settings)")
        
        # BLOCK SETTINGS-1: Ограничение max_zoom до 17 (для пользователей со старыми сохранёнными значениями)
        return jsonify({
            "local_background_enabled": settings.map_local_background_enabled,
            "tile_url": tile_url,
            "attribution": settings.map_tile_attribution,
            "max_zoom": min(settings.map_tile_max_zoom, 17),
            "tile_type": settings.map_tile_type,  # "raster" | "vector"
            "use_proxy": use_proxy,  # Информация для клиента
        })
    except Exception as e:
        logger.error(f"ERROR in /api/map_config: {e}")
        # Безопасный fallback на OSM, чтобы карта не осталась совсем без подложки
        # BLOCK SETTINGS-1: fallback также использует max_zoom=17
        return jsonify({
            "tile_url": "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            "attribution": "© OpenStreetMap",
            "max_zoom": 17,
            "tile_type": "raster",  # fallback на растровые тайлы
            "use_proxy": False,
        })


@app.route("/api/vector_tile_proxy/<int:z>/<int:x>/<int:y>")
def api_vector_tile_proxy(z, x, y):
    """
    Прокси для векторных тайлов — обходит CORS-блокировку.
    
    ДИАГНОСТИКА (Задача 0): До реализации прокси запрос из QWebEngineView
    к api.maps.by падал с ошибкой в консоли браузера:
    "blocked by CORS policy: No 'Access-Control-Allow-Origin' header is present"
    
    Большинство ArcGIS/Esri VectorTileServer инстансов не отдают
    Access-Control-Allow-Origin, а QWebEngineView (как и любой браузер)
    блокирует fetch/XHR с другого origin без этого заголовка.
    
    Прокси решает проблему: Flask-сервер делает запрос к upstream (который
    не подчиняется CORS для серверных HTTP-клиентов), а клиенту отдаёт
    с корректным Access-Control-Allow-Origin: *.
    
    Формирует upstream URL из настроек (map_tile_url с подставленными
    {z}/{x}/{y}), сохраняя query string (токен!) как есть, и пробрасывает
    ответ как application/x-protobuf.
    """
    try:
        from configs.settings import get_app_settings
        import requests as req
        
        settings = get_app_settings()
        
        # Проверяем, что векторные тайлы настроены
        if settings.map_tile_type != "vector":
            logger.warning(f"[vector_tile_proxy] Called but map_tile_type={settings.map_tile_type}")
            return jsonify({"error": "vector tiles not configured"}), 400
        
        # Формируем upstream URL с сохранением query string
        upstream_url = _build_upstream_tile_url(settings.map_tile_url, z, x, y)
        
        # Логируем с маскированным токеном
        masked = _mask_token_for_log(upstream_url)
        logger.info(f"[vector_tile_proxy] GET {masked}")
        
        # Делаем запрос к upstream-серверу
        resp = req.get(upstream_url, timeout=10)
        resp.raise_for_status()
        
        # Возвращаем ответ с корректными CORS-заголовками
        return Response(
            resp.content,
            mimetype="application/x-protobuf",
            headers={
                "Access-Control-Allow-Origin": "*",  # CORS fix
                "Cache-Control": "public, max-age=86400",  # Кэшируем на 24 часа
            }
        )
    
    except ValueError as e:
        # ValueError = отсутствие плейсхолдеров в template (критическая ошибка конфигурации)
        error_msg = str(e)
        logger.error(f"[vector_tile_proxy] CONFIGURATION ERROR: {error_msg}")
        return jsonify({
            "error": "Invalid tile URL template",
            "details": "URL does not contain {z}/{x}/{y} placeholders. Please check map settings.",
            "diagnostic": error_msg
        }), 400
        
    except req.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else 502
        masked = _mask_token_for_log(upstream_url) if 'upstream_url' in locals() else 'unknown'
        logger.warning(f"[vector_tile_proxy] Upstream HTTP {status} for {masked}")
        return jsonify({"error": f"Upstream HTTP {status}"}), status
        
    except req.exceptions.Timeout:
        masked = _mask_token_for_log(upstream_url) if 'upstream_url' in locals() else 'unknown'
        logger.warning(f"[vector_tile_proxy] Timeout for {masked}")
        return jsonify({"error": "Upstream timeout"}), 504
        
    except Exception as e:
        masked = _mask_token_for_log(upstream_url) if 'upstream_url' in locals() else 'unknown'
        logger.error(f"[vector_tile_proxy] Error: {e} for {masked}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 502


@app.route("/api/vector_tile_style")
def api_vector_tile_style():
    from configs.settings import get_app_settings
    from server.vector_styles import load_style
    settings = get_app_settings()
    if settings.map_tile_type != "vector":
        return jsonify(error="Векторная подложка не выбрана"), 400
    try:
        return jsonify(load_style(
            settings.map_tile_url, settings.map_vector_style_url,
            request.host_url.rstrip('/') + '/api/vector_resource/',
            settings.map_tile_use_proxy,
            native_max_zoom=settings.map_tile_max_zoom,
        ))
    except ValueError as exc:
        return jsonify(error=str(exc)), 502


@app.route("/api/vector_resource/<ident>/<filename>")
def api_vector_resource(ident, filename):
    import requests
    from server.vector_styles import resource_url
    try:
        url = resource_url(ident, filename, request.args)
    except ValueError:
        return jsonify(error="Unknown style resource"), 404
    try:
        upstream = requests.get(url, timeout=20)
        upstream.raise_for_status()
        return Response(upstream.content, content_type=upstream.headers.get('Content-Type', 'application/octet-stream'),
                        headers={'Cache-Control': 'private, max-age=3600'})
    except requests.RequestException:
        return jsonify(error="Не удалось загрузить ресурс векторной карты"), 502


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
                "azimuth":     _map_azimuth(props),
                "description": props.get("SEM250", ""),
                "side":        side_bool,  # Теперь bool
                "left":        str(props.get("left", "False")).strip().lower() in ("true", "1", "yes"),
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
                # Keep the detail panel consistent with marker rendering.
                feat = dict(feat)
                feat["properties"] = dict(feat.get("properties", {}))
                feat["properties"]["azimuth"] = _map_azimuth(feat["properties"])
                return jsonify(feat)
        
        logger.warning(f"[API /api/sign/{sign_id}] Знак не найден в GeoJSON")
        return jsonify({"error": f"Sign with id '{sign_id}' not found"}), 404
        
    except Exception as e:
        logger.error(f"[API /api/sign/{sign_id}] Ошибка при загрузке: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Server error: {str(e)}"}), 500


@app.route("/api/sign", methods=["POST"])
@serialized_edit
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
        
        # Валидация координат
        if not (-90 <= lat <= 90):
            return jsonify({"error": f"Invalid latitude: {lat} (must be in [-90, 90])"}), 400
        if not (-180 <= lon <= 180):
            return jsonify({"error": f"Invalid longitude: {lon} (must be in [-180, 180])"}), 400
        
        azimuth = float(body.get("azimuth", 0.0))
        description = body.get("description", "")
        is_left = bool(body.get("is_left", False))  # Сторона: False = справа, True = слева
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
            "left": str(is_left),      # Консистентно с остальным пайплайном: "True"/"False"
            "manually_added": True,    # Отдельный флаг происхождения знака
            "conf_cnn": 1.0,           # Максимальная уверенность для ручных знаков
            "conf_total": 1.0,
            "length": 1,               # Одно наблюдение
        }
    }
    
    # Добавляем hint-поля от ближайшего знака (для привязки видео)
    if "abs_frame_hint" in body:
        feature["properties"]["absolute_frame_numbers"] = body["abs_frame_hint"]
    if "time_hint" in body:
        feature["properties"]["time"] = body["time_hint"]
    if "name_video_hint" in body:
        feature["properties"]["name_video"] = body["name_video_hint"]
    
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
@serialized_edit
def api_sign_update(sign_id: str):
    """
    Обновление знака.
    Body: { 
        "type": "3.24", 
        "description": "5",
        "lat": 53.905,        # Опционально (BLOCK S.2)
        "lon": 27.560,        # Опционально (BLOCK S.2)
        "azimuth": 90.0       # Опционально (BLOCK S.2, BLOCK MAP-AZ-3)
    }
    """
    body = request.get_json(silent=True) or {}
    if not os.path.exists(config.PATH_TO_GEOJSON):
        return jsonify({"error": "no geojson"}), 404

    import math
    try:
        for field in ('lat', 'lon', 'azimuth'):
            if field in body and not math.isfinite(float(body[field])):
                raise ValueError()
        if ('lat' in body) != ('lon' in body):
            raise ValueError()
        if 'lat' in body and not (-90 <= float(body['lat']) <= 90 and -180 <= float(body['lon']) <= 180):
            raise ValueError()
    except (TypeError, ValueError, OverflowError):
        return jsonify(error='Некорректные координаты или азимут'), 400

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
            
            # BLOCK S.2 + BLOCK MAP-AZ-3: Обновление координат и/или азимута
            if "lat" in body and "lon" in body:
                new_lat = float(body["lat"])
                new_lon = float(body["lon"])
                
                if feat["geometry"]["type"] == "Point":
                    feat["geometry"]["coordinates"][:2] = [new_lon, new_lat]
                    if "azimuth" in body:
                        feat["properties"]["azimuth"] = float(body["azimuth"]) % 360

                # Обновляем геометрию (LineString с двумя точками)
                if feat["geometry"]["type"] == "LineString":
                    coords = feat["geometry"]["coordinates"]
                    if len(coords) >= 2:
                        # Обновляем первую точку
                        coords[0][0] = new_lon
                        coords[0][1] = new_lat
                        
                        # Если есть азимут, пересчитываем вторую точку
                        if "azimuth" in body or "azimuth" in feat["properties"]:
                            azimuth = float(body["azimuth"]) if "azimuth" in body else _map_azimuth(feat["properties"])
                            # Используем CoordinateCalculation для точного расчёта
                            from core.coordinate_calculation import CoordinateCalculation
                            calc = CoordinateCalculation()
                            # Длина линии ~5м (стандартная для визуализации направления)
                            new_lat2, new_lon2 = calc.point_at_distance(new_lat, new_lon, azimuth, 5.0)
                            coords[1][0] = new_lon2
                            coords[1][1] = new_lat2
                            feat["properties"]["azimuth"] = azimuth
            
            # BLOCK MAP-AZ-3: Обновление только азимута (без изменения координат)
            elif "azimuth" in body:
                new_azimuth = float(body["azimuth"]) % 360
                feat["properties"]["azimuth"] = new_azimuth
                
                # Пересчитываем вторую точку линии на основе нового азимута
                if feat["geometry"]["type"] == "LineString":
                    coords = feat["geometry"]["coordinates"]
                    if len(coords) >= 2:
                        base_lon, base_lat = coords[0][0], coords[0][1]
                        from core.coordinate_calculation import CoordinateCalculation
                        calc = CoordinateCalculation()
                        new_lat2, new_lon2 = calc.point_at_distance(base_lat, base_lon, new_azimuth, 5.0)
                        coords[1][0] = new_lon2
                        coords[1][1] = new_lat2
            
            if "azimuth" in body:
                feat["properties"]["azimuth_mode"] = "manual"
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
@serialized_edit
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


@app.route("/api/video_position")
def api_video_position():
    from server.map_media import video_position
    try:
        paths = [os.path.join(config.PATH_TO_VIDEO, name) for name in config.VIDEOS]
        return jsonify(video_position(paths, float(request.args.get("frame", "nan"))))
    except (ValueError, OSError) as error:
        return jsonify(error=str(error)), 400


@app.route("/api/track_window")
def api_track_window():
    from server.map_media import track_window
    try:
        if not config.PATH_TO_GPX:
            return jsonify(before=[], after=[], position=None, available=False)
        return jsonify(track_window(config.PATH_TO_GPX, float(request.args.get("seconds", "nan"))))
    except (ValueError, OSError) as error:
        return jsonify(error=str(error)), 400


@app.route("/api/video_clip/<int:video_idx>")
def api_video_clip(video_idx: int):
    from server.map_media import prepare_video
    if not config.VIDEOS or video_idx >= len(config.VIDEOS):
        return jsonify(error="Видео не найдено"), 404
    try:
        start = float(request.args.get("start", 0))
        duration = float(request.args.get("duration", 15))
        path = os.path.abspath(os.path.join(config.PATH_TO_VIDEO, config.VIDEOS[video_idx]))
        target, job = prepare_video(path, start, duration, _get_clip_cache_dir(path))
        if request.args.get("prepare") == "1":
            if job is not None:
                if not job.done():
                    return jsonify(status="preparing"), 202
                job.result()
            return jsonify(status="ready")
        if job is not None:
            job.result()
        return send_file(target, mimetype="video/webm", conditional=True)
    except (ValueError, OSError) as error:
        return jsonify(error=str(error)), 400
    except Exception as error:
        logger.exception("Video preparation failed")
        return jsonify(error=str(error)), 500


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
                    chunk = f.read(min(256 * 1024, remaining))
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


@app.route("/api/clear_clip_cache", methods=["POST"])
def api_clear_clip_cache():
    """
    Очистка кэша видео-клипов для текущей директории с видео.
    
    Returns:
        JSON: {"ok": true, "files_removed": N, "bytes_freed": N}
        или {"error": "..."}
    """
    try:
        # Получаем путь к директории с видео
        if not config.PATH_TO_VIDEO:
            return jsonify({"error": "PATH_TO_VIDEO not configured"}), 400
        
        video_dir = os.path.normpath(os.path.abspath(config.PATH_TO_VIDEO))
        
        if not os.path.exists(video_dir):
            return jsonify({"error": f"Video directory not found: {video_dir}"}), 404
        
        # Очищаем кэш
        files_removed, bytes_freed = clear_clip_cache(video_dir)
        
        # Форматируем размер для удобства
        mb_freed = bytes_freed / (1024 * 1024)
        
        logger.info(f"[API /api/clear_clip_cache] Очищено: {files_removed} файлов, {mb_freed:.2f} МБ")
        
        return jsonify({
            "ok": True,
            "files_removed": files_removed,
            "bytes_freed": bytes_freed,
            "mb_freed": round(mb_freed, 2)
        })
        
    except Exception as e:
        logger.error(f"[API /api/clear_clip_cache] Ошибка: {e}", exc_info=True)
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
