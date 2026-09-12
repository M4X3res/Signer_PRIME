"""
Пример использования системы лицензирования в мок-режиме (без сервера).

Для тестирования без реального сервера лицензий установите
LICENSE_MOCK_MODE = True в licensing/license_client.py
"""
import logging
import sys
import os

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)

# Включаем мок-режим
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Устанавливаем мок-режим перед импортом
import licensing.license_client
licensing.license_client.LICENSE_MOCK_MODE = True

from licensing.license_manager import LicenseManager, LicenseStatus

logger = logging.getLogger(__name__)

def main():
    """Демонстрация работы системы лицензирования."""
    
    print("=" * 60)
    print("Система лицензирования Signer PRIME (МОК-РЕЖИМ)")
    print("=" * 60)
    
    # Создаём менеджер лицензий
    manager = LicenseManager()
    
    # 1. Проверяем статус
    print("\n[1] Проверка статуса лицензии...")
    status = manager.check_local_status()
    print(f"    Статус: {status.value}")
    
    # 2. Если не активирована - активируем
    if status == LicenseStatus.NOT_ACTIVATED:
        print("\n[2] Лицензия не активирована, выполняем активацию...")
        print("    (в мок-режиме любой ключ будет принят)")
        
        test_key = "SGNR-TEST-MOCK-MODE-KEY1"
        print(f"    Ключ: {test_key}")
        
        success, error_msg = manager.activate(test_key)
        
        if success:
            print("    ✓ Активация успешна!")
        else:
            print(f"    ✗ Ошибка: {error_msg}")
            return
        
        # Проверяем статус после активации
        status = manager.check_local_status()
        print(f"    Новый статус: {status.value}")
    
    # 3. Показываем информацию о лицензии
    print("\n[3] Информация о лицензии:")
    plan_info = manager.get_plan_info()
    
    if plan_info:
        from datetime import datetime
        
        print(f"    Ключ: {plan_info['license_key']}")
        print(f"    План: {plan_info['plan']}")
        
        expiry_date = datetime.fromtimestamp(plan_info['current_period_end'])
        print(f"    Действует до: {expiry_date.strftime('%d.%m.%Y %H:%M:%S')}")
        
        issued_date = datetime.fromtimestamp(plan_info['issued_at'])
        print(f"    Выдан: {issued_date.strftime('%d.%m.%Y %H:%M:%S')}")
    else:
        print("    (нет данных)")
    
    # 4. Демонстрация refresh
    print("\n[4] Обновление токена (синхронное)...")
    success = manager._refresh_internal()
    print(f"    Результат: {'успешно' if success else 'ошибка'}")
    
    # 5. Путь к файлу токена
    print("\n[5] Файл токена:")
    print(f"    {manager.token_path}")
    print(f"    Существует: {manager.token_path.exists()}")
    
    # 6. Опция деактивации
    print("\n[6] Опции управления:")
    print("    Для деактивации: manager.deactivate_this_device()")
    print("    Для удаления токена: удалить файл license.token")
    
    print("\n" + "=" * 60)
    print("Тестирование завершено успешно!")
    print("=" * 60)
    print("\nПримечание: Это МОК-РЕЖИМ для разработки без сервера.")
    print("Для продакшна отключите LICENSE_MOCK_MODE и настройте сервер.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nПрервано пользователем")
    except Exception as e:
        logger.error(f"Ошибка: {e}", exc_info=True)
        sys.exit(1)
