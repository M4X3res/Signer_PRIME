"""
Переключение на OpenStreetMap (временное решение).
Меняет настройки карты на бесплатные растровые тайлы OSM.
"""
from PyQt6.QtCore import QSettings

print(f"\n{'='*70}")
print(f"  ПЕРЕКЛЮЧЕНИЕ НА OPENSTREETMAP")
print(f"{'='*70}\n")

settings = QSettings("Signer", "RoadScanner")

# Сохраняем текущие настройки для бэкапа
old_type = settings.value("map_tile_type", "raster")
old_url = settings.value("map_tile_url", "")
old_use_proxy = settings.value("map_tile_use_proxy", True)

print(f"Текущие настройки:")
print(f"  map_tile_type: {old_type}")
print(f"  map_tile_url: {old_url[:80]}...")
print(f"  map_tile_use_proxy: {old_use_proxy}\n")

# Устанавливаем OSM
settings.setValue("map_tile_type", "raster")
settings.setValue("map_tile_url", "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png")
settings.setValue("map_tile_attribution", "© OpenStreetMap contributors")
settings.setValue("map_tile_max_zoom", 19)
settings.setValue("map_tile_use_proxy", False)

settings.sync()

print(f"✅ Настройки обновлены:")
print(f"  map_tile_type: raster")
print(f"  map_tile_url: https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png")
print(f"  map_tile_attribution: © OpenStreetMap contributors")
print(f"  map_tile_max_zoom: 19")
print(f"  map_tile_use_proxy: False\n")

print(f"{'─'*70}\n")
print(f"🗺️  Теперь карта будет использовать бесплатные тайлы OpenStreetMap.")
print(f"   Запустите приложение и проверьте что карта отображается.\n")
print(f"⚠️  Для возврата к векторным тайлам api.maps.by:")
print(f"   1. Получите действительный API токен от провайдера")
print(f"   2. Откройте Настройки → Карта в приложении")
print(f"   3. Установите правильный URL с токеном\n")

# Показываем пример правильного URL
print(f"📝 Пример правильного URL для api.maps.by:")
print(f"   https://api.maps.by/api/vectorTile/VectorTileServer/tile/{{z}}/{{y}}/{{x}}.pbf?token=YOUR_ACTUAL_TOKEN")
print(f"\n   где YOUR_ACTUAL_TOKEN - это строка без символа '*' и без префикса '$2a$10$'\n")
