"""
licensing/device_fingerprint.py
Сбор аппаратных характеристик устройства для создания уникального fingerprint.
Используется для привязки лицензии к конкретному ПК.
"""
import hashlib
import logging
import platform
import subprocess
import uuid
from typing import Optional

logger = logging.getLogger(__name__)


def get_device_fingerprint() -> str:
    """
    Собирает и хэширует аппаратные характеристики устройства.
    
    Использует:
    - Серийный номер системного диска (Windows: wmic diskdrive)
    - MAC-адрес первого физического сетевого адаптера
    - Идентификатор процессора (platform.processor())
    
    Если какой-то источник недоступен — использует fallback значения.
    Это нормально: главное — стабильность fingerprint на одном ПК.
    
    Returns:
        SHA-256 хэш (64 символа hex) от комбинации характеристик.
    """
    components = []
    
    # 1. Серийный номер диска
    disk_serial = _get_disk_serial()
    if disk_serial:
        components.append(f"disk:{disk_serial}")
        logger.debug(f"[Fingerprint] Disk serial: {disk_serial[:8]}...")
    else:
        logger.warning("[Fingerprint] Disk serial unavailable, using fallback")
        components.append(f"disk:unknown")
    
    # 2. MAC-адрес (физический адаптер)
    mac = _get_mac_address()
    if mac:
        components.append(f"mac:{mac}")
        logger.debug(f"[Fingerprint] MAC address: {mac}")
    else:
        logger.warning("[Fingerprint] MAC address unavailable, using uuid.getnode()")
        # Fallback: uuid.getnode() (может быть не физическим MAC, но стабилен)
        components.append(f"mac:{uuid.getnode()}")
    
    # 3. CPU ID (processor string)
    cpu_id = platform.processor()
    if cpu_id:
        components.append(f"cpu:{cpu_id}")
        logger.debug(f"[Fingerprint] CPU: {cpu_id[:30]}...")
    else:
        logger.warning("[Fingerprint] CPU ID unavailable")
        components.append(f"cpu:unknown")
    
    # Объединяем через pipe и хэшируем
    combined = "|".join(components)
    fingerprint = hashlib.sha256(combined.encode('utf-8')).hexdigest()
    
    logger.info(f"[Fingerprint] Generated: {fingerprint[:16]}...")
    return fingerprint


def _get_disk_serial() -> Optional[str]:
    """
    Получить серийный номер системного диска (Windows).
    
    Returns:
        Серийный номер диска или None если не удалось получить.
    """
    try:
        if platform.system() != "Windows":
            # На Linux/Mac можно использовать другие методы
            # Пока оставляем только Windows (т.к. проект под Windows)
            return None
        
        # wmic diskdrive get serialnumber
        result = subprocess.run(
            ["wmic", "diskdrive", "get", "serialnumber"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW  # Не показывать окно консоли
        )
        
        if result.returncode != 0:
            return None
        
        # Парсим вывод: первая строка — заголовок, вторая — значение
        lines = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
        if len(lines) >= 2:
            serial = lines[1].strip()
            if serial and serial.lower() != "serialnumber":
                return serial
        
        return None
    
    except Exception as e:
        logger.debug(f"[Fingerprint] Error getting disk serial: {e}")
        return None


def _get_mac_address() -> Optional[str]:
    """
    Получить MAC-адрес первого физического сетевого адаптера (Windows).
    
    Returns:
        MAC-адрес в формате AA:BB:CC:DD:EE:FF или None.
    """
    try:
        if platform.system() != "Windows":
            return None
        
        # wmic nic where "PhysicalAdapter=True" get MACAddress
        result = subprocess.run(
            ["wmic", "nic", "where", "PhysicalAdapter=True", "get", "MACAddress"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        
        if result.returncode != 0:
            return None
        
        # Парсим вывод: берём первый валидный MAC
        lines = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
        for line in lines[1:]:  # Пропускаем заголовок
            if ':' in line or '-' in line:
                # Нормализуем формат (может быть XX:XX:XX:XX:XX:XX или XX-XX-XX-XX-XX-XX)
                mac = line.replace('-', ':').upper()
                if len(mac) == 17:  # AA:BB:CC:DD:EE:FF
                    return mac
        
        return None
    
    except Exception as e:
        logger.debug(f"[Fingerprint] Error getting MAC address: {e}")
        return None


def get_device_label() -> str:
    """
    Получить человекочитаемое имя устройства (hostname).
    Используется для отображения в личном кабинете пользователя.
    
    Returns:
        Hostname или "Unknown Device".
    """
    try:
        return platform.node() or "Unknown Device"
    except Exception:
        return "Unknown Device"


if __name__ == "__main__":
    # Тест
    logging.basicConfig(level=logging.DEBUG)
    print("=== Device Fingerprint Test ===")
    print(f"Fingerprint: {get_device_fingerprint()}")
    print(f"Device label: {get_device_label()}")
    print(f"\nDisk serial: {_get_disk_serial()}")
    print(f"MAC address: {_get_mac_address()}")
    print(f"CPU: {platform.processor()}")
