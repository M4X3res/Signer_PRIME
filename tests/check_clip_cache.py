"""
tests/check_clip_cache.py
Regression test для Задачи 2: Кэш видео-клипов в отдельной папке.
"""
import os
import sys
import re

def test_clip_cache_constants():
    """Проверяет наличие константы CLIP_CACHE_DIRNAME в map_server.py"""
    
    map_server_path = "server/map_server.py"
    
    if not os.path.exists(map_server_path):
        print(f"❌ Файл {map_server_path} не найден")
        return False
    
    with open(map_server_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if 'CLIP_CACHE_DIRNAME' not in content:
        print("❌ Константа CLIP_CACHE_DIRNAME не найдена")
        return False
    
    if '.signer_clip_cache' not in content:
        print("❌ Значение CLIP_CACHE_DIRNAME не найдено")
        return False
    
    print("✅ Константа CLIP_CACHE_DIRNAME определена корректно")
    return True


def test_cache_helper_functions():
    """Проверяет наличие функций для работы с кэшем"""
    
    map_server_path = "server/map_server.py"
    
    with open(map_server_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if 'def _get_clip_cache_dir' not in content:
        print("❌ Функция _get_clip_cache_dir не найдена")
        return False
    
    if 'def clear_clip_cache' not in content:
        print("❌ Функция clear_clip_cache не найдена")
        return False
    
    print("✅ Функции для работы с кэшем определены")
    return True


def test_api_video_clip_uses_subfolder():
    """Проверяет что api_video_clip использует подпапку для кэша"""
    
    map_server_path = "server/map_server.py"
    
    with open(map_server_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Ищем функцию api_video_clip
    if '@app.route("/api/video_clip' not in content:
        print("❌ Роут /api/video_clip не найден")
        return False
    
    # Проверяем что используется _get_clip_cache_dir
    if '_get_clip_cache_dir(video_path)' not in content:
        print("❌ api_video_clip не использует _get_clip_cache_dir")
        return False
    
    # Проверяем что старый паттерн (кэш прямо в video_dir) больше не используется
    # Ищем паттерн where cache_path формируется напрямую через video_dir
    lines = content.split('\n')
    in_api_video_clip = False
    bad_pattern_found = False
    
    for i, line in enumerate(lines):
        if 'def api_video_clip' in line:
            in_api_video_clip = True
        elif in_api_video_clip and ('def ' in line or '@app.route' in line):
            in_api_video_clip = False
        
        # Проверяем старый паттерн только внутри api_video_clip
        if in_api_video_clip:
            # Старый паттерн: cache_path = os.path.join(video_dir, cache_filename)
            # где video_dir = os.path.dirname(video_path), а не результат _get_clip_cache_dir
            if 'cache_path = os.path.join(video_dir, cache_filename)' in line:
                # Проверяем что перед этим есть вызов _get_clip_cache_dir
                context_lines = lines[max(0, i-5):i]
                if not any('_get_clip_cache_dir' in l for l in context_lines):
                    bad_pattern_found = True
                    print(f"❌ Найден старый паттерн кэширования в строке {i+1}")
                    break
    
    if bad_pattern_found:
        return False
    
    print("✅ api_video_clip использует подпапку для кэша")
    return True


def test_clear_cache_route():
    """Проверяет наличие роута для очистки кэша"""
    
    map_server_path = "server/map_server.py"
    
    with open(map_server_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if '@app.route("/api/clear_clip_cache"' not in content:
        print("❌ Роут /api/clear_clip_cache не найден")
        return False
    
    if 'def api_clear_clip_cache' not in content:
        print("❌ Функция api_clear_clip_cache не найдена")
        return False
    
    if 'clear_clip_cache(video_dir)' not in content:
        print("❌ api_clear_clip_cache не вызывает clear_clip_cache")
        return False
    
    print("✅ Роут для очистки кэша добавлен")
    return True


def test_map_html_clear_button():
    """Проверяет наличие кнопки очистки кэша в map.html"""
    
    map_html_path = "templates/map.html"
    
    if not os.path.exists(map_html_path):
        print(f"❌ Файл {map_html_path} не найден")
        return False
    
    with open(map_html_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Проверяем наличие кнопки
    if 'Очистить кэш' not in content and 'clearClipCache' not in content:
        print("❌ Кнопка очистки кэша не найдена в map.html")
        return False
    
    # Проверяем наличие функции clearClipCache
    if 'function clearClipCache' not in content and 'async function clearClipCache' not in content:
        print("❌ Функция clearClipCache не найдена в map.html")
        return False
    
    # Проверяем что функция делает POST запрос к /api/clear_clip_cache
    if '/clear_clip_cache' not in content:
        print("❌ clearClipCache не делает запрос к /api/clear_clip_cache")
        return False
    
    if "method: 'POST'" not in content and 'method: "POST"' not in content:
        print("❌ clearClipCache не использует метод POST")
        return False
    
    print("✅ Кнопка и функция очистки кэша добавлены в map.html")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("Проверка Задачи 2: Кэш видео-клипов")
    print("=" * 60)
    
    results = [
        test_clip_cache_constants(),
        test_cache_helper_functions(),
        test_api_video_clip_uses_subfolder(),
        test_clear_cache_route(),
        test_map_html_clear_button(),
    ]
    
    print("=" * 60)
    if all(results):
        print("✅ Все проверки пройдены успешно!")
        sys.exit(0)
    else:
        print("❌ Некоторые проверки не прошли")
        sys.exit(1)
