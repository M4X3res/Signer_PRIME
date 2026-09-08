"""
Современные QSS стили для RoadScanner
С поддержкой анимаций, shadows, и улучшенной типографики
"""


def build_modern_qss(t: dict) -> str:
    """
    Генерирует современный QSS с улучшенным дизайном
    
    Args:
        t: словарь токенов темы (MODERN_DARK_TOKENS или MODERN_LIGHT_TOKENS)
    
    Returns:
        str: готовый QSS stylesheet
    """
    
    # Проверяем наличие теней (только в современных темах)
    has_shadows = 'shadow_sm' in t
    
    # Определяем является ли тема темной
    is_dark = t.get('bg_primary', '#000') < '#888888'
    
    return f"""
/* ═══════════════════════════════════════════════════════════════════
   MODERN ROADSCANNER THEME
   ═══════════════════════════════════════════════════════════════════ */

/* ── Root & Base ─────────────────────────────────────────────────── */
QMainWindow, QDialog, QWidget {{
    background-color: {t['bg_primary']};
    color: {t['text_primary']};
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "SF Pro Display", "Helvetica Neue", "Inter", sans-serif;
    font-size: 13px;
    font-weight: 400;
}}

* {{
    outline: none;
}}

/* ── Sidebar ────────────────────────────────────────────────────── */
#Sidebar {{
    background-color: {t['sidebar_bg']};
    border-right: 1px solid {t['sidebar_border']};
    padding: 16px 12px;
}}

#SidebarItem {{
    background: transparent;
    border: none;
    border-radius: 8px;
    color: {t['text_secondary']};
    padding: 12px 16px;
    text-align: left;
    font-size: 13px;
    font-weight: 500;
    letter-spacing: 0.2px;
    margin: 2px 0px;
}}

#SidebarItem:hover {{
    background-color: {t['sidebar_item_hover']};
    color: {t['text_primary']};
}}

#SidebarItem[active="true"] {{
    background-color: {t['sidebar_item_active']};
    color: {t['accent']};
    font-weight: 600;
    position: relative;
}}

/* Индикатор активного элемента */
#SidebarItem[active="true"]::before {{
    content: '';
    width: 3px;
    height: 100%;
    background-color: {t.get('sidebar_indicator', t['accent'])};
    position: absolute;
    left: 0;
    border-radius: 0px 2px 2px 0px;
}}

#SidebarLogo {{
    color: {t['text_primary']};
    font-size: 16px;
    font-weight: 700;
    letter-spacing: 0.5px;
    padding: 8px 0px;
    background: transparent;
    border: none;
}}

#SidebarVersion {{
    color: {t['text_tertiary']};
    font-size: 10px;
    font-weight: 500;
    background: transparent;
    letter-spacing: 0.5px;
}}

#SidebarDivider {{
    background-color: {t['border_subtle']};
    height: 1px;
    margin: 12px 0px;
}}

/* ── Content Area ───────────────────────────────────────────────── */
#ContentArea {{
    background-color: {t['bg_primary']};
}}

#PageTitle {{
    color: {t['text_primary']};
    font-size: 24px;
    font-weight: 600;
    letter-spacing: -0.5px;
    line-height: 1.3;
}}

#PageSubtitle {{
    color: {t['text_secondary']};
    font-size: 14px;
    font-weight: 400;
    line-height: 1.5;
    letter-spacing: 0.1px;
}}

/* ── Labels with text wrapping ──────────────────────────────────── */
QLabel {{
    line-height: 1.4;
}}

#SettingsLabel {{
    color: {t['text_primary']};
    font-size: 14px;
    font-weight: 500;
    background: transparent;
    line-height: 1.5;
}}

#SettingsHint {{
    color: {t['text_tertiary']};
    font-size: 12px;
    background: transparent;
    line-height: 1.5;
}}

/* ── Cards ──────────────────────────────────────────────────────── */
#Card {{
    background-color: {t['bg_secondary']};
    border: 1px solid {t['border_default']};
    border-radius: 12px;
}}

#CardElevated {{
    background-color: {t['bg_elevated']};
    border: 1px solid {t['border_default']};
    border-radius: 12px;
}}

#CardTitle {{
    color: {t['text_tertiary']};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    background: transparent;
}}

#CardSubtitle {{
    color: {t['text_secondary']};
    font-size: 12px;
    font-weight: 400;
    background: transparent;
}}

/* ── Buttons ────────────────────────────────────────────────────── */
#BtnPrimary {{
    background-color: {t['accent']};
    color: {t['text_on_accent']};
    border: none;
    border-radius: 8px;
    padding: 10px 24px;
    font-size: 14px;
    font-weight: 600;
    min-width: 120px;
    min-height: 36px;
    letter-spacing: 0.2px;
}}

#BtnPrimary:hover {{
    background-color: {t['accent_hover']};
}}

#BtnPrimary:pressed {{
    background-color: {t['accent_pressed']};
}}

#BtnPrimary:disabled {{
    background-color: {t['bg_tertiary']};
    color: {t['text_secondary']};
    border: 1.5px solid {t['border_strong']};
}}

#BtnSecondary {{
    background-color: transparent;
    color: {t['text_primary']};
    border: 1.5px solid {t['border_default']};
    border-radius: 8px;
    padding: 10px 24px;
    font-size: 14px;
    font-weight: 500;
    min-width: 120px;
    min-height: 36px;
}}

#BtnSecondary:hover {{
    background-color: {t['bg_hover']};
    border-color: {t['border_strong']};
}}

#BtnSecondary:pressed {{
    background-color: {t['bg_active']};
    border-color: {t['accent']};
}}

#BtnSecondary:disabled {{
    color: {t['text_disabled']};
    border-color: {t['border_subtle']};
}}

#BtnDanger {{
    background-color: transparent;
    color: {t['error']};
    border: 1.5px solid {t['error']};
    border-radius: 8px;
    padding: 8px 20px;
    font-size: 13px;
    font-weight: 600;
}}

#BtnDanger:hover {{
    background-color: {t['error']};
    color: {t['text_on_accent']};
}}

#BtnDanger:pressed {{
    background-color: {t['error_hover']};
}}

#BtnSuccess {{
    background-color: {t['success']};
    color: {t['text_on_accent']};
    border: none;
    border-radius: 8px;
    padding: 10px 24px;
    font-size: 14px;
    font-weight: 600;
}}

#BtnSuccess:hover {{
    background-color: {t['success_hover']};
}}

#BtnIcon {{
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 8px;
    color: {t['text_secondary']};
}}

#BtnIcon:hover {{
    background-color: {t['bg_hover']};
    color: {t['text_primary']};
}}

#BtnIcon:pressed {{
    background-color: {t['bg_active']};
}}

/* ── File Path Widget ───────────────────────────────────────────── */
#FilePathBox {{
    background-color: {t['bg_tertiary']};
    border: 1px solid {t['border_default']};
    border-radius: 8px;
    padding: 10px 14px;
    color: {t['text_secondary']};
    font-size: 12px;
    font-family: "SF Mono", "Monaco", "Cascadia Code", "JetBrains Mono", "Consolas", monospace;
    font-weight: 400;
}}

#FileLabel {{
    color: {t['text_secondary']};
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.5px;
    background: transparent;
}}

#FilePlaceholder {{
    color: {t['text_tertiary']};
    font-size: 12px;
    font-style: italic;
    background: transparent;
}}

/* ── Progress Bar ───────────────────────────────────────────────── */
QProgressBar {{
    background-color: {t.get('progress_bg', t['bg_tertiary'])};
    border: none;
    border-radius: 4px;
    height: 6px;
    text-align: center;
    color: transparent;
}}

QProgressBar::chunk {{
    background-color: {t.get('progress_fill', t['accent'])};
    border-radius: 4px;
}}

/* ── Log Console ────────────────────────────────────────────────── */
#LogConsole {{
    background-color: {t['bg_tertiary']};
    border: 1px solid {t['border_default']};
    border-radius: 10px;
    color: {t['text_secondary']};
    font-family: "SF Mono", "Monaco", "Cascadia Code", "JetBrains Mono", "Consolas", monospace;
    font-size: 12px;
    padding: 12px;
    selection-background-color: {t['accent_subtle']};
    line-height: 1.6;
}}

/* ── Input Fields ───────────────────────────────────────────────── */
QLineEdit, QSpinBox, QDoubleSpinBox {{
    background-color: {t['bg_tertiary']};
    border: 1.5px solid {t['border_default']};
    border-radius: 8px;
    padding: 8px 12px;
    color: {t['text_primary']};
    font-size: 14px;
    selection-background-color: {t['accent_subtle']};
}}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {t.get('border_focus', t['accent'])};
    background-color: {t['bg_secondary']};
}}

QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    background-color: {t['bg_hover']};
    color: {t['text_disabled']};
    border-color: {t['border_subtle']};
}}

/* ── ComboBox ───────────────────────────────────────────────────── */
QComboBox {{
    background-color: {t['bg_tertiary']};
    border: 1.5px solid {t['border_default']};
    border-radius: 8px;
    padding: 8px 12px;
    color: {t['text_primary']};
    font-size: 14px;
    min-height: 20px;
}}

QComboBox:hover {{
    border-color: {t['border_strong']};
}}

QComboBox:focus {{
    border-color: {t.get('border_focus', t['accent'])};
}}

QComboBox::drop-down {{
    border: none;
    width: 30px;
    padding-right: 8px;
}}

QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {t['text_secondary']};
    margin-right: 8px;
}}

QComboBox QAbstractItemView {{
    background-color: {t['bg_elevated']};
    border: 1px solid {t['border_default']};
    selection-background-color: {t['accent_subtle']};
    selection-color: {t['accent']};
    color: {t['text_primary']};
    border-radius: 8px;
    padding: 4px;
    outline: none;
}}

QComboBox QAbstractItemView::item {{
    min-height: 32px;
    padding: 6px 12px;
    border-radius: 6px;
}}

QComboBox QAbstractItemView::item:hover {{
    background-color: {t['bg_hover']};
}}

QComboBox QAbstractItemView::item:selected {{
    background-color: {t['accent_subtle']};
    color: {t['accent']};
}}

""" + _build_modern_qss_part2(t)


