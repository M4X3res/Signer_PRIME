"""
ui/widgets/error_editor_page.py
Редактор ошибок — просмотр и корректировка знаков после обработки.

Возможности:
  - Список знаков отсортированный от наименее к наиболее уверенному
  - Предпросмотр кадра с bounding box
  - Смена типа знака через поиск
  - Удаление знака
  - Сохранение изменений в GeoJSON
"""
from __future__ import annotations

import json
import os
import re
from typing import Optional

import cv2
import geojson
from PyQt6.QtCore import (
    Qt, pyqtSignal, QTimer, QSortFilterProxyModel,
    QAbstractListModel, QModelIndex
)
from PyQt6.QtGui import QPixmap, QImage, QColor, QPainter, QPen, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListView, QSplitter, QFrame,
    QLineEdit, QComboBox, QSizePolicy, QScrollArea,
    QAbstractItemView, QStyledItemDelegate, QStyleOptionViewItem,
    QApplication, QCheckBox
)

from configs import config
from configs.sign_data import CODES_SIGNS, TYPE_SIGNS_WITH_TEXT, NAMES_SIGNS_BY_TYPE
from ui.themes.theme_manager import theme_manager
from ui.widgets.utils import connect_combobox_theme_updates  # ЗАДАЧА 1


# ── Модель данных ─────────────────────────────────────────────────

class SignRecord:
    """Один знак из GeoJSON с рассчитанной уверенностью."""

    def __init__(self, feature: dict):
        self.feature    = feature
        self.props      = feature.get("properties", {})
        self.id:   str  = self.props.get("id", "")
        self.type: str  = self.props.get("type", "")
        self.code: str  = str(self.props.get("code", ""))
        self.azimuth    = float(self.props.get("azimuth", 0) or 0)
        self.time: str  = self.props.get("time", "")
        self.video: str = self.props.get("name_video", "")
        self.text: str  = self.props.get("SEM250", "")
        self.is_left    = str(self.props.get("left", "")).lower() == "true"

        # Координаты кадра (нужны для расчёта уверенности)
        self._abs_frames: list[int] = self._parse_int_list(
            self.props.get("absolute_frame_numbers", "")
        )
        self._frame_numbers: list[int] = self._parse_int_list(
            self.props.get("frame_numbers", "")
        )

        # Пиксельные координаты bbox (берём медианный кадр)
        self.bbox: Optional[tuple] = self._parse_median_bbox()

        # Уверенность классификации (CNN)
        self.confidence: float = self._calc_confidence()
        
        # Уверенность размещения (GPS + OSM snap)
        self.gps_confidence: float = self._calc_gps_confidence()
        
        # Общая уверенность
        # Пытаемся взять готовое значение conf_total из GeoJSON (предпочтительно)
        conf_total_str = self.props.get("conf_total", "")
        if conf_total_str:
            try:
                self.total_confidence = float(conf_total_str)
            except (ValueError, TypeError):
                # Если не удалось распарсить — рассчитываем
                self.total_confidence = 0.5 * self.confidence + 0.5 * self.gps_confidence
        else:
            # Если нет готового значения — рассчитываем (50/50 как в core/sign.py)
            self.total_confidence = 0.5 * self.confidence + 0.5 * self.gps_confidence

        # Изменения пользователя
        self.new_type: str  = self.type
        self.new_text: str  = self.text
        self.modified:  bool = False
        self.deleted:   bool = False

    def _calc_confidence(self) -> float:
        """
        Уверенность классификации нейросетью: cnn_count / observation_count.
        
        Сначала пытаемся взять готовое значение conf_cnn из properties.
        Если его нет — рассчитываем вручную.
        """
        # Пытаемся взять готовое значение
        conf_cnn_str = self.props.get("conf_cnn", "")
        if conf_cnn_str:
            try:
                return float(conf_cnn_str)
            except (ValueError, TypeError):
                pass
        
        # Если нет готового значения — рассчитываем
        cnn_count_str = self.props.get("cnn_count", "")
        obs_count_str = self.props.get("observation_count", "")
        
        try:
            cnn_count = int(cnn_count_str) if cnn_count_str else 0
            obs_count = int(obs_count_str) if obs_count_str else 0
            
            if obs_count > 0:
                return min(1.0, cnn_count / obs_count)
        except (ValueError, TypeError):
            pass
        
        # Fallback: используем length / total кадров
        raw = self.props.get("frame_numbers", "")
        total = len(self._parse_int_list(raw))
        if total == 0:
            return 0.0

        length = int(self.props.get("length", total) or total)
        if length == 0:
            return 0.0

        return min(1.0, length / max(total, 1))
    
    def _calc_gps_confidence(self) -> float:
        """
        Уверенность размещения (placement): качество GPS + OSM snap + азимут.
        
        Сначала пытаемся взять готовое значение conf_placement из properties.
        Если его нет — рассчитываем приближённо на основе доступных данных.
        """
        # Пытаемся взять готовое значение (предпочтительно)
        conf_placement_str = self.props.get("conf_placement", "")
        if conf_placement_str:
            try:
                return float(conf_placement_str)
            except (ValueError, TypeError):
                pass
        
        # Если нет готового значения — рассчитываем приближённо
        # (менее точно, т.к. не учитывает OSM snap и детальную стабильность)
        try:
            # 1. Проверяем наличие азимута (хороший индикатор качества GPS)
            has_azimuth = self.azimuth > 0.0
            azimuth_score = 0.3 if has_azimuth else 0.0
            
            # 2. Проверяем количество наблюдений
            obs_count = len(self._abs_frames)
            obs_score = min(0.3, obs_count / 30.0)  # max 0.3 при 30+ кадрах
            
            # 3. Проверяем стабильность координат через geometry
            geom = self.feature.get("geometry", {})
            coords = geom.get("coordinates", [[]])
            if len(coords) > 0 and len(coords[0]) > 1:
                # Есть линия - считаем разброс координат
                lats = [c[1] for c in coords[0] if len(c) >= 2]
                lons = [c[0] for c in coords[0] if len(c) >= 2]
                
                if lats and lons:
                    lat_range = max(lats) - min(lats)
                    lon_range = max(lons) - min(lons)
                    
                    # Малый разброс = высокая уверенность
                    # Порог: 0.001 градуса ≈ 100м
                    stability = 1.0 - min(1.0, (lat_range + lon_range) / 0.002)
                    stability_score = stability * 0.4
                else:
                    stability_score = 0.2
            else:
                stability_score = 0.2  # средняя оценка при отсутствии данных
            
            return min(1.0, azimuth_score + obs_score + stability_score)
        except Exception as e:
            print(f"[SignRecord] Ошибка в _calc_gps_confidence: {e}")
            return 0.5  # Возвращаем среднее значение при ошибке

    def _parse_int_list(self, raw) -> list[int]:
        """Парсит список целых чисел из строки или массива."""
        if not raw:
            return []
        
        # Если уже массив (новый формат GeoJSON)
        if isinstance(raw, list):
            return [int(x) for x in raw if isinstance(x, (int, float))]
        
        # Если строка (старый формат) — парсим через regex
        nums = re.findall(r"-?\d+", str(raw))
        return [int(n) for n in nums]

    def _parse_float_list(self, raw) -> list[float]:
        """Парсит список float из строки или массива."""
        if not raw:
            return []
        
        # Если уже массив (новый формат GeoJSON)
        if isinstance(raw, list):
            return [float(x) for x in raw if isinstance(x, (int, float))]
        
        # Если строка (старый формат) — парсим через regex
        nums = re.findall(r"-?\d+\.?\d*", str(raw))
        return [float(n) for n in nums]

    def _parse_median_bbox(self) -> Optional[tuple[int,int,int,int]]:
        """Возвращает bbox из медианного кадра наблюдений."""
        try:
            xs = self._parse_int_list(self.props.get("pixel_coordinates_x", ""))
            ys = self._parse_int_list(self.props.get("pixel_coordinates_y", ""))
            ws = self._parse_int_list(self.props.get("w", ""))
            hs = self._parse_int_list(self.props.get("h", ""))
            if not all([xs, ys, ws, hs]):
                return None
            # Проверяем что все списки одной длины
            min_len = min(len(xs), len(ys), len(ws), len(hs))
            if min_len == 0:
                return None
            mid = min_len // 2
            return (xs[mid], ys[mid], ws[mid], hs[mid])
        except Exception as e:
            print(f"[SignRecord] Ошибка в _parse_median_bbox: {e}")
            return None

    @property
    def confidence_pct(self) -> int:
        return int(self.confidence * 100)

    @property
    def sign_name(self) -> str:
        return NAMES_SIGNS_BY_TYPE.get(self.type, "")

    def abs_frame_for_video(self) -> Optional[tuple[int, int]]:
        """
        Task C: Возвращает (video_idx, frame_in_video) для прыжка к кадру,
        используя РЕАЛЬНЫЕ длины видеофайлов через resolve_video_and_frame().
        """
        if not self._abs_frames:
            return None
        
        from core.video_index import resolve_video_and_frame
        avg = sum(self._abs_frames) // len(self._abs_frames)
        
        try:
            video_idx, frame_in_video = resolve_video_and_frame(avg)
            return video_idx, frame_in_video
        except ValueError as e:
            print(f"[SignRecord] ОШИБКА при определении видео для кадра {avg}: {e}")
            return None


