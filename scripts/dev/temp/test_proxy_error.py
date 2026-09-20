"""
Тест прокси векторных тайлов - смотрим точную ошибку.
"""
from configs.settings import get_app_settings

settings = get_app_settings()

print(f"\n{'='*70}")
print(f"  ТЕСТ ПРОКСИ ВЕКТОРНЫХ ТАЙЛОВ")
print(f"{'='*70}\n")

print(f"Текущие настройки:")
print(f"  map_tile_type: {settings.map_tile_type}")
print(f"  map_tile_url: {settings.map_tile_url}")
print(f"  map_tile_use_proxy: {settings.map_tile_use_proxy}")

# Импортируем функцию построения URL
from server.map_server import _build_upstream_tile_url, _mask_token_for_log

# Тестовые координаты из лога
z, x, y = 20, 604567, 337149

print(f"\n{'─'*70}")
print(f"  Попытка построить URL для тайла z={z}, x={x}, y={y}")
print(f"{'─'*70}\n")

try:
    upstream_url = _build_upstream_tile_url(settings.map_tile_url, z, x, y)
    masked = _mask_token_for_log(upstream_url)
    print(f"✅ URL построен успешно:")
    print(f"   {masked}\n")
    
    # Пробуем сделать запрос
    print(f"Пробуем загрузить тайл...")
    import requests
    
    response = requests.get(upstream_url, timeout=10)
    print(f"   HTTP Status: {response.status_code}")
    print(f"   Content-Type: {response.headers.get('Content-Type', 'N/A')}")
    print(f"   Content-Length: {len(response.content)} bytes")
    
    if response.status_code == 200:
        print(f"\n✅ Тайл загружен успешно!")
        print(f"\nПроблема НЕ в upstream-сервере, а в обработке в прокси.")
    else:
        print(f"\n❌ Ошибка от upstream-сервера: HTTP {response.status_code}")
        print(f"   Первые 200 символов ответа:")
        print(f"   {response.text[:200]}")

except ValueError as e:
    print(f"❌ ОШИБКА ВАЛИДАЦИИ URL:")
    print(f"   {e}\n")
    print(f"Решение:")
    print(f"  1. Откройте настройки приложения")
    print(f"  2. Перейдите в раздел 'Карта'")
    print(f"  3. Убедитесь что URL содержит плейсхолдеры {{z}}/{{x}}/{{y}}")
    print(f"  4. Пример правильного URL:")
    print(f"     https://api.maps.by/.../tile/{{z}}/{{y}}/{{x}}.pbf?token=YOUR_TOKEN")

except Exception as e:
    print(f"❌ ОШИБКА: {e}")
    import traceback
    traceback.print_exc()
