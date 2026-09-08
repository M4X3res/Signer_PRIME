"""
BLOCK L: Современная светлая тема с теплой нейтральной палитрой
Акцент: глубокий индиго/океан (тематика: дороги и GPS)
"""

MODERN_LIGHT_TOKENS = {
    # === Backgrounds === #
    "bg_primary":       "#F9F8F5",      # Теплый приглушенный белый
    "bg_secondary":     "#F2F0EA",      # Карточки и панели
    "bg_tertiary":      "#EAE7DF",      # Инпуты и вторичные элементы
    "bg_elevated":      "#FFFFFF",      # Elevated элементы с тенью
    "bg_hover":         "#EDEAE2",      # Hover состояния
    "bg_active":        "#E1DDD2",      # Активные/pressed состояния
    "bg_accent_subtle": "#E7EEF5",      # Тонкий акцентный фон
    
    # === Borders === #
    "border_subtle":    "#EAE6DD",      # Едва заметные границы
    "border_default":   "#DAD4C7",      # Стандартные границы
    "border_strong":    "#B9B2A0",      # Выделенные границы
    "border_focus":     "#2F5D8A",      # Границы в фокусе
    
    # === Text === #
    "text_primary":     "#26241F",      # Основной текст (теплый черный)
    "text_secondary":   "#5C574C",      # Вторичный текст
    "text_tertiary":    "#847E70",      # Третичный текст
    "text_disabled":    "#B4AE9F",      # Отключенный текст
    "text_link":        "#2F5D8A",      # Ссылки
    "text_on_accent":   "#FFFFFF",      # Текст на акценте
    
    # === Accent Colors (глубокий индиго/океан) === #
    "accent":           "#2F5D8A",      # Основной акцент
    "accent_hover":     "#254A6E",      # Hover акцент
    "accent_pressed":   "#1C3A57",      # Pressed акцент
    "accent_subtle":    "#E7EEF5",      # Тонкий акцентный фон
    "accent_muted":     "#5F86A8",      # Приглушенный акцент
    
    # === Secondary Accent (теплый коричневый) === #
    "secondary_accent": "#8A6D4E",      # Вторичный акцент
    "secondary_hover":  "#735A3F",      # Hover вторичного
    
    # === Status Colors === #
    "success":          "#3F7D58",      # Зеленый (успех)
    "success_hover":    "#336548",      
    "success_bg":       "#E7F0EA",      # Фон успеха
    
    "warning":          "#B07A25",      # Оранжевый (предупреждение)
    "warning_hover":    "#8F6320",
    "warning_bg":       "#F5EBDA",      # Фон предупреждения
    
    "error":            "#B14A3E",      # Красный (ошибка)
    "error_hover":      "#a40e26",
    "error_bg":         "#ffebe9",      # Фон ошибки
    
    "info":             "#0969da",      # Синий (инфо)
    "info_hover":       "#0550ae",
    "info_bg":          "#ddf4ff",      # Фон инфо
    
    # === Sidebar === #
    "sidebar_bg":       "#24292f",      # Темный сайдбар (контраст)
    "sidebar_border":   "#373e47",
    "sidebar_item_active":   "#1f6feb",  # Активный элемент (синий)
    "sidebar_item_hover":    "#2d333b",  # Hover
    "sidebar_indicator":     "#1f6feb",  # Индикатор активного
    
    # === Special === #
    "shadow_sm":        "rgba(31, 35, 40, 0.04)",
    "shadow_md":        "rgba(31, 35, 40, 0.08)",
    "shadow_lg":        "rgba(31, 35, 40, 0.15)",
    "shadow_accent":    "rgba(9, 105, 218, 0.2)",
    
    # === Progress & Charts === #
    "progress_bg":      "#e5e7eb",
    "progress_fill":    "#0969da",

    # === Video Preview === #
    # Канвас видео/кадра осознанно остаётся тёмным в ОБЕИХ темах (как у
    # большинства видеоплееров) — но значение должно быть явно задано для
    # каждой темы, а не подразумеваться дефолтом '#000000' в коде.
    "video_bg":         "#0a0a0a",
    "video_controls":   "#1a1a1a",

    # === Scrollbar === #
    "scrollbar_bg":     "transparent",
    "scrollbar_handle": "#d1d5db",
    "scrollbar_hover":  "#9ca3af",
}
