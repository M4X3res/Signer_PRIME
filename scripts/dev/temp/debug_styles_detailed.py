"""
Детальная проверка запросов к стилям и тайлам.
Смотрим что именно возвращает сервер для каждого endpoint.
"""
import requests
from configs.settings import get_app_settings

settings = get_app_settings()

print(f"\n{'='*70}")
print(f"  ДЕТАЛЬНАЯ ПРОВЕРКА СТИЛЕЙ И ТАЙЛОВ")
print(f"{'='*70}\n")

tile_url = settings.map_tile_url
print(f"Текущий URL: {tile_url}\n")

# Извлекаем базовый URL и query string
base_url = tile_url.split('?')[0] if '?' in tile_url else tile_url
query_string = '?' + tile_url.split('?')[1] if '?' in tile_url else ''

print(f"Базовый URL: {base_url}")
print(f"Query: {query_string[:50]}...\n")

# Тестовые координаты
z, x, y = 9, 291, 163

# 1. Проверяем тайл напрямую
print(f"{'─'*70}")
print(f"  ТЕСТ 1: Запрос тайла напрямую")
print(f"{'─'*70}\n")

tile_test_url = base_url.replace('{z}', str(z)).replace('{x}', str(x)).replace('{y}', str(y)) + query_string

print(f"URL: {tile_test_url[:80]}...")
try:
    resp = requests.get(tile_test_url, timeout=10)
    print(f"HTTP Status: {resp.status_code}")
    print(f"Content-Type: {resp.headers.get('Content-Type', 'N/A')}")
    print(f"Content-Length: {len(resp.content)} bytes")
    
    if resp.status_code != 200:
        print(f"Ответ: {resp.text[:200]}")
    else:
        print(f"✅ Тайл загружен успешно")
        
        # Проверяем это действительно protobuf
        if resp.content[:2] == b'\x1a\x00' or 'protobuf' in resp.headers.get('Content-Type', '').lower():
            print(f"   Формат: Protobuf (векторный тайл)")
        else:
            print(f"   ⚠️  Не похоже на protobuf, первые байты: {resp.content[:10]}")
except Exception as e:
    print(f"❌ Ошибка: {e}")

# 2. Проверяем стили - вариант 1 (без /VectorTileServer в пути)
print(f"\n{'─'*70}")
print(f"  ТЕСТ 2: Запрос стилей (вариант 1)")
print(f"{'─'*70}\n")

# Убираем /VectorTileServer/tile/ из base_url
if '/VectorTileServer/tile/' in base_url:
    style_base = base_url.split('/VectorTileServer/tile/')[0]
    style_url_1 = f"{style_base}/resources/styles{query_string}"
else:
    style_url_1 = base_url.replace('/tile/{z}/{y}/{x}.pbf', '/resources/styles') + query_string

print(f"URL: {style_url_1[:80]}...")
try:
    resp = requests.get(style_url_1, timeout=10, headers={'Accept': 'application/json'})
    print(f"HTTP Status: {resp.status_code}")
    print(f"Content-Type: {resp.headers.get('Content-Type', 'N/A')}")
    print(f"Content-Length: {len(resp.content)} bytes")
    
    if resp.status_code == 200:
        print(f"✅ Стили получены!")
        try:
            import json
            data = resp.json()
            print(f"   Структура: {list(data.keys())[:5]}")
            if 'layers' in data:
                print(f"   Layers: {len(data['layers'])} слоёв")
            if 'sources' in data:
                print(f"   Sources: {len(data['sources'])} источников")
        except:
            print(f"   ⚠️  Не JSON: {resp.text[:100]}")
    else:
        print(f"Ответ: {resp.text[:200]}")
except Exception as e:
    print(f"❌ Ошибка: {e}")

# 3. Проверяем стили - вариант 2 (с /VectorTileServer в пути)
print(f"\n{'─'*70}")
print(f"  ТЕСТ 3: Запрос стилей (вариант 2)")
print(f"{'─'*70}\n")

if '/VectorTileServer/tile/' in base_url:
    style_base = base_url.split('/VectorTileServer/tile/')[0]
    style_url_2 = f"{style_base}/VectorTileServer/resources/styles{query_string}"
    
    print(f"URL: {style_url_2[:80]}...")
    try:
        resp = requests.get(style_url_2, timeout=10, headers={'Accept': 'application/json'})
        print(f"HTTP Status: {resp.status_code}")
        print(f"Content-Type: {resp.headers.get('Content-Type', 'N/A')}")
        print(f"Content-Length: {len(resp.content)} bytes")
        
        if resp.status_code == 200:
            print(f"✅ Стили получены!")
            try:
                import json
                data = resp.json()
                print(f"   Структура: {list(data.keys())[:5]}")
                if 'layers' in data:
                    print(f"   Layers: {len(data['layers'])} слоёв")
                if 'sources' in data:
                    print(f"   Sources: {len(data['sources'])} источников")
            except:
                print(f"   ⚠️  Не JSON: {resp.text[:100]}")
        else:
            print(f"Ответ: {resp.text[:200]}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
else:
    print(f"Пропущено - URL не содержит /VectorTileServer/")

# 4. Проверяем что возвращает root endpoint
print(f"\n{'─'*70}")
print(f"  ТЕСТ 4: Запрос корневого endpoint")
print(f"{'─'*70}\n")

if '/VectorTileServer/tile/' in base_url:
    root_url = base_url.split('/VectorTileServer/tile/')[0] + '/VectorTileServer' + query_string
    
    print(f"URL: {root_url[:80]}...")
    try:
        resp = requests.get(root_url, timeout=10, headers={'Accept': 'application/json'})
        print(f"HTTP Status: {resp.status_code}")
        print(f"Content-Type: {resp.headers.get('Content-Type', 'N/A')}")
        
        if resp.status_code == 200:
            try:
                import json
                data = resp.json()
                print(f"✅ Корневой endpoint отвечает")
                print(f"   Ключи: {list(data.keys())[:10]}")
                
                # Ищем ссылки на стили
                if 'defaultStyles' in data:
                    print(f"   defaultStyles: {data['defaultStyles']}")
                if 'tiles' in data:
                    print(f"   tiles: {data['tiles'][:100]}...")
                if 'styleUrl' in data:
                    print(f"   styleUrl: {data['styleUrl']}")
                    
            except Exception as e:
                print(f"   Ответ (не JSON): {resp.text[:300]}")
        else:
            print(f"Ответ: {resp.text[:200]}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

print(f"\n{'='*70}")
print(f"  ВЫВОДЫ")
print(f"{'='*70}\n")
print(f"Если ТЕСТ 1 (тайлы) работает, но ТЕСТ 2-3 (стили) не работают,")
print(f"то проблема именно в доступе к endpoint стилей, а не в токене.\n")
