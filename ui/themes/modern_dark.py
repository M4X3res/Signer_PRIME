"""
Современная темная тема с улучшенной цветовой палитрой
Вдохновлена: VSCode Dark+, GitHub Dark, Arc Theme
"""

MODERN_DARK_TOKENS = {
    # === Backgrounds === #
    "bg_primary":       "#0d1117",      # Глубокий темный фон
    "bg_secondary":     "#161b22",      # Карточки и панели
    "bg_tertiary":      "#1c2128",      # Инпуты и вторичные элементы
    "bg_elevated":      "#22272e",      # Elevated элементы (модалы, dropdown)
    "bg_hover":         "#2d333b",      # Hover состояния
    "bg_active":        "#373e47",      # Активные/pressed состояния
    "bg_accent_subtle": "#1a2332",      # Тонкий акцентный фон
    
    # === Borders === #
    "border_subtle":    "#21262d",      # Едва заметные границы
    "border_default":   "#30363d",      # Стандартные границы
    "border_strong":    "#444c56",      # Выделенные границы
    "border_focus":     "#388bfd",      # Границы в фокусе
    
    # === Text === #
    "text_primary":     "#e6edf3",      # Основной текст
    "text_secondary":   "#8b949e",      # Вторичный текст
    "text_tertiary":    "#6e7681",      # Третичный текст
    "text_disabled":    "#484f58",      # Отключенный текст
    "text_link":        "#58a6ff",      # Ссылки
    "text_on_accent":   "#ffffff",      # Текст на акценте
    
    # === Accent Colors === #
    "accent":           "#2f81f7",      # Основной акцент (синий)
    "accent_hover":     "#4493ff",      # Hover акцент
    "accent_pressed":   "#1e6ed6",      # Pressed акцент
    "accent_subtle":    "#1a2d4d",      # Тонкий акцентный фон
    "accent_muted":     "#1f6feb",      # Приглушенный акцент
    
    # === Secondary Accent (Фиолетовый для разнообразия) === #
    "secondary_accent": "#8957e5",      # Вторичный акцент
    "secondary_hover":  "#9d6bfb",      # Hover вторичного
    
    # === Status Colors === #
    "success":          "#3fb950",      # Зеленый (успех)
    "success_hover":    "#4ac65f",      
    "success_bg":       "#0f2417",      # Фон успеха
    
    "warning":          "#d29922",      # Оранжевый (предупреждение)
    "warning_hover":    "#e5a835",
    "warning_bg":       "#2c2212",      # Фон предупреждения
    
    "error":            "#f85149",      # Красный (ошибка)
    "error_hover":      "#ff6b68",
    "error_bg":         "#2e1517",      # Фон ошибки
    
    "info":             "#388bfd",      # Синий (инфо)
    "info_hover":       "#4da3ff",
    "info_bg":          "#0c1929",      # Фон инфо
    
    # === Sidebar === #
    "sidebar_bg":       "#010409",      # Почти черный
    "sidebar_border":   "#1c2128",
    "sidebar_item_active":   "#1a2d4d",  # Активный элемент
    "sidebar_item_hover":    "#161b22",  # Hover
    "sidebar_indicator":     "#2f81f7",  # Индикатор активного
    
    # === Special === #
    "shadow_sm":        "rgba(1, 4, 9, 0.15)",
    "shadow_md":        "rgba(1, 4, 9, 0.3)",
    "shadow_lg":        "rgba(1, 4, 9, 0.5)",
    "shadow_accent":    "rgba(47, 129, 247, 0.3)",
    
    # === Progress & Charts === #
    "progress_bg":      "#21262d",
    "progress_fill":    "#2f81f7",
    
    # === Video Preview === #
    "video_bg":         "#000000",
    "video_controls":   "#0d1117",
    
    # === Scrollbar === #
    "scrollbar_bg":     "transparent",
    "scrollbar_handle": "#484f58",
    "scrollbar_hover":  "#6e7681",
}
