"""
Скрипт для проверки доступности векторных тайлов и стилей.
Проверяет текущую сохранённую ссылку из настроек приложения.
"""
import sys
import requests
import json
import re
from configs.settings import get_app_settings


def mask_token(url: str) -> str:
    """Маскирует токен в URL для безопасного вывода."""
    def mask_match(match):
        token_value = match.group(1)
        if len(token_value) <= 4:
            return f"token=****"
        return f"token=****{token_value[-3:]}"
    return re.sub(r'token=([^&\s]+)', mask_match, url)


def check_tile_url(tile_url: str) -> dict:
    """
    Проверяет доступность тайла.
    Returns: dict с результатом проверки
    """
    print(f"\n{'='*70}")
    print(f"  ПРОВЕРКА ДОСТУПНОСТИ ТАЙЛА")
    print(f"{'='*70}")
    
    # Подставляем тестовые координаты (Минск, zoom 9)
    test_url = (
        tile_url
        .replace("{z}", "9")
        .replace("{x}", "291")
        .replace("{y}", "163")
        .replace("{s}", "a")
    )
    
    # Проверяем что плейсхолдеры были заменены
    if test_url == tile_url:
        return {
            "success": False,
            "error": "URL не содержит плейсхолдеров {z}/{x}/{y}",
            "details": "Template должен выглядеть как: https://api.maps.by/.../tile/{z}/{y}/{x}.pbf?token=...",
        }
    
    print(f"\n📍 Test URL: {mask_token(test_url)}")
    print(f"   Координаты: z=9, x=291, y=163 (Минск)")
    
    try:
        print(f"\n⏳ Отправка запроса...")
        response = requests.get(test_url, timeout=10)
        
        print(f"   HTTP Status: {response.status_code}")
        print(f"   Content-Type: {response.headers.get('Content-Type', 'N/A')}")
        print(f"   Content-Length: {len(response.content)} bytes")
        
        if response.status_code == 200:
            # Проверяем что это protobuf (векторный тайл)
            content_type = response.headers.get('Content-Type', '')
            is_protobuf = (
                'protobuf' in content_type.lower() or
                'pbf' in content_type.lower() or
                response.content[:2] == b'\x1a\x00'  # Protobuf magic bytes
            )
            
            if is_protobuf:
                print(f"   ✅ Тайл загружен успешно (Protobuf)")
                return {"success": True, "size": len(response.content)}
            else:
                print(f"   ⚠️  Ответ получен, но Content-Type не похож на Protobuf")
                print(f"   Первые 100 байт: {response.content[:100]}")
                return {
                    "success": False,
                    "error": f"Invalid Content-Type: {content_type}",
                    "details": "Ожидается application/x-protobuf или application/vnd.mapbox-vector-tile"
                }
        else:
            print(f"   ❌ HTTP {response.status_code}")
            return {
                "success": False,
                "error": f"HTTP {response.status_code}",
                "details": response.text[:200] if hasattr(response, 'text') else str(response.content[:200])
            }
    
    except requests.exceptions.Timeout:
        print(f"   ❌ Timeout (10s)")
        return {"success": False, "error": "Timeout после 10 секунд"}
    
    except requests.exceptions.RequestException as e:
        print(f"   ❌ Request Error: {e}")
        return {"success": False, "error": str(e)}