class SignListModel(QAbstractListModel):
    """Qt модель для QListView — хранит список SignRecord."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._records: list[SignRecord] = []

    def load(self, records: list[SignRecord]) -> None:
        self.beginResetModel()
        # Сортировка: сначала наименее уверенные (по общей уверенности)
        self._records = sorted(records, key=lambda r: r.total_confidence)
        print(f"[SignListModel] Загружено {len(self._records)} записей")
        if self._records:
            print(f"[SignListModel] Диапазон уверенности: {self._records[0].total_confidence:.3f} - {self._records[-1].total_confidence:.3f}")
            print(f"[SignListModel] Первые 3 знака:")
            for i, r in enumerate(self._records[:3]):
                print(f"  [{i}] {r.type} - confidence: {r.confidence:.3f}, gps: {r.gps_confidence:.3f}, total: {r.total_confidence:.3f}")
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._records)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._records):
            return None
        rec = self._records[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return rec.type
        if role == Qt.ItemDataRole.UserRole:
            return rec
        return None

    def record_at(self, row: int) -> Optional[SignRecord]:
        if 0 <= row < len(self._records):
            return self._records[row]
        return None

    def update_record(self, row: int) -> None:
        idx = self.index(row)
        self.dataChanged.emit(idx, idx)

    def remove_record(self, row: int) -> None:
        self.beginRemoveRows(QModelIndex(), row, row)
        self._records.pop(row)
        self.endRemoveRows()

    def all_records(self) -> list[SignRecord]:
        return list(self._records)


# ── Делегат (рисует строку списка) ────────────────────────────────

class SignItemDelegate(QStyledItemDelegate):
    """Кастомный рендер строки знака с индикатором уверенности."""

    ROW_H = 64

    def sizeHint(self, option, index) -> object:
        from PyQt6.QtCore import QSize
        return QSize(option.rect.width(), self.ROW_H)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        rec: Optional[SignRecord] = index.data(Qt.ItemDataRole.UserRole)
        if not rec:
            return

        t = theme_manager.tokens
        r = option.rect

        # ── Фон ───────────────────────────────────────────────────
        selected = bool(
            option.state & option.state.State_Selected  # type: ignore
        )
        if rec.deleted:
            bg = QColor(t["error"]).darker(180)
        elif rec.modified:
            bg = QColor(t["warning"]).darker(200)
        elif selected:
            bg = QColor(t["accent_subtle"])
        else:
            bg = QColor(t["bg_secondary"])

        painter.fillRect(r, bg)

        # ── Индикатор уверенности (левая полоса) ──────────────────
        bar_w = 4
        conf_h = int(r.height() * rec.confidence)
        conf_color = self._conf_color(rec.confidence, t)
        painter.fillRect(r.x(), r.y(), bar_w, r.height(), QColor(t["border_subtle"]))
        painter.fillRect(
            r.x(), r.y() + r.height() - conf_h,
            bar_w, conf_h, QColor(conf_color)
        )

        # ── Текст ─────────────────────────────────────────────────
        pad = bar_w + 10
        tx  = r.x() + pad
        ty  = r.y()
        tw  = r.width() - pad - 60  # место под % справа

        painter.setPen(QColor(t["text_primary"] if not rec.deleted else t["text_disabled"]))

        # Тип знака (крупно)
        f_type = QFont("Segoe UI", 13, QFont.Weight.Light)
        painter.setFont(f_type)
        display_type = rec.new_type if rec.modified else rec.type
        painter.drawText(tx, ty + 22, display_type)

        # Название (мелко)
        f_name = QFont("Segoe UI", 10)
        painter.setFont(f_name)
        painter.setPen(QColor(t["text_tertiary"]))
        name = NAMES_SIGNS_BY_TYPE.get(display_type, "")
        # Обрезаем если длинное
        if len(name) > 32:
            name = name[:30] + "…"
        painter.drawText(tx, ty + 40, name)

        # Время
        painter.setPen(QColor(t["text_tertiary"]))
        f_small = QFont("Segoe UI", 9)
        painter.setFont(f_small)
        painter.drawText(tx, ty + 56, rec.time)

        # ── % уверенности (справа) ────────────────────────────────
        painter.setPen(QColor(conf_color))
        f_conf = QFont("Segoe UI", 11, QFont.Weight.Light)
        painter.setFont(f_conf)
        painter.drawText(
            r.right() - 54, ty, 50, r.height(),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
            f"{rec.confidence_pct}%",
        )

        # ── Разделитель ───────────────────────────────────────────
        painter.setPen(QColor(t["border_subtle"]))
        painter.drawLine(r.x(), r.bottom(), r.right(), r.bottom())

    @staticmethod
    def _conf_color(conf: float, t: dict) -> str:
        if conf < 0.4:
            return t["error"]
        if conf < 0.7:
            return t["warning"]
        return t["success"]


# ── Основная страница ─────────────────────────────────────────────

class ErrorEditorPage(QWidget):
    jump_to_frame = pyqtSignal(int, int)  # video_idx, frame_in_video

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ContentArea")

        self._model     = SignListModel()
        self._current_row: int = -1
        self._current_rec: Optional[SignRecord] = None
        self._cap: Optional[cv2.VideoCapture] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Topbar ────────────────────────────────────────────────
        root.addWidget(self._build_topbar())

        # ── Main splitter ─────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet(
            f"QSplitter::handle {{ background: {theme_manager.tokens['border_subtle']}; }}"
        )

        splitter.addWidget(self._build_list_panel())
        splitter.addWidget(self._build_detail_panel())
        splitter.setSizes([320, 880])

        root.addWidget(splitter)
        
        # Подписка на смену темы
        theme_manager.theme_changed.connect(self._on_theme_changed)
        self._restyle_list_panel()

    def _on_theme_changed(self, _theme_name: str) -> None:
        """
        Большая часть стилизации переведена на objectName + глобальный QSS
        и обновляется автоматически. Здесь досчитываем только то, что
        принципиально не выражается статическим QSS: цветные бейджи
        счётчиков (зависят и от темы, и от семантики "обычный"/"ошибка"),
        и перекраску карточки уверенности текущего выбранного знака.
        """
        self._restyle_badges()
        self._restyle_list_panel()
        if self._current_rec is not None:
            self._show_record(self._current_rec)

    # ── Topbar ────────────────────────────────────────────────────

    def _build_topbar(self) -> QWidget:
        t = theme_manager.tokens
        bar = QWidget()
        bar.setObjectName("EditorTopbar")
        bar.setMinimumHeight(48)  # Минимальная высота
        bar.setMaximumHeight(56)  # Максимальная высота
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 0, 20, 0)
        lay.setSpacing(12)

        title = QLabel("Редактор ошибок")
        title.setObjectName("PageTitle")
        lay.addWidget(title)
        lay.addStretch()

        # Счётчики
        self._lbl_total    = self._tb_badge("0 знаков")
        self._lbl_low_conf = self._tb_badge("0 < 50%")
        lay.addWidget(self._lbl_total)
        lay.addWidget(self._lbl_low_conf)

        sep = QFrame()
        sep.setObjectName("Separator")
        sep.setFixedWidth(1)
        lay.addWidget(sep)

        # Кнопки
        # ЗАДАЧА 4: Унифицируем размеры парных кнопок
        self._btn_load = QPushButton("↑  Загрузить GeoJSON")
        self._btn_load.setObjectName("BtnSecondary")
        self._btn_load.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        # ЗАДАЧА 4: Используем min-height из QSS (36px), убираем конфликт
        self._btn_load.setFixedWidth(220)  # Увеличено — "Загрузить GeoJSON" обрезался
        self._btn_load.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_load.clicked.connect(self.load_geojson)

        self._btn_save = QPushButton("✓  Сохранить")
        self._btn_save.setObjectName("BtnPrimary")
        self._btn_save.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        # ЗАДАЧА 4: Используем min-height из QSS (36px), убираем конфликт
        self._btn_save.setFixedWidth(220)  # Увеличено — держим пару одинаковой ширины
        self._btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_save.setEnabled(False)
        self._btn_save.clicked.connect(self.save_geojson)

        lay.addWidget(self._btn_load)
        lay.addWidget(self._btn_save)
        
        # Применяем стили к бейджам
        self._restyle_badges()
        
        return bar

    def _tb_badge(self, text: str) -> QLabel:
        lbl = QLabel(text)
        return lbl
    
    def _restyle_badges(self) -> None:
        """
        Перекрашивает бейджи счётчиков при смене темы.
        Бейджи используют семантические цвета (нейтральный / ошибка),
        которые нельзя выразить статическим objectName без потери смысла.
        """
        t = theme_manager.tokens
        self._lbl_total.setStyleSheet(
            f"color: {t['text_tertiary']}; font-size: 11px; font-weight: 600;"
            "background: transparent; padding: 0 4px;"
        )
        self._lbl_low_conf.setStyleSheet(
            f"color: {t['error']}; font-size: 11px; font-weight: 600;"
            "background: transparent; padding: 0 4px;"
        )

    def _restyle_list_panel(self) -> None:
        """
        Перекрашивает левую панель списка и фильтр-комбобокс при смене темы.
        Они используют инлайн-стили с токенами темы и не покрываются
        статическим objectName-QSS.
        """
        t = theme_manager.tokens
        self._list_panel.setStyleSheet(
            f"background: {t['bg_secondary']};"
            f"border-right: 1px solid {t['border_subtle']};"
        )
        self._filter_combo.setStyleSheet(
            f"QComboBox#FilterChipCombo {{"
            f"  color: {t['text_secondary']}; font-size: 11px; background: {t['bg_tertiary']};"
            f"  border: 1px solid {t['border_subtle']}; border-radius: 12px; padding: 5px 12px;"
            f"}}"
            f"QComboBox#FilterChipCombo:hover {{ border-color: {t['border_strong']}; }}"
            f"QComboBox#FilterChipCombo::drop-down {{ width: 0px; border: none; }}"
            f"QComboBox#FilterChipCombo::down-arrow {{ width: 0px; height: 0px; image: none; }}"
        )

    # ── Левая панель: список ──────────────────────────────────────

    def _build_list_panel(self) -> QWidget:
        t = theme_manager.tokens
        self._list_panel = QWidget()
        panel = self._list_panel
        panel.setMinimumWidth(280)
        panel.setStyleSheet(
            f"background: {t['bg_secondary']};"
            f"border-right: 1px solid {t['border_subtle']};"
        )
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Фильтры
        filter_bar = QWidget()
        filter_bar.setObjectName("EditorFilterBar")
        filter_bar.setMinimumHeight(44)  # Минимальная высота
        filter_bar.setMaximumHeight(52)  # Максимальная высота
        fb_lay = QHBoxLayout(filter_bar)
        fb_lay.setContentsMargins(10, 0, 10, 0)
        fb_lay.setSpacing(6)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Поиск по типу…")
        self._search.setObjectName("FilePathBox")
        self._search.setMinimumHeight(32)  # Минимальная высота вместо фиксированной
        self._search.textChanged.connect(self._apply_filter)
        fb_lay.addWidget(self._search)

        self._filter_combo = QComboBox()
        self._filter_combo.setObjectName("FilterChipCombo")
        self._filter_combo.addItems([
            "Все", "< 30%", "< 40%", "< 50%", "< 70%", ">= 70%"
        ])
        self._filter_combo.setStyleSheet(
            f"QComboBox#FilterChipCombo {{"
            f"  color: {t['text_secondary']}; font-size: 11px; background: {t['bg_tertiary']};"
            f"  border: 1px solid {t['border_subtle']}; border-radius: 12px; padding: 5px 12px;"
            f"}}"
            f"QComboBox#FilterChipCombo:hover {{ border-color: {t['border_strong']}; }}"
            f"QComboBox#FilterChipCombo::drop-down {{ width: 0px; border: none; }}"
            f"QComboBox#FilterChipCombo::down-arrow {{ width: 0px; height: 0px; image: none; }}"
        )
        self._filter_combo.currentTextChanged.connect(self._apply_filter)
        # ЗАДАЧА 1: Стилизация popup для корректного отображения темы
        connect_combobox_theme_updates(self._filter_combo)
        
        fb_lay.addWidget(self._filter_combo)

        lay.addWidget(filter_bar)

        # Список
        self._list_view = QListView()
        self._list_view.setModel(self._model)
        self._list_view.setItemDelegate(SignItemDelegate())
        self._list_view.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._list_view.setSpacing(0)
        self._list_view.setObjectName("SignListView")
        self._list_view.selectionModel().currentChanged.connect(
            self._on_list_selection
        )
        lay.addWidget(self._list_view)

        # Кнопки навигации
        nav_bar = QWidget()
        nav_bar.setObjectName("EditorNavBar")
        nav_bar.setMinimumHeight(40)  # Минимальная высота
        nav_bar.setMaximumHeight(48)  # Максимальная высота

        nb_lay = QHBoxLayout(nav_bar)
        nb_lay.setContentsMargins(8, 0, 8, 0)
        nb_lay.setSpacing(6)

        self._btn_prev = QPushButton("← Пред.")
        self._btn_next = QPushButton("След. →")
        for btn in (self._btn_prev, self._btn_next):
            btn.setObjectName("BtnSecondary")
            # ЗАДАЧА 4: Убираем setMinimumHeight - используем QSS (36px)
            btn.setFixedWidth(130)  # Увеличено — 100px было < min-width(120px) из QSS, текст резался
            btn.setSizePolicy(
                QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
            )
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_prev.clicked.connect(self._go_prev)
        self._btn_next.clicked.connect(self._go_next)
        self._lbl_nav = QLabel("—")
        self._lbl_nav.setObjectName("EditorNavLabel")
        self._lbl_nav.setAlignment(Qt.AlignmentFlag.AlignCenter)

        nb_lay.addWidget(self._btn_prev)
        nb_lay.addWidget(self._lbl_nav)
        nb_lay.addWidget(self._btn_next)
        lay.addWidget(nav_bar)
        return panel

    # ── Правая панель: детали + редактор ─────────────────────────

    def _build_detail_panel(self) -> QWidget:
        t = theme_manager.tokens
        panel = QWidget()
        panel.setObjectName("ContentArea")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── Кадр превью ───────────────────────────────────────────
        frame_card = QWidget()
        frame_card.setObjectName("Card")
        frame_lay = QVBoxLayout(frame_card)
        frame_lay.setContentsMargins(0, 0, 0, 0)
        frame_lay.setSpacing(0)

        # Заголовок кадра
        fh = QWidget()
        fh.setObjectName("PreviewHeader")
        fh.setMinimumHeight(36)  # Минимальная высота
        fh.setMaximumHeight(44)  # Максимальная высота
        fh_lay = QHBoxLayout(fh)
        fh_lay.setContentsMargins(14, 0, 14, 0)
        fh_title = QLabel("КАДР")
        fh_title.setObjectName("CardTitle")
        fh_lay.addWidget(fh_title)
        fh_lay.addStretch()
        self._lbl_frame_info = QLabel("—")
        self._lbl_frame_info.setObjectName("PreviewFrameInfo")
        fh_lay.addWidget(self._lbl_frame_info)
        frame_lay.addWidget(fh)

        self._frame_label = QLabel()
        self._frame_label.setObjectName("VideoLabel")
        self._frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._frame_label.setMinimumHeight(300)
        frame_lay.addWidget(self._frame_label)

        lay.addWidget(frame_card, stretch=3)

        # ── Нижняя панель: мета + редактор ────────────────────────
        bottom = QWidget()
        bottom_lay = QHBoxLayout(bottom)
        bottom_lay.setContentsMargins(20, 16, 20, 16)
        bottom_lay.setSpacing(20)

        # Мета-информация
        meta_col = QVBoxLayout()
        meta_col.setSpacing(8)

        self._lbl_conf     = self._meta_val("—", big=True)
        self._lbl_gps_conf = self._meta_val("—")
        self._lbl_type     = self._meta_val("—")
        self._lbl_name     = self._meta_val("—")
        self._lbl_time     = self._meta_val("—")
        self._lbl_video    = self._meta_val("—")
        self._lbl_side     = self._meta_val("—")

        meta_col.addWidget(self._meta_label("Уверенность класс."))
        meta_col.addWidget(self._lbl_conf)
        meta_col.addWidget(self._meta_label("Уверенность GPS"))
        meta_col.addWidget(self._lbl_gps_conf)
        meta_col.addSpacing(4)
        meta_col.addWidget(self._meta_label("Тип"))
        meta_col.addWidget(self._lbl_type)
        meta_col.addWidget(self._meta_label("Название"))
        meta_col.addWidget(self._lbl_name)
        meta_col.addWidget(self._meta_label("Время / Видео"))
        meta_col.addWidget(self._lbl_time)
        meta_col.addWidget(self._meta_label("Сторона"))
        meta_col.addWidget(self._lbl_side)
        meta_col.addStretch()
        bottom_lay.addLayout(meta_col, stretch=1)

        # Разделитель
        vsep = QFrame()
        vsep.setObjectName("Separator")
        vsep.setFixedWidth(1)
        bottom_lay.addWidget(vsep)

        # Редактор
        edit_col = QVBoxLayout()
        edit_col.setSpacing(10)

        edit_title = QLabel("РЕДАКТИРОВАТЬ")
        edit_title.setObjectName("CardTitle")
        edit_col.addWidget(edit_title)

        # Поиск типа знака
        edit_col.addWidget(self._meta_label("Тип знака"))
        self._type_search = QLineEdit()
        self._type_search.setPlaceholderText("Введите тип (напр. 3.24) или название…")
        self._type_search.textChanged.connect(self._on_type_search)
        edit_col.addWidget(self._type_search)

        self._type_combo = QComboBox()
        self._type_combo.setMaxVisibleItems(10)
        self._type_combo.currentTextChanged.connect(self._on_type_selected)
        # ЗАДАЧА 1: Стилизация popup для корректного отображения темы
        connect_combobox_theme_updates(self._type_combo)
        
        edit_col.addWidget(self._type_combo)

        # Текст на знаке
        self._text_label = QLabel("ТЕКСТ НА ЗНАКЕ")
        self._text_label.setObjectName("CardTitle")
        self._text_label.setVisible(False)
        edit_col.addWidget(self._text_label)

        self._text_input = QLineEdit()
        self._text_input.setPlaceholderText("Значение (напр. 40 для знака 3.24)…")
        self._text_input.setVisible(False)
        edit_col.addWidget(self._text_input)

        edit_col.addStretch()

        # Кнопки действий
        actions = QHBoxLayout()
        actions.setSpacing(8)

        self._btn_jump_frame = QPushButton("⏩  К кадру")
        self._btn_apply      = QPushButton("✓  Применить")
        self._btn_delete     = QPushButton("✕  Удалить")

        self._btn_jump_frame.setObjectName("BtnSecondary")
        self._btn_apply.setObjectName("BtnPrimary")
        self._btn_delete.setObjectName("BtnDanger")

        for btn in (self._btn_jump_frame, self._btn_apply, self._btn_delete):
            btn.setMinimumHeight(36)
            btn.setSizePolicy(
                QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed
            )
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setEnabled(False)

        self._btn_jump_frame.clicked.connect(self._on_jump_to_frame)
        self._btn_apply.clicked.connect(self._on_apply)
        self._btn_delete.clicked.connect(self._on_delete)

        actions.addWidget(self._btn_jump_frame)
        actions.addWidget(self._btn_apply)
        actions.addWidget(self._btn_delete)
        edit_col.addLayout(actions)

        bottom_lay.addLayout(edit_col, stretch=2)
        lay.addWidget(bottom, stretch=2)

        return panel

    # ── Вспомогательные виджеты ───────────────────────────────────

    def _meta_label(self, text: str) -> QLabel:
        lbl = QLabel(text.upper())
        lbl.setObjectName("CardTitle")
        return lbl

    def _meta_val(self, text: str, big: bool = False) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("MetaValueBig" if big else "MetaValue")
        return lbl

    # ── Загрузка / сохранение ─────────────────────────────────────

    def load_geojson(self, path: str = "") -> None:
        """Загружает GeoJSON и строит список знаков."""
        try:
            target = path or config.PATH_TO_GEOJSON
            print(f"[ErrorEditor] load_geojson вызван, target = {target}")
            
            if not target:
                print("[ErrorEditor] target пустой, выход")
                return
            if not os.path.exists(target):
                print(f"[ErrorEditor] Файл не существует: {target}")
                return

            print(f"[ErrorEditor] Загружаем GeoJSON из {target}")
            with open(target, encoding="utf-8") as f:
                data = geojson.load(f)

            features = data.get("features", [])
            print(f"[ErrorEditor] Найдено {len(features)} features в GeoJSON")
            
            records = []
            for feat in features:
                try:
                    props = feat.get("properties", {})
                    if props.get("type"):
                        records.append(SignRecord(feat))
                except Exception as e:
                    print(f"[ErrorEditor] Ошибка при создании SignRecord: {e}")
                    continue
            
            print(f"[ErrorEditor] Создано {len(records)} SignRecord объектов")

            self._model.load(records)
            self._populate_type_combo("")
            self._update_counters()
            self._btn_save.setEnabled(True)

            # Выбрать первый элемент
            if records:
                self._list_view.setCurrentIndex(self._model.index(0))
                print(f"[ErrorEditor] Выбран первый элемент, всего записей: {len(records)}")
            else:
                print("[ErrorEditor] Нет записей для отображения")
                
        except Exception as e:
            print(f"[ErrorEditor] КРИТИЧЕСКАЯ ОШИБКА в load_geojson: {e}")
            import traceback
            traceback.print_exc()

    def save_geojson(self) -> None:
        """Сохраняет изменения в GeoJSON."""
        target = config.PATH_TO_GEOJSON
        if not target:
            return

        # Загружаем оригинал
        with open(target, encoding="utf-8") as f:
            data = geojson.load(f)

        records_by_id = {r.id: r for r in self._model.all_records()}

        new_features = []
        for feat in data.get("features", []):
            fid = feat.get("properties", {}).get("id", "")
            rec = records_by_id.get(fid)
            if rec is None:
                new_features.append(feat)
                continue
            if rec.deleted:
                continue   # пропускаем удалённые
            if rec.modified:
                feat["properties"]["type"] = rec.new_type
                if rec.new_type in CODES_SIGNS:
                    feat["properties"]["code"] = int(CODES_SIGNS[rec.new_type])
                if rec.new_type in TYPE_SIGNS_WITH_TEXT:
                    feat["properties"]["SEM250"] = rec.new_text
                    feat["properties"]["MVALUE"] = rec.new_text
                else:
                    feat["properties"].pop("SEM250", None)
                    feat["properties"].pop("MVALUE", None)
            new_features.append(feat)

        data["features"] = new_features
        with open(target, "w", encoding="utf-8") as f:
            geojson.dump(data, f, ensure_ascii=False)

        self._btn_save.setStyleSheet(
            f"background: {theme_manager.tokens['success']}; color: #fff;"
            "border-radius: 6px; padding: 8px 24px;"
        )
        QTimer.singleShot(2000, lambda: self._btn_save.setStyleSheet(""))

    # ── Отображение знака ─────────────────────────────────────────

    def _on_list_selection(self, current: QModelIndex, _) -> None:
        row = current.row()
        rec = self._model.record_at(row)
        if rec is None:
            return
        self._current_row = row
        self._current_rec = rec
        self._show_record(rec)
        self._update_nav_label()

    def _show_record(self, rec: SignRecord) -> None:
        """Отображает знак в правой панели."""
        t = theme_manager.tokens

        # Мета - уверенность классификации
        conf_color = SignItemDelegate._conf_color(rec.confidence, t)
        self._lbl_conf.setText(f"{rec.confidence_pct}%")
        self._lbl_conf.setStyleSheet(
            f"color: {conf_color}; font-size: 24px; font-weight: 300;"
            "background: transparent;"
        )
        
        # Уверенность GPS
        gps_conf_pct = int(rec.gps_confidence * 100)
        gps_color = SignItemDelegate._conf_color(rec.gps_confidence, t)
        self._lbl_gps_conf.setText(f"{gps_conf_pct}%")
        self._lbl_gps_conf.setStyleSheet(
            f"color: {gps_color}; font-size: 16px; font-weight: 400;"
            "background: transparent;"
        )
        
        self._lbl_type.setText(rec.new_type)
        self._lbl_name.setText(NAMES_SIGNS_BY_TYPE.get(rec.new_type, "—"))
        self._lbl_time.setText(f"{rec.time}  ·  {rec.video}")
        self._lbl_side.setText("Левая" if rec.is_left else "Правая")

        # Кадр превью
        self._load_frame(rec)

        # Редактор
        self._type_search.blockSignals(True)
        self._type_search.setText(rec.new_type)
        self._type_search.blockSignals(False)
        self._populate_type_combo(rec.new_type)

        has_text = rec.new_type in TYPE_SIGNS_WITH_TEXT
        self._text_label.setVisible(has_text)
        self._text_input.setVisible(has_text)
        self._text_input.setText(rec.new_text)

        # Кнопки
        for btn in (self._btn_apply, self._btn_delete, self._btn_jump_frame):
            btn.setEnabled(not rec.deleted)

    def _load_frame(self, rec: SignRecord) -> None:
        """
        Task C: Загружает кадр из видеофайла и рисует bbox.
        Добавлена диагностика для чёрных/пустых кадров.
        """
        t = theme_manager.tokens
        info = rec.abs_frame_for_video()

        if info is None or not config.PATH_TO_VIDEO or not config.VIDEOS:
            self._frame_label.setText("Нет данных о кадре")
            self._lbl_frame_info.setText("—")
            return

        video_idx, frame_num = info
        if video_idx >= len(config.VIDEOS):
            self._frame_label.setText("Видео не найдено")
            return

        video_path = os.path.join(config.PATH_TO_VIDEO, config.VIDEOS[video_idx])

        # Закрываем предыдущий cap
        try:
            if self._cap:
                self._cap.release()
                self._cap = None
        except Exception as e:
            print(f"[ErrorEditor] Ошибка при закрытии VideoCapture: {e}")

        try:
            self._cap = cv2.VideoCapture(video_path)
            if not self._cap.isOpened():
                self._frame_label.setText("Не удалось открыть видео")
                self._cap = None
                return
                
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            ret, frame = self._cap.read()

            if not ret:
                self._frame_label.setText("Не удалось прочитать кадр")
                return
        except Exception as e:
            print(f"[ErrorEditor] Ошибка при открытии видео: {e}")
            self._frame_label.setText(f"Ошибка: {str(e)}")
            return

        # Task C: Диагностика пустых/чёрных кадров
        mean_brightness = frame.mean()
        if mean_brightness < 5:
            print(f"[ErrorEditor] ВНИМАНИЕ: Кадр выглядит пустым (яркость={mean_brightness:.1f}) - возможно неверный индекс")
        
        frame = cv2.resize(frame, (960, 540))

        # Рисуем bbox
        if rec.bbox:
            x, y, w, h = rec.bbox
            # Масштабируем bbox под resize 960x540
            sx = 960 / 1920
            sy = 540 / 1080
            cv2.rectangle(
                frame,
                (int(x * sx), int(y * sy)),
                (int((x + w) * sx), int((y + h) * sy)),
                (61, 142, 240), 2
            )
        
        # Task C: Если кадр очень тёмный, добавляем текстовый оверлей
        if mean_brightness < 5:
            cv2.putText(
                frame,
                "! Pustoy kadr - vozmozhno neverni indeks",
                (20, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 255),  # Жёлтый
                2
            )

        # BGR → RGB → QPixmap
        rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h_, w_, ch = rgb.shape
        qimg  = QImage(rgb.data, w_, h_, ch * w_, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)

        self._frame_label.setPixmap(
            pixmap.scaled(
                self._frame_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self._lbl_frame_info.setText(
            f"{config.VIDEOS[video_idx]}  ·  кадр {frame_num}"
        )

    # ── Фильтрация ────────────────────────────────────────────────

    def _apply_filter(self) -> None:
        text        = self._search.text().lower()
        filter_text = self._filter_combo.currentText()
        
        # Определяем порог уверенности
        threshold_min = 0.0
        threshold_max = 1.0
        
        if filter_text == "< 30%":
            threshold_max = 0.30
        elif filter_text == "< 40%":
            threshold_max = 0.40
        elif filter_text == "< 50%":
            threshold_max = 0.50
        elif filter_text == "< 70%":
            threshold_max = 0.70
        elif filter_text == ">= 70%":
            threshold_min = 0.70

        for row in range(self._model.rowCount()):
            rec = self._model.record_at(row)
            if rec is None:
                continue
            match_text = (not text
                          or text in rec.type.lower()
                          or text in NAMES_SIGNS_BY_TYPE.get(rec.type, "").lower())
            match_conf = (filter_text == "Все" 
                         or (threshold_min <= rec.total_confidence < threshold_max))
            self._list_view.setRowHidden(row, not (match_text and match_conf))

    # ── Навигация ─────────────────────────────────────────────────

    def _go_prev(self) -> None:
        row = max(0, self._current_row - 1)
        self._list_view.setCurrentIndex(self._model.index(row))

    def _go_next(self) -> None:
        row = min(self._model.rowCount() - 1, self._current_row + 1)
        self._list_view.setCurrentIndex(self._model.index(row))

    def _update_nav_label(self) -> None:
        total = self._model.rowCount()
        self._lbl_nav.setText(
            f"{self._current_row + 1} / {total}" if total else "—"
        )

    # ── Редактор ──────────────────────────────────────────────────

    def _populate_type_combo(self, current: str) -> None:
        """Заполняет комбобокс всеми типами знаков."""
        self._type_combo.blockSignals(True)
        self._type_combo.clear()

        items = sorted(
            [(k, f"{k} — {v}") for k, v in NAMES_SIGNS_BY_TYPE.items()
             if k in CODES_SIGNS],
            key=lambda x: x[0],
        )
        for code, label in items:
            self._type_combo.addItem(label, userData=code)

        # Установить текущий
        for i in range(self._type_combo.count()):
            if self._type_combo.itemData(i) == current:
                self._type_combo.setCurrentIndex(i)
                break

        self._type_combo.blockSignals(False)

    def _on_type_search(self, text: str) -> None:
        """Фильтрует комбобокс при вводе."""
        text_low = text.lower()
        for i in range(self._type_combo.count()):
            label = self._type_combo.itemText(i).lower()
            code  = (self._type_combo.itemData(i) or "").lower()
            hide  = text_low not in label and text_low not in code
            # QComboBox не поддерживает скрытие item напрямую —
            # обновляем через setItemData видимость в модели
            self._type_combo.model().item(i).setEnabled(not hide)

    def _on_type_selected(self, label: str) -> None:
        if not self._current_rec:
            return
        code = self._type_combo.currentData()
        if not code:
            return
        has_text = code in TYPE_SIGNS_WITH_TEXT
        self._text_label.setVisible(has_text)
        self._text_input.setVisible(has_text)

    def _on_apply(self) -> None:
        if not self._current_rec:
            return
        code = self._type_combo.currentData()
        if not code:
            return
        rec = self._current_rec
        rec.new_type = code
        rec.new_text = self._text_input.text() if code in TYPE_SIGNS_WITH_TEXT else ""
        rec.modified = (rec.new_type != rec.type or rec.new_text != rec.text)
        self._model.update_record(self._current_row)

        # Обновляем мета
        self._lbl_type.setText(rec.new_type)
        self._lbl_name.setText(NAMES_SIGNS_BY_TYPE.get(rec.new_type, "—"))
        self._btn_save.setEnabled(True)

    def _on_delete(self) -> None:
        if not self._current_rec:
            return
        self._current_rec.deleted = True
        self._model.update_record(self._current_row)
        self._btn_apply.setEnabled(False)
        self._btn_delete.setEnabled(False)
        self._update_counters()
        self._btn_save.setEnabled(True)
        # Переходим к следующему
        self._go_next()

    def _on_jump_to_frame(self) -> None:
        if not self._current_rec:
            return
        info = self._current_rec.abs_frame_for_video()
        if info:
            self.jump_to_frame.emit(info[0], info[1])

    # ── Счётчики ─────────────────────────────────────────────────

    def _update_counters(self) -> None:
        records  = self._model.all_records()
        total    = sum(1 for r in records if not r.deleted)
        low_conf = sum(1 for r in records if not r.deleted and r.confidence < 0.5)
        self._lbl_total.setText(f"{total} знаков")
        self._lbl_low_conf.setText(f"{low_conf} < 50%")

    # ── Публичное API ─────────────────────────────────────────────

    def reload(self) -> None:
        """Вызывается из MainWindow после завершения обработки."""
        self.load_geojson()
    
    def cleanup(self):
        """Безопасная очистка ресурсов перед закрытием."""
        try:
            if self._cap:
                self._cap.release()
                self._cap = None
        except Exception as e:
            print(f"[ErrorEditor] Ошибка при освобождении VideoCapture: {e}")