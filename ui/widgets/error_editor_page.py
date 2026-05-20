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

        # Уверенность: cnn_count / observation_count
        self.confidence: float = self._calc_confidence()

        # Координаты кадра
        self._abs_frames: list[int] = self._parse_int_list(
            self.props.get("absolute_frame_numbers", "")
        )
        self._frame_numbers: list[int] = self._parse_int_list(
            self.props.get("frame_numbers", "")
        )

        # Пиксельные координаты bbox (берём медианный кадр)
        self.bbox: Optional[tuple] = self._parse_median_bbox()

        # Изменения пользователя
        self.new_type: str  = self.type
        self.new_text: str  = self.text
        self.modified:  bool = False
        self.deleted:   bool = False

    def _calc_confidence(self) -> float:
        """
        cnn_count / observation_count.
        Парсим из строки вида '[1.21, 1.21, 1.23, 1.21]'.
        """
        raw = self.props.get("frame_numbers", "")
        total = len(self._parse_int_list(raw))
        if total == 0:
            return 0.0

        cnn_raw = self.props.get("pixel_coordinates_x", "")
        # Считаем совпадения лучшего класса
        cnn_list_raw = self.props.get("car_coordinates_x", "")  # прокси длины
        cnn_len = len(self._parse_float_list(cnn_list_raw))

        # Упрощённо: если нет данных — используем длину трека
        length = int(self.props.get("length", total) or total)
        if length == 0:
            return 0.0

        # Уверенность = length / total (сколько кадров знак "устойчиво" виден)
        return min(1.0, length / max(total, 1))

    def _parse_int_list(self, raw: str) -> list[int]:
        if not raw:
            return []
        nums = re.findall(r"-?\d+", str(raw))
        return [int(n) for n in nums]

    def _parse_float_list(self, raw: str) -> list[float]:
        if not raw:
            return []
        nums = re.findall(r"-?\d+\.?\d*", str(raw))
        return [float(n) for n in nums]

    def _parse_median_bbox(self) -> Optional[tuple[int,int,int,int]]:
        """Возвращает bbox из медианного кадра наблюдений."""
        xs = self._parse_int_list(self.props.get("pixel_coordinates_x", ""))
        ys = self._parse_int_list(self.props.get("pixel_coordinates_y", ""))
        ws = self._parse_int_list(self.props.get("w", ""))
        hs = self._parse_int_list(self.props.get("h", ""))
        if not all([xs, ys, ws, hs]):
            return None
        mid = len(xs) // 2
        return (xs[mid], ys[mid], ws[mid], hs[mid])

    @property
    def confidence_pct(self) -> int:
        return int(self.confidence * 100)

    @property
    def sign_name(self) -> str:
        return NAMES_SIGNS_BY_TYPE.get(self.type, "")

    def abs_frame_for_video(self) -> Optional[tuple[int, int]]:
        """Возвращает (video_idx, frame_in_video) для прыжка к кадру."""
        if not self._abs_frames:
            return None
        avg = sum(self._abs_frames) // len(self._abs_frames)
        video_idx      = avg // 63600
        frame_in_video = avg % 63600
        return video_idx, frame_in_video