def check_styles(tile_url: str) -> dict:
    """
    Проверяет доступность стилей для векторного тайл-сервера.
    Returns: dict с результатом проверки
    """
    print(f"\n{'='*70}")
    print(f"  ПРОВЕРКА ДОСТУПНОСТИ СТИЛЕЙ")
    print(f"{'='*70}")
    
    # Извлекаем query string (токен)
    query_string = ''
    if '?' in tile_url:
        query_string = '?' + tile_url.split('?', 1)[1]
    
    # Формируем возможные URL стилей
    style_paths = []
    
    # Вариант 1: api.maps.by - убираем /VectorTileServer/tile/ и добавляем /resources/styles
    if '/VectorTileServer/tile/' in tile_url:
        base_url = tile_url.split('/VectorTileServer/tile/')[0]
        style_paths.append(f"{base_url}/resources/styles{query_string}")
        style_paths.append(f"{base_url}/VectorTileServer/resources/styles{query_string}")
    # Вариант 2: Общий случай /tile/
    elif '/tile/' in tile_url:
        base_url = tile_url.split('/tile/')[0]
        style_paths.append(f"{base_url}/resources/styles{query_string}")
        style_paths.append(f"{base_url}/resources/styles/root.json{query_string}")
        style_paths.append(f"{base_url}/styles/root.json{query_string}")
        style_paths.append(f"{base_url}/style.json{query_string}")
    else:
        return {
            "success": False,
            "error": "Не удалось определить базовый URL для стилей",
            "details": "URL должен содержать /tile/ или /VectorTileServer/tile/"
        }
    
    print(f"\n🎨 Проверка {len(style_paths)} возможных путей к стилям...")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json, */*'
    }
    
    for idx, style_url in enumerate(style_paths, 1):
        masked = mask_token(style_url)
        print(f"\n   [{idx}/{len(style_paths)}] {masked}")
        
        try:
            response = requests.get(style_url, timeout=10, headers=headers)
            print(f"      HTTP Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    
                    # Проверяем структуру стилей
                    has_layers = 'layers' in data
                    has_sources = 'sources' in data
                    has_version = 'version' in data
                    
                    print(f"      Content-Type: {response.headers.get('Content-Type', 'N/A')}")
                    print(f"      Size: {len(response.content)} bytes")
                    print(f"      Structure: layers={has_layers}, sources={has_sources}, version={has_version}")
                    
                    if isinstance(data, dict) and (has_layers or has_sources or has_version):
                        print(f"      ✅ Стили найдены!")
                        print(f"      Keys: {list(data.keys())[:10]}")
                        
                        # Выводим детали стилей
                        if has_sources:
                            print(f"\n      📦 Sources:")
                            for source_id, source in list(data.get('sources', {}).items())[:3]:
                                print(f"         - {source_id}: {source.get('type', 'unknown')}")
                                if 'url' in source:
                                    print(f"           URL: {mask_token(source['url'][:100])}")
                        
                        if has_layers:
                            layer_count = len(data.get('layers', []))
                            print(f"\n      🎨 Layers: {layer_count} слоёв")
                            for layer in data.get('layers', [])[:3]:
                                print(f"         - {layer.get('id', 'unknown')}: {layer.get('type', 'unknown')}")
                        
                        return {
                            "success": True,
                            "url": masked,
                            "layers_count": len(data.get('layers', [])),
                            "sources_count": len(data.get('sources', {})),
                        }
                    else:
                        print(f"      ⚠️  JSON получен, но структура не похожа на стили")
                
                except json.JSONDecodeError as e:
                    print(f"      ⚠️  Не удалось распарсить JSON: {e}")
                    print(f"      Preview: {response.text[:200]}")
            
            elif response.status_code == 404:
                print(f"      ❌ 404 Not Found")
            else:
                print(f"      ❌ HTTP {response.status_code}")
        
        except requests.exceptions.Timeout:
            print(f"      ❌ Timeout")
        except requests.exceptions.RequestException as e:
            print(f"      ❌ Error: {e}")
    
    return {
        "success": False,
        "error": "Стили не найдены ни по одному из путей",
        "tried_count": len(style_paths)
    }


def main():
    print(f"\n{'#'*70}")
    print(f"  🗺️  ПРОВЕРКА ВЕКТОРНЫХ ТАЙЛОВ И СТИЛЕЙ")
    print(f"{'#'*70}")
    
    # Загружаем настройки
    try:
        settings = get_app_settings()
    except Exception as e:
        print(f"\n❌ Ошибка загрузки настроек: {e}")
        sys.exit(1)
    
    print(f"\n📋 Текущие настройки карты:")
    print(f"   Tile Type: {settings.map_tile_type}")
    print(f"   Tile URL: {mask_token(settings.map_tile_url)}")
    print(f"   Max Zoom: {settings.map_tile_max_zoom}")
    print(f"   Use Proxy: {settings.map_tile_use_proxy}")
    print(f"   Attribution: {settings.map_tile_attribution[:50]}...")
    
    # Проверяем тип тайлов
    if settings.map_tile_type != "vector":
        print(f"\n⚠️  ВНИМАНИЕ: Текущий тип тайлов = '{settings.map_tile_type}'")
        print(f"   Для проверки векторных тайлов переключите map_tile_type на 'vector'")
        print(f"\n   Можно проверить доступность растрового тайла:")
        
        # Всё равно проверяем URL
        tile_result = check_tile_url(settings.map_tile_url)
        
        if tile_result["success"]:
            print(f"\n✅ РЕЗУЛЬТАТ: Растровый тайл доступен")
        else:
            print(f"\n❌ РЕЗУЛЬТАТ: Растровый тайл недоступен")
            print(f"   Error: {tile_result.get('error', 'Unknown error')}")
        
        sys.exit(0 if tile_result["success"] else 1)
    
    # Проверяем векторные тайлы
    tile_result = check_tile_url(settings.map_tile_url)
    
    if not tile_result["success"]:
        print(f"\n❌ РЕЗУЛЬТАТ: Векторные тайлы недоступны")
        print(f"   Error: {tile_result.get('error', 'Unknown error')}")
        if 'details' in tile_result:
            print(f"   Details: {tile_result['details']}")
        sys.exit(1)
    
    # Проверяем стили
    style_result = check_styles(settings.map_tile_url)
    
    # Итоговый отчёт
    print(f"\n{'='*70}")
    print(f"  📊 ИТОГОВЫЙ ОТЧЁТ")
    print(f"{'='*70}\n")
    
    if tile_result["success"] and style_result["success"]:
        print(f"✅ Векторные тайлы: OK ({tile_result['size']} bytes)")
        print(f"✅ Стили: OK")
        print(f"   - Layers: {style_result.get('layers_count', 0)}")
        print(f"   - Sources: {style_result.get('sources_count', 0)}")
        print(f"\n🎉 ВСЁ РАБОТАЕТ! Карта должна отображаться корректно.")
        sys.exit(0)
    
    elif tile_result["success"] and not style_result["success"]:
        print(f"✅ Векторные тайлы: OK ({tile_result['size']} bytes)")
        print(f"⚠️  Стили: НЕ НАЙДЕНЫ")
        print(f"   Error: {style_result.get('error', 'Unknown error')}")
        print(f"\n⚠️  ЧАСТИЧНАЯ РАБОТА: Тайлы доступны, но нет стилей.")
        print(f"   Карта будет использовать fallback-стили (может выглядеть некорректно).")
        sys.exit(0)  # Не критично - приложение работает с fallback
    
    else:
        print(f"❌ Векторные тайлы: НЕДОСТУПНЫ")
        print(f"   Error: {tile_result.get('error', 'Unknown error')}")
        print(f"\n❌ КАРТА НЕ РАБОТАЕТ! Проверьте:")
        print(f"   1. Правильность URL (должен содержать {{z}}/{{x}}/{{y}})")
        print(f"   2. Действительность токена (если требуется)")
        print(f"   3. Доступность сервера")
        sys.exit(1)


if __name__ == "__main__":
    main()