def _build_modern_qss_part2(t: dict) -> str:
    """Вторая часть QSS стилей"""
    return f"""
/* ── CheckBox ───────────────────────────────────────────────────── */
QCheckBox {{
    color: {t['text_primary']};
    spacing: 10px;
    font-size: 14px;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 1.5px solid {t['border_default']};
    background: {t['bg_tertiary']};
}}

QCheckBox::indicator:hover {{
    border-color: {t['border_strong']};
    background: {t['bg_hover']};
}}

QCheckBox::indicator:checked {{
    background: {t['accent']};
    border-color: {t['accent']};
    image: none;
}}

QCheckBox::indicator:checked::after {{
    content: '✓';
    color: {t['text_on_accent']};
    font-weight: bold;
}}

QCheckBox:disabled {{
    color: {t['text_disabled']};
}}

QCheckBox::indicator:disabled {{
    background: {t['bg_hover']};
    border-color: {t['border_subtle']};
}}

/* ── RadioButton ────────────────────────────────────────────────── */
QRadioButton {{
    color: {t['text_primary']};
    spacing: 10px;
    font-size: 14px;
}}

QRadioButton::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 9px;
    border: 1.5px solid {t['border_default']};
    background: {t['bg_tertiary']};
}}

QRadioButton::indicator:hover {{
    border-color: {t['border_strong']};
}}

QRadioButton::indicator:checked {{
    background: {t['accent']};
    border-color: {t['accent']};
}}

QRadioButton::indicator:checked::after {{
    width: 8px;
    height: 8px;
    border-radius: 4px;
    background: {t['text_on_accent']};
}}

/* ── Scrollbar ──────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: {t.get('scrollbar_bg', 'transparent')};
    width: 8px;
    margin: 0;
    border-radius: 4px;
}}

QScrollBar::handle:vertical {{
    background: {t.get('scrollbar_handle', t['border_strong'])};
    border-radius: 4px;
    min-height: 40px;
}}

QScrollBar::handle:vertical:hover {{
    background: {t.get('scrollbar_hover', t['text_tertiary'])};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
    border: none;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}

QScrollBar:horizontal {{
    background: {t.get('scrollbar_bg', 'transparent')};
    height: 8px;
    border-radius: 4px;
}}

QScrollBar::handle:horizontal {{
    background: {t.get('scrollbar_handle', t['border_strong'])};
    border-radius: 4px;
    min-width: 40px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {t.get('scrollbar_hover', t['text_tertiary'])};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
    border: none;
}}

QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: transparent;
}}

/* ── Separator ──────────────────────────────────────────────────── */
#Separator {{
    background-color: {t['border_subtle']};
    border: none;
}}

QFrame[frameShape="4"], QFrame[frameShape="5"] {{  /* HLine, VLine */
    background-color: {t['border_subtle']};
    border: none;
}}

/* ── Status Bar ─────────────────────────────────────────────────── */
#StatusBar {{
    background-color: {t['bg_secondary']};
    border-top: 1px solid {t['border_subtle']};
    color: {t['text_tertiary']};
    font-size: 12px;
    padding: 0 16px;
}}

#StatusDot {{
    background: transparent;
    border: none;
    font-size: 10px;
    padding: 0;
}}

/* ── Settings ───────────────────────────────────────────────────── */
#SettingsGroup {{
    background-color: {t['bg_secondary']};
    border: 1px solid {t['border_default']};
    border-radius: 12px;
    padding: 16px;
}}

#SettingsLabel {{
    color: {t['text_primary']};
    font-size: 14px;
    font-weight: 500;
    background: transparent;
    line-height: 1.5;
}}

#SettingsHint {{
    color: {t['text_tertiary']};
    font-size: 12px;
    background: transparent;
    line-height: 1.5;
}}

/* ── Toggle Switch ──────────────────────────────────────────────── */
#ToggleSwitch {{
    background-color: {t['bg_hover']};
    border: 1.5px solid {t['border_default']};
    border-radius: 12px;
    min-width: 48px;
    max-width: 48px;
    min-height: 24px;
    max-height: 24px;
}}

#ToggleSwitch:hover {{
    background-color: {t['bg_active']};
}}

#ToggleSwitch[checked="true"] {{
    background-color: {t['accent']};
    border-color: {t['accent']};
}}

#ToggleSwitch[checked="true"]:hover {{
    background-color: {t['accent_hover']};
}}

/* ── Stats Display ──────────────────────────────────────────────── */
#StatValue {{
    color: {t['text_primary']};
    font-size: 32px;
    font-weight: 300;
    letter-spacing: -1px;
    background: transparent;
    line-height: 1.2;
}}

#StatLabel {{
    color: {t['text_tertiary']};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    background: transparent;
    line-height: 1.4;
}}

#AccentLine {{
    background-color: {t['accent']};
    border-radius: 2px;
    border: none;
}}

#SuccessLine {{
    background-color: {t['success']};
    border-radius: 2px;
    border: none;
}}

#WarningLine {{
    background-color: {t['warning']};
    border-radius: 2px;
    border: none;
}}

#ErrorLine {{
    background-color: {t['error']};
    border-radius: 2px;
    border: none;
}}

/* ── Section Labels ─────────────────────────────────────────────── */
#SectionLabel {{
    color: {t['text_tertiary']};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    background: transparent;
}}

#SectionDivider {{
    background-color: {t['border_subtle']};
    height: 1px;
}}

/* ── Tooltips ───────────────────────────────────────────────────── */
QToolTip {{
    background-color: {t['bg_elevated']};
    color: {t['text_primary']};
    border: 1px solid {t['border_default']};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}}

/* ── Menu ───────────────────────────────────────────────────────── */
QMenu {{
    background-color: {t['bg_elevated']};
    border: 1px solid {t['border_default']};
    border-radius: 8px;
    padding: 6px;
}}

QMenu::item {{
    padding: 8px 16px;
    border-radius: 6px;
    color: {t['text_primary']};
}}

QMenu::item:selected {{
    background-color: {t['accent_subtle']};
    color: {t['accent']};
}}

QMenu::separator {{
    height: 1px;
    background: {t['border_subtle']};
    margin: 4px 8px;
}}

/* ── Table ──────────────────────────────────────────────────────── */
QTableWidget {{
    background-color: {t['bg_secondary']};
    border: 1px solid {t['border_default']};
    border-radius: 8px;
    gridline-color: {t['border_subtle']};
    color: {t['text_primary']};
}}

QTableWidget::item {{
    padding: 8px;
    border-bottom: 1px solid {t['border_subtle']};
}}

QTableWidget::item:selected {{
    background-color: {t['accent_subtle']};
    color: {t['accent']};
}}

QHeaderView::section {{
    background-color: {t['bg_tertiary']};
    color: {t['text_secondary']};
    padding: 10px;
    border: none;
    border-bottom: 1px solid {t['border_default']};
    font-weight: 600;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}

/* ── Slider ─────────────────────────────────────────────────────── */
QSlider::groove:horizontal {{
    background: {t['bg_tertiary']};
    height: 4px;
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    background: {t['accent']};
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}}

QSlider::handle:horizontal:hover {{
    background: {t['accent_hover']};
}}

QSlider::sub-page:horizontal {{
    background: {t['accent']};
    border-radius: 2px;
}}

/* ── Badge / Tag ────────────────────────────────────────────────── */
#Badge {{
    background-color: {t['accent_subtle']};
    color: {t['accent']};
    border-radius: 12px;
    padding: 4px 12px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.3px;
}}

#BadgeSuccess {{
    background-color: {t.get('success_bg', t['bg_tertiary'])};
    color: {t['success']};
    border-radius: 12px;
    padding: 4px 12px;
    font-size: 11px;
    font-weight: 600;
}}

#BadgeWarning {{
    background-color: {t.get('warning_bg', t['bg_tertiary'])};
    color: {t['warning']};
    border-radius: 12px;
    padding: 4px 12px;
    font-size: 11px;
    font-weight: 600;
}}

#BadgeError {{
    background-color: {t.get('error_bg', t['bg_tertiary'])};
    color: {t['error']};
    border-radius: 12px;
    padding: 4px 12px;
    font-size: 11px;
    font-weight: 600;
}}

/* ── Video Preview ──────────────────────────────────────────────── */
#VideoLabel {{
    background-color: {t.get('video_bg', '#0a0a0a')};
    /* Текст поверх видео-канваса — намеренно НЕ зависит от темы
       приложения (канвас всегда тёмный), поэтому это литерал, а не
       токен из t[...]. Не переводи это в токен из соображений
       «единообразия» — тогда в светлой теме текст станет
       нечитаемым на тёмном фоне. */
    color: #9aa4af;
    border-radius: 8px;
    border: 1px solid {t['border_default']};
}}

/* ── Preview headers (переиспользуются в Processing и Error Editor) ── */
#PreviewHeader {{
    background-color: {t['bg_tertiary']};
    border-radius: 8px 8px 0px 0px;
}}

#PreviewFrameInfo {{
    color: {t['text_tertiary']};
    font-size: 10px;
    background: transparent;
}}

#PreviewEta {{
    color: {t['text_tertiary']};
    font-size: 11px;
    background: transparent;
}}

#ProgressPercent {{
    color: {t['text_primary']};
    font-size: 32px;
    font-weight: 200;
    letter-spacing: -1px;
    background: transparent;
}}

#MiniStatValue {{
    color: {t['text_primary']};
    font-size: 18px;
    font-weight: 300;
    background: transparent;
}}

#MiniStatLabel {{
    color: {t['text_tertiary']};
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.8px;
    background: transparent;
}}

#ClearLogBtn {{
    color: {t['text_tertiary']};
    font-size: 10px;
    background: transparent;
    border: none;
    text-decoration: underline;
}}

/* ── Error Editor ─────────────────────────────────────────────────── */
#EditorTopbar {{
    background-color: {t['bg_secondary']};
    border-bottom: 1px solid {t['border_subtle']};
}}

#EditorFilterBar {{
    background-color: {t['bg_tertiary']};
    border-bottom: 1px solid {t['border_subtle']};
}}

#EditorNavBar {{
    background-color: {t['bg_tertiary']};
    border-top: 1px solid {t['border_subtle']};
}}

#EditorNavLabel {{
    color: {t['text_tertiary']};
    font-size: 11px;
    background: transparent;
}}

#SignListView {{
    background: {t['bg_secondary']};
    border: none;
}}
#SignListView::item:selected {{
    background: {t['accent_subtle']};
}}

#MetaValueBig {{
    color: {t['text_primary']};
    font-size: 20px;
    font-weight: 300;
    background: transparent;
}}

#MetaValue {{
    color: {t['text_primary']};
    font-size: 12px;
    font-weight: 400;
    background: transparent;
}}

/* ── Special Effects (если поддерживается) ───────────────────────── */
#CardWithShadow {{
    background-color: {t['bg_elevated']};
    border: 1px solid {t['border_subtle']};
    border-radius: 12px;
}}

"""
