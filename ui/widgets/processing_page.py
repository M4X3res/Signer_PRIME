from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QPlainTextEdit,
    QFrame, QSizePolicy, QGridLayout
)
from PyQt6.QtCore import Qt, pyqtSignal, QDateTime
from PyQt6.QtGui import QPixmap, QTextCursor, QFont
from ui.themes.theme_manager import theme_manager


class ProcessingPage(QWidget):
    stop_requested = pyqtSignal()
    finish_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ContentArea")

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(16)

        # ── Header ──────────────────────────────────────────────
        header = QHBoxLayout()

        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel("Обработка")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Видеопоток · детекция знаков · запись GPS-координат")
        subtitle.setObjectName("PageSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles)
        header.addStretch()

        self.btn_pause = QPushButton("⏸  Пауза")
        self.btn_pause.setObjectName("BtnSecondary")
        self.btn_pause.setFixedHeight(36)
        self.btn_pause.setMinimumWidth(100)
        self.btn_pause.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pause.setEnabled(False)

        self.btn_finish = QPushButton("■  Завершить")
        self.btn_finish.setObjectName("BtnPrimary")
        self.btn_finish.setFixedHeight(36)
        self.btn_finish.setMinimumWidth(120)
        self.btn_finish.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_finish.setEnabled(False)
        self.btn_finish.clicked.connect(self.finish_requested)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addWidget(self.btn_pause)
        btn_row.addWidget(self.btn_finish)
        header.addLayout(btn_row)

        root.addLayout(header)

        # ── Main split: video | stats ────────────────────────────
        split = QHBoxLayout()
        split.setSpacing(16)

        # Left: video preview
        video_card = QWidget()
        video_card.setObjectName("Card")
        video_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        video_layout = QVBoxLayout(video_card)
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_layout.setSpacing(0)

        # Заголовок карточки
        video_header = QWidget()
        video_header.setStyleSheet(
            f"background: {theme_manager.tokens['bg_tertiary']};"
            "border-radius: 8px 8px 0px 0px;"
        )
        video_header.setFixedHeight(36)
        vh_layout = QHBoxLayout(video_header)
        vh_layout.setContentsMargins(14, 0, 14, 0)
        video_title = QLabel("ПРЕДПРОСМОТР КАДРА")
        video_title.setObjectName("CardTitle")
        vh_layout.addWidget(video_title)
        vh_layout.addStretch()

        self._frame_info = QLabel("кадр: — / —")
        self._frame_info.setStyleSheet(
            f"color: {theme_manager.tokens['text_tertiary']};"
            "font-size: 10px; background: transparent;"
        )
        vh_layout.addWidget(self._frame_info)
        video_layout.addWidget(video_header)

        # Сам label для кадров
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setMinimumSize(480, 270)
        self.video_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.video_label.setStyleSheet(
            f"background: {theme_manager.tokens['bg_primary']};"
            "border-radius: 0px 0px 8px 8px;"
        )
        self._show_placeholder()
        video_layout.addWidget(self.video_label)

        split.addWidget(video_card, stretch=3)

        # Right: stats column
        stats_col = QVBoxLayout()
        stats_col.setSpacing(12)

        # Progress card
        prog_card = QWidget()
        prog_card.setObjectName("Card")
        prog_card.setFixedWidth(260)
        prog_layout = QVBoxLayout(prog_card)
        prog_layout.setContentsMargins(16, 14, 16, 16)
        prog_layout.setSpacing(10)

        prog_title = QLabel("ПРОГРЕСС")
        prog_title.setObjectName("CardTitle")
        prog_layout.addWidget(prog_title)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setTextVisible(False)
        prog_layout.addWidget(self.progress_bar)

        self._pct_lbl = QLabel("0%")
        self._pct_lbl.setObjectName("StatValue")
        self._pct_lbl.setStyleSheet(
            f"color: {theme_manager.tokens['text_primary']};"
            "font-size: 32px; font-weight: 200; letter-spacing: -1px;"
            "background: transparent;"
        )

        self._eta_lbl = QLabel("ETA: —")
        self._eta_lbl.setStyleSheet(
            f"color: {theme_manager.tokens['text_tertiary']};"
            "font-size: 11px; background: transparent;"
        )
        prog_layout.addWidget(self._pct_lbl)
        prog_layout.addWidget(self._eta_lbl)

        stats_col.addWidget(prog_card)

        # Mini stat grid
        mini_grid_card = QWidget()
        mini_grid_card.setObjectName("Card")
        mini_grid_card.setFixedWidth(260)
        mini_layout = QVBoxLayout(mini_grid_card)
        mini_layout.setContentsMargins(16, 14, 16, 16)
        mini_layout.setSpacing(10)

        mini_title = QLabel("СТАТИСТИКА")
        mini_title.setObjectName("CardTitle")
        mini_layout.addWidget(mini_title)

        grid = QGridLayout()
        grid.setSpacing(10)

        self._stat_frames   = self._make_mini_stat("0", "кадров обр.")
        self._stat_signs    = self._make_mini_stat("0", "знаков найд.")
        self._stat_fps      = self._make_mini_stat("—", "FPS")
        self._stat_video    = self._make_mini_stat("1/1", "видео")

        grid.addWidget(self._stat_frames[0],  0, 0)
        grid.addWidget(self._stat_signs[0],   0, 1)
        grid.addWidget(self._stat_fps[0],     1, 0)
        grid.addWidget(self._stat_video[0],   1, 1)

        mini_layout.addLayout(grid)
        stats_col.addWidget(mini_grid_card)
        stats_col.addStretch()

        split.addLayout(stats_col, stretch=0)
        root.addLayout(split, stretch=3)

        # ── Log console ──────────────────────────────────────────
        log_card = QWidget()
        log_card.setObjectName("Card")
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(0)

        log_header = QWidget()
        log_header.setFixedHeight(36)
        log_header.setStyleSheet(
            f"background: {theme_manager.tokens['bg_tertiary']};"
            "border-radius: 8px 8px 0px 0px;"
        )
        lh_layout = QHBoxLayout(log_header)
        lh_layout.setContentsMargins(14, 0, 14, 0)
        log_title = QLabel("ЛОГ ОБРАБОТКИ")
        log_title.setObjectName("CardTitle")
        lh_layout.addWidget(log_title)
        lh_layout.addStretch()

        self._clear_btn = QPushButton("очистить")
        self._clear_btn.setObjectName("BtnIcon")
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.setStyleSheet(
            f"color: {theme_manager.tokens['text_tertiary']};"
            "font-size: 10px; background: transparent; border: none;"
            "text-decoration: underline;"
        )
        self._clear_btn.clicked.connect(self._clear_log)
        lh_layout.addWidget(self._clear_btn)

        self.log_console = QPlainTextEdit()
        self.log_console.setObjectName("LogConsole")
        self.log_console.setReadOnly(True)
        self.log_console.setFixedHeight(130)
        self.log_console.setStyleSheet(
            f"background: {theme_manager.tokens['bg_primary']};"
            f"border: none; border-radius: 0px 0px 8px 8px;"
            f"color: {theme_manager.tokens['text_secondary']};"
            "font-family: 'Cascadia Code','Consolas',monospace; font-size: 11px;"
            "padding: 10px 14px;"
        )

        log_layout.addWidget(log_header)
        log_layout.addWidget(self.log_console)

        root.addWidget(log_card, stretch=1)

    # ── Helpers ────────────────────────────────────────────────

    def _make_mini_stat(self, value: str, label: str):
        t = theme_manager.tokens
        card = QWidget()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(2)

        val_lbl = QLabel(value)
        val_lbl.setStyleSheet(
            f"color: {t['text_primary']}; font-size: 18px;"
            "font-weight: 300; background: transparent;"
        )

        lbl_lbl = QLabel(label.upper())
        lbl_lbl.setStyleSheet(
            f"color: {t['text_tertiary']}; font-size: 9px;"
            "font-weight: 600; letter-spacing: 0.8px; background: transparent;"
        )

        layout.addWidget(val_lbl)
        layout.addWidget(lbl_lbl)
        return card, val_lbl

    def _show_placeholder(self):
        t = theme_manager.tokens
        self.video_label.setText("Видео не запущено")
        self.video_label.setStyleSheet(
            f"background: {t['bg_primary']}; color: {t['text_tertiary']};"
            "font-size: 13px; border-radius: 0px 0px 8px 8px;"
        )

    def _clear_log(self):
        self.log_console.clear()

    # ── Public API ─────────────────────────────────────────────

    def set_frame(self, pixmap: QPixmap):
        self.video_label.setPixmap(
            pixmap.scaled(
                self.video_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def set_progress(self, value: int, eta: str = ""):
        self.progress_bar.setValue(value)
        self._pct_lbl.setText(f"{value}%")
        if eta:
            self._eta_lbl.setText(f"ETA: {eta}")

    def set_frame_info(self, current: int, total: int):
        self._frame_info.setText(f"кадр: {current:,} / {total:,}".replace(",", " "))

    def set_stats(self, frames: int, signs: int, fps: float, video_idx: int, video_total: int):
        self._stat_frames[1].setText(str(frames))
        self._stat_signs[1].setText(str(signs))
        self._stat_fps[1].setText(f"{fps:.1f}")
        self._stat_video[1].setText(f"{video_idx}/{video_total}")

    def log(self, message: str, level: str = "info"):
        """Добавить строку в лог. level: info | warn | error | success"""
        t = theme_manager.tokens
        colors = {
            "info":    t["text_secondary"],
            "warn":    t["warning"],
            "error":   t["error"],
            "success": t["success"],
        }
        color = colors.get(level, t["text_secondary"])
        ts = QDateTime.currentDateTime().toString("hh:mm:ss")
        html = (
            f'<span style="color:{t["text_tertiary"]}">[{ts}]</span> '
            f'<span style="color:{color}">{message}</span>'
        )
        self.log_console.appendHtml(html)
        self.log_console.moveCursor(QTextCursor.MoveOperation.End)

    def set_active(self, active: bool):
        self.btn_pause.setEnabled(active)
        self.btn_finish.setEnabled(active)