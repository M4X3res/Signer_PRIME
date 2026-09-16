"""
Пример использования системы лицензирования с локальным dev-сервером.

Для тестирования запустите локальный сервер лицензий:
    cd signer-license-server
    bash scripts/local_dev_up.sh

Затем установите переменную окружения:
    export SIGNER_LICENSE_SERVER_URL=http://localhost:8000
    python example_licensing_local.py
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

# Устанавливаем переменную окружения для локального сервера перед импортом
os.environ.setdefault("SIGNER_LICENSE_SERVER_URL", "http://localhost:8000")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from licensing.license_manager import LicenseManager, LicenseStatus

logger = logging.getLogger(__name__)

def main():
    """Демонстрация работы системы лицензирования."""
    
    print("=" * 60)
    print("Система лицензирования Signer PRIME (LOCAL DEV SERVER)")
    print("=" * 60)
    
    # Проверяем что сервер указан
    server_url = os.environ.get("SIGNER_LICENSE_SERVER_URL", "http://localhost:8000")
    print(f"\nLicense server URL: {server_url}")
    
    # Создаём менеджер лицензий
    manager = LicenseManager()
    
    # 1. Проверяем статус
    print("\n[1] Проверка статуса лицензии...")
    status = manager.check_local_status()
    print(f"    Статус: {status.value}")
    
    # 2. Если не активирована - активируем
    if status == LicenseStatus.NOT_ACTIVATED:
        print("\n[2] Лицензия не активирована, выполняем активацию...")
        print("    ВАЖНО: Сначала создайте тестовую лицензию через:")
        print("    cd signer-license-server")
        print("    python scripts/create_license_manual.py")
        print()
        
        test_key = input("    Введите ключ лицензии (или Enter для пропуска): ").strip()
        
        if not test_key:
            print("    Активация пропущена")
            return
        
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
    print(f"\nПримечание: Используется локальный dev-сервер на {server_url}")
    print("Для продакшна настройте реальный сервер лицензий.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nПрервано пользователем")
    except Exception as e:
        logger.error(f"Ошибка: {e}", exc_info=True)
        sys.exit(1)
