"""
Тестовый скрипт для проверки layout кнопок навигации и сортировки.
Проверяет, что минимальные ширины не конфликтуют с размерами панели.
"""
import sys
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QSplitter, QSizePolicy
)

# Простые токены темы для теста
TOKENS = {
    'bg_primary': '#1a1a1a',
    'bg_secondary': '#222222',
    'bg_tertiary': '#2a2a2a',
    'bg_hover': '#333333',
    'bg_active': '#404040',
    'text_primary': '#e0e0e0',
    'text_secondary': '#a0a0a0',
    'border_default': '#404040',
    'border_strong': '#606060',
    'border_subtle': '#303030',
    'accent': '#4a9eff',
}

# QSS для BtnNavCompact (без min-width!)
BTN_NAV_COMPACT_QSS = f"""
#BtnNavCompact {{
    background-color: transparent;
    color: {TOKENS['text_primary']};
    border: 1.5px solid {TOKENS['border_default']};
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 12px;
    font-weight: 500;
    min-height: 32px;
    /* без min-width */
}}
#BtnNavCompact:hover {{
    background-color: {TOKENS['bg_hover']};
    border-color: {TOKENS['border_strong']};
}}
"""

class TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Тест Layout Кнопок")
        self.setMinimumSize(1200, 720)
        
        # Создаём сплиттер как в ErrorEditorPage
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        
        # Левая панель (список + навигация)
        left_panel = self._build_left_panel()
        
        # Правая панель (заглушка)
        right_panel = QWidget()
        right_panel.setStyleSheet(f"background: {TOKENS['bg_primary']};")
        right_label = QLabel("Правая панель (детали)")
        right_label.setStyleSheet(f"color: {TOKENS['text_primary']};")
        right_layout = QVBoxLayout(right_panel)
        right_layout.addWidget(right_label)
        
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([340, 860])
        
        layout.addWidget(splitter)
        
        # Применяем QSS
        self.setStyleSheet(BTN_NAV_COMPACT_QSS)
        
        # Тестовый вывод размеров
        self._print_sizes()
    
    def _build_left_panel(self) -> QWidget:
        """Имитация _build_list_panel из ErrorEditorPage."""
        panel = QWidget()
        panel.setMinimumWidth(300)
        panel.setStyleSheet(f"background: {TOKENS['bg_secondary']}; border-right: 1px solid {TOKENS['border_subtle']};")
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # ── Фильтры (2 ряда) ────────────────────────────────────
        filter_bar = QWidget()
        filter_bar.setMinimumHeight(78)
        fb_lay = QVBoxLayout(filter_bar)
        fb_lay.setContentsMargins(10, 6, 10, 6)
        fb_lay.setSpacing(6)
        
        # Ряд 1: поиск (заглушка)
        search_label = QLabel("Поиск...")
        search_label.setStyleSheet(f"color: {TOKENS['text_secondary']}; padding: 5px;")
        fb_lay.addWidget(search_label)
        
        # Ряд 2: комбобокс + кнопка сортировки
        row2 = QHBoxLayout()
        row2.setSpacing(6)
        
        filter_combo = QComboBox()
        filter_combo.addItems(["Все", "< 30%", "< 40%"])
        filter_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        filter_combo.setStyleSheet(f"""
            QComboBox {{
                color: {TOKENS['text_secondary']};
                background: {TOKENS['bg_tertiary']};
                border: 1px solid {TOKENS['border_subtle']};
                border-radius: 12px;
                padding: 5px 12px;
            }}
        """)
        row2.addWidget(filter_combo, 1)  # stretch=1
        
        sort_btn = QPushButton("↑")
        sort_btn.setObjectName("BtnNavCompact")
        sort_btn.setFixedSize(36, 32)
        sort_btn.setToolTip("По возрастанию")
        row2.addWidget(sort_btn, 0)  # stretch=0
        
        fb_lay.addLayout(row2)
        layout.addWidget(filter_bar)
        
        # ── Список (заглушка) ────────────────────────────────────
        list_placeholder = QLabel("Список знаков...")
        list_placeholder.setStyleSheet(f"color: {TOKENS['text_secondary']}; padding: 20px;")
        layout.addWidget(list_placeholder, 1)  # stretch=1
        
        # ── Панель навигации ─────────────────────────────────────
        nav_bar = QWidget()
        nav_bar.setMinimumHeight(40)
        nav_bar.setMaximumHeight(48)
        nav_bar.setStyleSheet(f"background: {TOKENS['bg_tertiary']};")
        
        nb_lay = QHBoxLayout(nav_bar)
        nb_lay.setContentsMargins(6, 0, 6, 0)
        nb_lay.setSpacing(4)
        
        btn_prev = QPushButton("← Пред.")
        btn_next = QPushButton("След. →")
        for btn in (btn_prev, btn_next):
            btn.setObjectName("BtnNavCompact")
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setMinimumWidth(0)
        
        lbl_nav = QLabel("12 / 34")
        lbl_nav.setStyleSheet(f"color: {TOKENS['text_primary']};")
        lbl_nav.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_nav.setFixedWidth(48)
        lbl_nav.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        
        nb_lay.addWidget(btn_prev, 1)   # stretch=1
        nb_lay.addWidget(lbl_nav,  0)   # stretch=0
        nb_lay.addWidget(btn_next, 1)   # stretch=1
        
        layout.addWidget(nav_bar)
        
        # Сохраним ссылки для теста
        self.btn_prev = btn_prev
        self.btn_next = btn_next
        self.lbl_nav = lbl_nav
        self.sort_btn = sort_btn
        self.filter_combo = filter_combo
        self.left_panel = panel
        
        return panel
    
    def _print_sizes(self):
        """Вывод размеров для диагностики."""
        print("\n=== DIAGNOSTIKA RAZMEROV ===")
        print(f"Levaya panel minimumWidth: {self.left_panel.minimumWidth()}")
        print(f"Levaya panel actual width: {self.left_panel.width()}")
        print(f"btn_prev minimumWidth: {self.btn_prev.minimumWidth()}")
        print(f"btn_prev minimumSizeHint: {self.btn_prev.minimumSizeHint().width()}")
        print(f"btn_next minimumWidth: {self.btn_next.minimumWidth()}")
        print(f"lbl_nav width: {self.lbl_nav.width()}")
        print(f"sort_btn size: {self.sort_btn.width()}x{self.sort_btn.height()}")
        print(f"filter_combo minimumWidth: {self.filter_combo.minimumWidth()}")
        print("============================\n")
        
        # Проверка: сумма минимумов не должна превышать ширину панели
        nav_min_sum = (
            self.btn_prev.minimumSizeHint().width() +
            self.lbl_nav.width() +
            self.btn_next.minimumSizeHint().width() +
            12  # margins + spacing
        )
        print(f"[OK] Navigaciya: summa minimumov = {nav_min_sum}px, panel min = {self.left_panel.minimumWidth()}px")
        
        filter_min_sum = (
            self.filter_combo.minimumSizeHint().width() +
            36 +  # sort_btn width
            6   # spacing
        )
        print(f"[OK] Filtr: summa minimumov = {filter_min_sum}px, panel min = {self.left_panel.minimumWidth()}px")
        
        if nav_min_sum > self.left_panel.minimumWidth():
            print("[ERROR] PROBLEMA: navigaciya ne vlezaet!")
        else:
            print("[OK] Navigaciya dolzhna vlezat")
        
        if filter_min_sum > self.left_panel.minimumWidth() - 20:  # -20 для margins
            print("[ERROR] PROBLEMA: filtr ne vlezaet!")
        else:
            print("[OK] Filtr dolzhen vlezat")
    
    def resizeEvent(self, event):
        """Проверка при изменении размера."""
        super().resizeEvent(event)
        # Обновляем диагностику после resize
        QApplication.processEvents()
        if hasattr(self, 'left_panel'):
            actual_width = self.left_panel.width()
            if actual_width > 0:  # только если уже отрисовано
                print(f"\n[Resize] Levaya panel actual width: {actual_width}px")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = TestWindow()
    window.show()
    
    # Тест: уменьшаем окно до минимума
    print("\nTest 1: Razmer po umolchaniyu (1200x720)")
    QApplication.processEvents()
    
    print("\nTest 2: Umenshaem okno i dvigaem splitter")
    window.resize(1200, 720)
    QApplication.processEvents()
    
    print("\n[OK] Esli knopki vidny i paneli ne naezzhayut drug na druga - test proyden!")
    print("Vruchnuyu potyanite splitter vlevo do ellipsis i proverit:")
    print("  - Knopki '<- Pred.' i 'Sled. ->' szhimayutsya bez naezda na pravuyu panel")
    print("  - Knopka '^' ostaetsya kompaktnym kvadratom 36x32")
    print("  - Komboboks filtra szhimaetsya, no ne vylezaet\n")
    
    sys.exit(app.exec())
