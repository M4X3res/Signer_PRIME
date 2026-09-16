"""
Проверка правильного формата URL векторных тайлов.
Тестирует разные комбинации координат и токена.
"""
import requests
from configs.settings import get_app_settings

settings = get_app_settings()

print(f"\n{'='*70}")
print(f"  ДИАГНОСТИКА URL ВЕКТОРНЫХ ТАЙЛОВ")
print(f"{'='*70}\n")

current_url = settings.map_tile_url
print(f"Текущий URL:")
print(f"  {current_url}\n")

# Извлекаем базовый URL и токен
base_url = current_url.split('?')[0] if '?' in current_url else current_url
query_string = '?' + current_url.split('?')[1] if '?' in current_url else ''

print(f"Базовый URL: {base_url}")
print(f"Query string: {query_string[:50]}{'...' if len(query_string) > 50 else ''}\n")

# Проблема 1: Проверяем токен
if '*' in query_string:
    print(f"⚠️  ПРОБЛЕМА ОБНАРУЖЕНА: Токен содержит символ '*'")
    print(f"   Это может означать что два токена были склеены вместе.\n")
    
    # Пробуем разделить
    token_param = query_string.replace('?token=', '')
    if '*' in token_param:
        tokens = token_param.split('*')
        print(f"   Найдено {len(tokens)} частей токена:")
        for i, part in enumerate(tokens):
            print(f"     [{i+1}] {part[:20]}...{part[-10:]}")
        
        print(f"\n   Рекомендация: Оставьте только один токен (обычно первый или последний).")
        print(f"   Попробуем оба варианта...\n")

# Тестовые координаты (Минск)
test_coords = [
    {'z': 9, 'x': 291, 'y': 163, 'desc': 'Минск zoom 9'},
    {'z': 20, 'x': 604567, 'y': 337149, 'desc': 'Из логов браузера'},
]

# Варианты порядка координат
coordinate_orders = [
    ('{z}/{y}/{x}', 'z/y/x (текущий)'),
    ('{z}/{x}/{y}', 'z/x/y (стандартный OSM/Mapbox)'),
]

print(f"{'─'*70}")
print(f"  ТЕСТИРОВАНИЕ ВАРИАНТОВ")
print(f"{'─'*70}\n")

# Варианты токенов для тестирования
token_variants = []

if '*' in query_string:
    token_param = query_string.replace('?token=', '')
    tokens = token_param.split('*')
    for i, token in enumerate(tokens):
        token_variants.append((f'?token={token}', f'Токен {i+1}'))
else:
    token_variants.append((query_string, 'Оригинальный токен'))

results = []

for token_query, token_desc in token_variants:
    for coord_format, coord_desc in coordinate_orders:
        for coords in test_coords:
            # Формируем URL
            test_base = base_url.replace('{z}/{y}/{x}', coord_format).replace('{z}/{x}/{y}', coord_format)
            test_url = (
                test_base
                .replace('{z}', str(coords['z']))
                .replace('{x}', str(coords['x']))
                .replace('{y}', str(coords['y']))
                + token_query
            )
            
            # Маскируем токен для вывода
            masked_url = test_url
            if 'token=' in masked_url:
                token_start = masked_url.index('token=') + 6
                token_val = masked_url[token_start:]
                if len(token_val) > 10:
                    masked_url = masked_url[:token_start] + f"****{token_val[-6:]}"
            
            print(f"Тест: {token_desc} + {coord_desc} + {coords['desc']}")
            print(f"  URL: {masked_url}")
            
            try:
                resp = requests.get(test_url, timeout=10)
                status = resp.status_code
                content_type = resp.headers.get('Content-Type', 'N/A')
                size = len(resp.content)
                
                print(f"  Ответ: HTTP {status}, {content_type}, {size} bytes")
                
                if status == 200 and ('protobuf' in content_type.lower() or 'pbf' in content_type.lower() or size > 0):
                    print(f"  ✅ УСПЕХ!\n")
                    results.append({
                        'success': True,
                        'url_template': test_base.replace(str(coords['z']), '{z}').replace(str(coords['x']), '{x}').replace(str(coords['y']), '{y}') + token_query,
                        'token_desc': token_desc,
                        'coord_desc': coord_desc,
                    })
                else:
                    print(f"  ❌ Ошибка")
                    if status != 200:
                        print(f"     Детали: {resp.text[:100]}")
                    print()
                    
            except Exception as e:
                print(f"  ❌ Исключение: {e}\n")

print(f"{'='*70}")
print(f"  РЕЗУЛЬТАТЫ")
print(f"{'='*70}\n")

if results:
    print(f"✅ Найдены рабочие варианты:\n")
    for i, result in enumerate(results, 1):
        print(f"{i}. {result['token_desc']} + {result['coord_desc']}")
        print(f"   URL: {result['url_template']}\n")
    
    print(f"Рекомендация: Скопируйте этот URL в настройки приложения (Настройки → Карта)")
else:
    print(f"❌ Ни один вариант не работает.\n")
    print(f"Возможные причины:")
    print(f"  1. Токен истёк или недействителен")
    print(f"  2. Сервер api.maps.by недоступен")
    print(f"  3. Неправильный базовый URL")
    print(f"\nСвяжитесь с провайдером карт для получения актуального URL и токена.")
