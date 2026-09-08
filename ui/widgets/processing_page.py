from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QPlainTextEdit,
    QFrame, QSizePolicy, QGridLayout
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QTextCursor, QFont
from ui.themes.theme_manager import theme_manager
from datetime import datetime


class ProcessingPage(QWidget):
    stop_requested = pyqtSignal()
    finish_requested = pyqtSignal()
    pause_requested = pyqtSignal()
    resume_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ContentArea")
        
        self._is_paused = False
        self._finish_clicked = False  # Защита от двойного клика

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

        self.btn_pause = QPushButton("⏸   Пауза")
        self.btn_pause.setObjectName("BtnSecondary")
        self.btn_pause.setSizePolicy(
            QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed
        )
        self.btn_pause.setMinimumHeight(36)
        self.btn_pause.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pause.setEnabled(False)
        self.btn_pause.clicked.connect(self._on_pause_clicked)

        self.btn_finish = QPushButton("■   Завершить")
        self.btn_finish.setObjectName("BtnPrimary")
        self.btn_finish.setSizePolicy(
            QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed
        )
        self.btn_finish.setMinimumHeight(36)
        self.btn_finish.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_finish.setEnabled(False)
        self.btn_finish.clicked.connect(self._on_finish_clicked)

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
        video_header.setObjectName("PreviewHeader")
        video_header.setMinimumHeight(36)  # Минимальная высота
        video_header.setMaximumHeight(44)  # Максимальная высота
        vh_layout = QHBoxLayout(video_header)
        vh_layout.setContentsMargins(14, 0, 14, 0)
        video_title = QLabel("ПРЕДПРОСМОТР КАДРА")
        video_title.setObjectName("CardTitle")
        vh_layout.addWidget(video_title)
        vh_layout.addStretch()

        self._frame_info = QLabel("кадр: — / —")
        self._frame_info.setObjectName("PreviewFrameInfo")
        vh_layout.addWidget(self._frame_info)
        video_layout.addWidget(video_header)

        # Сам label для кадров
        self.video_label = QLabel()
        self.video_label.setObjectName("VideoLabel")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setMinimumSize(480, 270)
        self.video_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
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
        self._pct_lbl.setObjectName("ProgressPercent")

        self._eta_lbl = QLabel("ETA: —")
        self._eta_lbl.setObjectName("PreviewEta")
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
        log_header.setObjectName("PreviewHeader")
        log_header.setMinimumHeight(36)  # Минимальная высота
        log_header.setMaximumHeight(44)  # Максимальная высота
        lh_layout = QHBoxLayout(log_header)
        lh_layout.setContentsMargins(14, 0, 14, 0)
        log_title = QLabel("ЛОГ ОБРАБОТКИ")
        log_title.setObjectName("CardTitle")
        lh_layout.addWidget(log_title)
        lh_layout.addStretch()

        self._clear_btn = QPushButton("очистить")
        self._clear_btn.setObjectName("ClearLogBtn")
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.clicked.connect(self._clear_log)
        lh_layout.addWidget(self._clear_btn)

        self.log_console = QPlainTextEdit()
        self.log_console.setObjectName("LogConsole")
        self.log_console.setReadOnly(True)
        self.log_console.setMinimumHeight(100)  # Минимальная высота
        self.log_console.setMaximumHeight(200)  # Максимальная высота
        self.log_console.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        log_layout.addWidget(log_header)
        log_layout.addWidget(self.log_console)

        root.addWidget(log_card, stretch=1)

    # ── Helpers ────────────────────────────────────────────────

    def _make_mini_stat(self, value: str, label: str):
        card = QWidget()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(2)

        val_lbl = QLabel(value)
        val_lbl.setObjectName("MiniStatValue")

        lbl_lbl = QLabel(label.upper())
        lbl_lbl.setObjectName("MiniStatLabel")

        layout.addWidget(val_lbl)
        layout.addWidget(lbl_lbl)
        return card, val_lbl

    def _show_placeholder(self):
        self.video_label.setText("Видео не запущено")
        # Фон/цвет текста задаются глобальным QSS-правилом #VideoLabel
        # (см. ui/themes/modern_styles.py) — оно теперь одинаково корректно
        # работает в тёмной и светлой темах.

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
        ts = datetime.now().strftime("%H:%M:%S")
        html = (
            f'<span style="color:{t["text_tertiary"]}">[{ts}]</span> '
            f'<span style="color:{color}">{message}</span>'
        )
        self.log_console.appendHtml(html)
        self.log_console.moveCursor(QTextCursor.MoveOperation.End)

    def set_active(self, active: bool):
        self.btn_pause.setEnabled(active)
        self.btn_finish.setEnabled(active)
        if not active:
            self._is_paused = False
            self._finish_clicked = False  # Сброс флага при новой обработке
            self.btn_pause.setText("⏸   Пауза")
            self.btn_finish.setText("■   Завершить")  # Сброс текста кнопки
        else:
            # При активации возвращаем стандартные тексты
            self.btn_pause.setText("⏸   Пауза")
            self.btn_finish.setText("■   Завершить")
    
    def _on_finish_clicked(self):
        """Обработчик кнопки завершения с защитой от двойного клика."""
        # Защита от повторного нажатия
        if self._finish_clicked:
            print("[ProcessingPage] Кнопка 'Завершить' уже нажата, игнорируем повторный клик")
            return
        
        self._finish_clicked = True
        
        # Немедленно отключаем обе кнопки
        self.btn_finish.setEnabled(False)
        self.btn_pause.setEnabled(False)
        
        # Визуальная обратная связь
        self.btn_finish.setText("⏳  Завершение…")
        
        # Отправляем сигнал
        self.finish_requested.emit()
    
    def _on_pause_clicked(self):
        """Обработчик кнопки паузы."""
        self._is_paused = not self._is_paused
        if self._is_paused:
            self.btn_pause.setText("▶   Продолжить")
            self.pause_requested.emit()
        else:
            self.btn_pause.setText("⏸   Пауза")
            self.resume_requested.emit()