class SignListModel(QAbstractListModel):
    """Qt модель для QListView — хранит список SignRecord."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._records: list[SignRecord] = []

    def load(self, records: list[SignRecord]) -> None:
        self.beginResetModel()
        # Сортировка: сначала наименее уверенные
        self._records = sorted(records, key=lambda r: r.confidence)
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

    # ── Topbar ────────────────────────────────────────────────────

    def _build_topbar(self) -> QWidget:
        t = theme_manager.tokens
        bar = QWidget()
        bar.setFixedHeight(48)
        bar.setStyleSheet(
            f"background: {t['bg_secondary']};"
            f"border-bottom: 1px solid {t['border_subtle']};"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 0, 20, 0)
        lay.setSpacing(12)

        title = QLabel("Редактор ошибок")
        title.setObjectName("PageTitle")
        lay.addWidget(title)
        lay.addStretch()

        # Счётчики
        self._lbl_total    = self._tb_badge("0 знаков", t["text_tertiary"])
        self._lbl_low_conf = self._tb_badge("0 < 50%", t["error"])
        lay.addWidget(self._lbl_total)
        lay.addWidget(self._lbl_low_conf)

        sep = QFrame()
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"background: {t['border_subtle']};")
        lay.addWidget(sep)

        # Кнопки
        self._btn_load = QPushButton("↑  Загрузить GeoJSON")
        self._btn_load.setObjectName("BtnSecondary")
        self._btn_load.setSizePolicy(
            QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed
        )
        self._btn_load.setMinimumHeight(34)
        self._btn_load.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_load.clicked.connect(self.load_geojson)

        self._btn_save = QPushButton("✓  Сохранить")
        self._btn_save.setObjectName("BtnPrimary")
        self._btn_save.setSizePolicy(
            QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed
        )
        self._btn_save.setMinimumHeight(34)
        self._btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_save.setEnabled(False)
        self._btn_save.clicked.connect(self.save_geojson)

        lay.addWidget(self._btn_load)
        lay.addWidget(self._btn_save)
        return bar

    def _tb_badge(self, text: str, color: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {color}; font-size: 11px; font-weight: 600;"
            "background: transparent; padding: 0 4px;"
        )
        return lbl

    # ── Левая панель: список ──────────────────────────────────────

    def _build_list_panel(self) -> QWidget:
        t = theme_manager.tokens
        panel = QWidget()
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
        filter_bar.setFixedHeight(44)
        filter_bar.setStyleSheet(
            f"background: {t['bg_tertiary']};"
            f"border-bottom: 1px solid {t['border_subtle']};"
        )
        fb_lay = QHBoxLayout(filter_bar)
        fb_lay.setContentsMargins(10, 0, 10, 0)
        fb_lay.setSpacing(6)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Поиск по типу…")
        self._search.setObjectName("FilePathBox")
        self._search.setFixedHeight(28)
        self._search.textChanged.connect(self._apply_filter)
        fb_lay.addWidget(self._search)

        self._chk_low = QCheckBox("< 50%")
        self._chk_low.setStyleSheet(
            f"color: {t['text_secondary']}; font-size: 11px; background: transparent;"
        )
        self._chk_low.stateChanged.connect(self._apply_filter)
        fb_lay.addWidget(self._chk_low)

        lay.addWidget(filter_bar)

        # Список
        self._list_view = QListView()
        self._list_view.setModel(self._model)
        self._list_view.setItemDelegate(SignItemDelegate())
        self._list_view.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._list_view.setSpacing(0)
        self._list_view.setStyleSheet(
            f"QListView {{ background: {t['bg_secondary']}; border: none; }}"
            f"QListView::item:selected {{ background: {t['accent_subtle']}; }}"
        )
        self._list_view.selectionModel().currentChanged.connect(
            self._on_list_selection
        )
        lay.addWidget(self._list_view)

        # Кнопки навигации
        nav_bar = QWidget()
        nav_bar.setFixedHeight(40)
        nav_bar.setStyleSheet(
            f"background: {t['bg_tertiary']};"
            f"border-top: 1px solid {t['border_subtle']};"
        )
        nb_lay = QHBoxLayout(nav_bar)
        nb_lay.setContentsMargins(8, 0, 8, 0)
        nb_lay.setSpacing(6)

        self._btn_prev = QPushButton("← Пред.")
        self._btn_next = QPushButton("След. →")
        for btn in (self._btn_prev, self._btn_next):
            btn.setObjectName("BtnSecondary")
            btn.setFixedHeight(28)
            btn.setSizePolicy(
                QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed
            )
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_prev.clicked.connect(self._go_prev)
        self._btn_next.clicked.connect(self._go_next)
        self._lbl_nav = QLabel("—")
        self._lbl_nav.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_nav.setStyleSheet(
            f"color: {t['text_tertiary']}; font-size: 11px; background: transparent;"
        )

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
        frame_card.setStyleSheet(
            f"background: {t['bg_secondary']};"
            f"border-bottom: 1px solid {t['border_subtle']};"
        )
        frame_lay = QVBoxLayout(frame_card)
        frame_lay.setContentsMargins(0, 0, 0, 0)
        frame_lay.setSpacing(0)

        # Заголовок кадра
        fh = QWidget()
        fh.setFixedHeight(36)
        fh.setStyleSheet(f"background: {t['bg_tertiary']};")
        fh_lay = QHBoxLayout(fh)
        fh_lay.setContentsMargins(14, 0, 14, 0)
        fh_title = QLabel("КАДР")
        fh_title.setObjectName("CardTitle")
        fh_lay.addWidget(fh_title)
        fh_lay.addStretch()
        self._lbl_frame_info = QLabel("—")
        self._lbl_frame_info.setStyleSheet(
            f"color: {t['text_tertiary']}; font-size: 10px; background: transparent;"
        )
        fh_lay.addWidget(self._lbl_frame_info)
        frame_lay.addWidget(fh)

        self._frame_label = QLabel()
        self._frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._frame_label.setMinimumHeight(300)
        self._frame_label.setStyleSheet(f"background: {t['bg_primary']};")
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

        self._lbl_conf  = self._meta_val("—", big=True)
        self._lbl_type  = self._meta_val("—")
        self._lbl_name  = self._meta_val("—")
        self._lbl_time  = self._meta_val("—")
        self._lbl_video = self._meta_val("—")
        self._lbl_side  = self._meta_val("—")

        meta_col.addWidget(self._meta_label("Уверенность"))
        meta_col.addWidget(self._lbl_conf)
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
        vsep.setFixedWidth(1)
        vsep.setStyleSheet(f"background: {t['border_subtle']};")
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
        t   = theme_manager.tokens
        lbl = QLabel(text)
        sz  = "20px" if big else "12px"
        fw  = "300"  if big else "400"
        lbl.setStyleSheet(
            f"color: {t['text_primary']}; font-size: {sz}; font-weight: {fw};"
            "background: transparent;"
        )
        return lbl

    # ── Загрузка / сохранение ─────────────────────────────────────

    def load_geojson(self, path: str = "") -> None:
        """Загружает GeoJSON и строит список знаков."""
        target = path or config.PATH_TO_GEOJSON
        if not target or not os.path.exists(target):
            return

        with open(target, encoding="utf-8") as f:
            data = geojson.load(f)

        records = [
            SignRecord(feat)
            for feat in data.get("features", [])
            if feat.get("properties", {}).get("type")
        ]

        self._model.load(records)
        self._populate_type_combo("")
        self._update_counters()
        self._btn_save.setEnabled(True)

        # Выбрать первый элемент
        if records:
            self._list_view.setCurrentIndex(self._model.index(0))

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

        # Мета
        conf_color = SignItemDelegate._conf_color(rec.confidence, t)
        self._lbl_conf.setText(f"{rec.confidence_pct}%")
        self._lbl_conf.setStyleSheet(
            f"color: {conf_color}; font-size: 24px; font-weight: 300;"
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
        """Загружает кадр из видеофайла и рисует bbox."""
        t = theme_manager.tokens
        info = rec.abs_frame_for_video()

        if info is None or not config.PATH_TO_VIDEO or not config.VIDEOS:
            self._frame_label.setText("Нет данных о кадре")
            self._frame_label.setStyleSheet(
                f"background: {t['bg_primary']}; color: {t['text_tertiary']};"
            )
            self._lbl_frame_info.setText("—")
            return

        video_idx, frame_num = info
        if video_idx >= len(config.VIDEOS):
            self._frame_label.setText("Видео не найдено")
            return

        video_path = os.path.join(config.PATH_TO_VIDEO, config.VIDEOS[video_idx])

        # Закрываем предыдущий cap
        if self._cap:
            self._cap.release()

        self._cap = cv2.VideoCapture(video_path)
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = self._cap.read()

        if not ret:
            self._frame_label.setText("Не удалось прочитать кадр")
            return

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
        text     = self._search.text().lower()
        low_only = self._chk_low.isChecked()

        for row in range(self._model.rowCount()):
            rec = self._model.record_at(row)
            if rec is None:
                continue
            match_text = (not text
                          or text in rec.type.lower()
                          or text in NAMES_SIGNS_BY_TYPE.get(rec.type, "").lower())
            match_conf = (not low_only or rec.confidence < 0.5)
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

    def __del__(self):
        if self._cap:
            self._cap.release()