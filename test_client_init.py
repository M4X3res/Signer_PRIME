#!/usr/bin/env python
"""Тест для проверки, что LicenseClient инстанцируется без ошибок."""
import sys
import importlib.util

# Прямой импорт модуля, минуя __init__.py
spec = importlib.util.spec_from_file_location("license_client", "licensing/license_client.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

LicenseClient = module.LicenseClient

try:
    client = LicenseClient()
    print('OK')
    print(f'base_url: {client.base_url}')
except Exception as e:
    print(f'FAILED: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
