"""
Исправление: ограничить maxZoom для api.maps.by.
Сервер не поддерживает zoom > 18 для большинства областей.
"""
from PyQt6.QtCore import QSettings

print(f"\n{'='*70}")
print(f"  ИСПРАВЛЕНИЕ НАСТРОЕК КАРТЫ")
print(f"{'='*70}\n")

settings = QSettings("Signer", "RoadScanner")

# Текущие настройки
old_max_zoom = settings.value("map_tile_max_zoom", 19)
print(f"Текущий max_zoom: {old_max_zoom}\n")

# Устанавливаем правильный maxZoom для api.maps.by
# По документации и нашим тестам - максимум 18
settings.setValue("map_tile_max_zoom", 18)
settings.sync()

print(f"✅ Обновлено:")
print(f"   map_tile_max_zoom: 18\n")
print(f"{'─'*70}\n")
print(f"📋 Что изменилось:")
print(f"   - Максимальный zoom ограничен до 18")
print(f"   - Leaflet не будет пытаться загружать тайлы zoom=19, 20, и т.д.")
print(f"   - Меньше ошибок HTTP 500 от api.maps.by\n")
print(f"💡 Теперь перезапустите приложение или обновите страницу (F5)")
print(f"   и попробуйте приблизить карту. Стили должны отображаться.\n")
