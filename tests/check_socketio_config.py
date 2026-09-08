"""
Интеграционный тест для проверки Flask-SocketIO конфигурации.
Защита от регрессии async_mode.
"""
import sys
import os


def test_socketio_async_mode():
    """Проверяет что async_mode в map_server.py имеет правильное значение."""
    
    with open("server/map_server.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    # Проверяем что async_mode НЕ равен "processing" (невалидное значение)
    if 'async_mode="processing"' in content or "async_mode='processing'" in content:
        print("FAIL: async_mode='processing' is INVALID for Flask-SocketIO!")
        print("Valid values: 'threading', 'eventlet', 'gevent', 'gevent_uwsgi', or None")
        return False
    
    # Проверяем что установлено правильное значение
    valid_modes = ["threading", "eventlet", "gevent", "gevent_uwsgi"]
    has_valid_mode = any(f'async_mode="{mode}"' in content or f"async_mode='{mode}'" in content for mode in valid_modes)
    
    if not has_valid_mode:
        print("FAIL: async_mode not found or has invalid value")
        print(f"Valid values: {valid_modes}")
        return False
    
    # Определяем какой режим используется
    used_mode = None
    for mode in valid_modes:
        if f'async_mode="{mode}"' in content or f"async_mode='{mode}'" in content:
            used_mode = mode
            break
    
    print(f"PASS: async_mode='{used_mode}' (valid)")
    return True


def test_socketio_initialization():
    """Проверяет базовую инициализацию SocketIO."""
    
    with open("server/map_server.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    required_patterns = [
        "from flask_socketio import SocketIO",
        "socketio = SocketIO",
        "cors_allowed_origins",
    ]
    
    missing = []
    for pattern in required_patterns:
        if pattern not in content:
            missing.append(pattern)
    
    if missing:
        print(f"FAIL: Missing required patterns:")
        for p in missing:
            print(f"  - {p}")
        return False
    
    print("PASS: SocketIO initialization present")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("Flask-SocketIO Configuration Test")
    print("=" * 60)
    
    results = [
        test_socketio_async_mode(),
        test_socketio_initialization(),
    ]
    
    print("=" * 60)
    if all(results):
        print("ALL TESTS PASSED")
        sys.exit(0)
    else:
        print("SOME TESTS FAILED")
        sys.exit(1)
