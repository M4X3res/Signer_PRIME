"""
MapServer — Flask-сервер карты.
Запускается в отдельном QThread, общается с UI через pyqtSignal.
Не импортирует ничего из PyQt напрямую — только через сигналы.
"""
import os
import uuid
import json

import flask
import geojson
import gpxpy
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_socketio import SocketIO

from configs import config
from configs.sign_config import (
    type_signs_with_text,
    codes_signs,
    signs_with_various_text,
    type_signs_city,
)
from utils import resource_path

# ── Пути к ресурсам ────────────────────────────────────────────────────────
TEMPLATES_DIR  = resource_path("templates")
STATIC_DIR     = resource_path("static")
SIGNS_DIR      = resource_path("sings")
SIGNS_TEXT_DIR = resource_path("sings_text")

# ── Приложение ─────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder=TEMPLATES_DIR, static_folder=STATIC_DIR)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="processing")

# Колбэки — устанавливаются снаружи через set_callbacks()
_on_jump_to_second: callable = None   # (seconds: int) → None
_on_sign_updated:   callable = None   # (sign_id: str)  → None


def set_callbacks(on_jump=None, on_sign_updated=None):
    global _on_jump_to_second, _on_sign_updated
    _on_jump_to_second  = on_jump
    _on_sign_updated    = on_sign_updated


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
    if not config.PATH_TO_GPX or not os.path.exists(config.PATH_TO_GPX):
        return jsonify([])
    points = []
    with open(config.PATH_TO_GPX, encoding="utf-8") as f:
        gpx = gpxpy.parse(f)
    for track in gpx.tracks:
        for segment in track.segments:
            for pt in segment.points:
                points.append([pt.latitude, pt.longitude])
    return jsonify(points)


@app.route("/api/signs")
def api_signs():
    """Все знаки из GeoJSON в упрощённом формате для Leaflet."""
    if not config.PATH_TO_GEOJSON or not os.path.exists(config.PATH_TO_GEOJSON):
        return jsonify([])
    data    = _load_geojson()
    result  = []
    for feat in data.get("features", []):
        props = feat.get("properties", {})
        coords = feat.get("geometry", {}).get("coordinates", [])
        if not coords:
            continue
        # Берём первую точку линии как позицию маркера
        lon, lat = coords[0][0], coords[0][1]
        result.append({
            "id":          props.get("id", str(uuid.uuid4())),
            "type":        props.get("type", ""),
            "code":        props.get("code", ""),
            "azimuth":     props.get("azimuth", 0),
            "description": props.get("SEM250", ""),
            "side":        props.get("side", ""),
            "time":        props.get("time", ""),
            "name_video":  props.get("name_video", ""),
            "abs_frame":   props.get("absolute_frame_numbers", ""),
            "lat":         lat,
            "lon":         lon,
            "line":        coords,          # полная линия для отображения
        })
    return jsonify(result)


@app.route("/api/sign/<sign_id>")
def api_sign_detail(sign_id: str):
    """Детали одного знака по ID."""
    if not os.path.exists(config.PATH_TO_GEOJSON):
        return jsonify({"error": "no geojson"}), 404
    data = _load_geojson()
    for feat in data.get("features", []):
        if feat["properties"].get("id") == sign_id:
            return jsonify(feat)
    return jsonify({"error": "not found"}), 404


@app.route("/api/sign/<sign_id>", methods=["PATCH"])
def api_sign_update(sign_id: str):
    """
    Обновление знака.
    Body: { "type": "3.24", "description": "5" }
    """
    body = request.get_json(silent=True) or {}
    if not os.path.exists(config.PATH_TO_GEOJSON):
        return jsonify({"error": "no geojson"}), 404

    data    = _load_geojson()
    updated = False
    for feat in data.get("features", []):
        if feat["properties"].get("id") == sign_id:
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
    seconds = int(request.args.get("seconds", 0))
    config.SECONDS_ALL_VIDEO = seconds
    if _on_jump_to_second:
        _on_jump_to_second(seconds)
    socketio.emit("jump", seconds)
    return jsonify({"seconds": seconds})


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
    if not os.path.exists(path):
        # fallback — пустой PNG
        return flask.send_file(
            os.path.join(SIGNS_DIR, "V1.1.png"), mimetype="image/png"
        )
    return send_file(path, mimetype="image/png")


@app.route("/api/geojson_export")
def api_geojson_export():
    """Отдаёт весь GeoJSON файл для скачивания."""
    if not os.path.exists(config.PATH_TO_GEOJSON):
        return jsonify({"error": "no file"}), 404
    return send_file(
        config.PATH_TO_GEOJSON,
        mimetype="application/geo+json",
        as_attachment=True,
        download_name="signs.geojson",
    )


# ── SocketIO события ───────────────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    pass


def emit_position(seconds: int):
    """Вызывается из VideoThread чтобы двигать маркер позиции на карте."""
    socketio.emit("position", seconds)


def emit_new_sign(sign_dict: dict):
    """Вызывается из FinalHandler когда появился новый знак."""
    socketio.emit("new_sign", sign_dict)


# ── Запуск ─────────────────────────────────────────────────────────────────

def run(port: int = 3000):
    socketio.run(app, port=port, log_output=False, allow_unsafe_werkzeug=True)