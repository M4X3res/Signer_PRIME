"""
configs/config.py
Глобальное состояние обработки.
Изменяется только из ProcessingController и VideoReaderThread.
UI читает через сигналы — не напрямую.
"""

# ── Пути ──────────────────────────────────────────────────────────
PATH_TO_VIDEO:        str = ""
PATH_TO_EXTRA_LAYERS: str = ""
PATH_TO_GEOJSON:      str = ""
PATH_TO_GPX:          str = ""

# ── Список видеофайлов ────────────────────────────────────────────
VIDEOS: list[str] = []

# ── Состояние обработки ───────────────────────────────────────────
FRAME_STEP:             int = 5     # каждый N-й кадр обрабатывается
COUNT_PROCESSED_FRAMES: int = 0

INDEX_OF_FRAME:    int = 0   # текущий кадр внутри видеофайла
INDEX_OF_VIDEO:    int = 0   # индекс текущего видеофайла
INDEX_OF_All_FRAME:int = 0   # глобальный номер кадра
INDEX_OF_GPS:      int = 0   # индекс GPS точки
INDEX_OF_SING:     int = 0   # индекс знака (устаревшее, для совместимости)

COUNT_FRAMES:      int = 0   # общее число кадров

# ── GPS / видео время ─────────────────────────────────────────────
SECONDS_ALL_VIDEO: float = 0.0  # текущая секунда по всем видео

# ── Прочее ───────────────────────────────────────────────────────
CLASSIFIER: dict = {}
FEATURES:   list = []