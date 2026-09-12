#!/usr/bin/env python3
"""
test_api.py
Быстрый тест API сервера лицензий (для ручной проверки после деплоя).
"""
import sys
import argparse
import requests
import hashlib

def test_health(base_url: str):
    """Тест health check endpoint."""
    print("\n🔍 Testing /health...")
    response = requests.get(f"{base_url}/health")
    if response.status_code == 200:
        print(f"✅ Health check OK: {response.json()}")
        return True
    else:
        print(f"❌ Health check failed: {response.status_code}")
        return False

def test_create_license(base_url: str, admin_key: str):
    """Тест создания лицензии."""
    print("\n🔍 Testing POST /api/admin/licenses...")
    response = requests.post(
        f"{base_url}/api/admin/licenses",
        json={"plan": "monthly", "duration_days": 30, "max_devices": 2},
        headers={"X-Admin-Key": admin_key}
    )
    if response.status_code == 200:
        data = response.json()
        print(f"✅ License created: {data['license_key']}")
        return data['license_key']
    else:
        print(f"❌ License creation failed: {response.status_code} {response.text}")
        return None

def test_activate(base_url: str, license_key: str):
    """Тест активации лицензии."""
    print("\n🔍 Testing POST /api/license/activate...")
    fingerprint = hashlib.sha256(b"test_device_123").hexdigest()
    response = requests.post(
        f"{base_url}/api/license/activate",
        json={
            "license_key": license_key,
            "fingerprint_hash": fingerprint,
            "device_label": "Test Device",
            "app_version": "1.0.0"
        }
    )
    if response.status_code == 200:
        data = response.json()
        print(f"✅ License activated, token: {data['token'][:50]}...")
        return data['token']
    else:
        print(f"❌ Activation failed: {response.status_code} {response.text}")
        return None

def test_refresh(base_url: str, token: str):
    """Тест refresh токена."""
    print("\n🔍 Testing POST /api/license/refresh...")
    fingerprint = hashlib.sha256(b"test_device_123").hexdigest()
    response = requests.post(
        f"{base_url}/api/license/refresh",
        json={
            "token": token,
            "fingerprint_hash": fingerprint
        }
    )
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Token refreshed: {data['token'][:50]}...")
        return True
    else:
        print(f"❌ Refresh failed: {response.status_code} {response.text}")
        return False

def test_deactivate(base_url: str, token: str):
    """Тест деактивации устройства."""
    print("\n🔍 Testing POST /api/license/deactivate...")
    response = requests.post(
        f"{base_url}/api/license/deactivate",
        json={"token": token}
    )
    if response.status_code == 200:
        print(f"✅ Device deactivated")
        return True
    else:
        print(f"❌ Deactivation failed: {response.status_code} {response.text}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Test License Server API")
    parser.add_argument("--url", required=True, help="Server URL (e.g., http://localhost:8000)")
    parser.add_argument("--admin-key", required=True, help="Admin API key")
    args = parser.parse_args()
    
    base_url = args.url.rstrip('/')
    
    print("════════════════════════════════════════════════════════")
    print(" License Server API Test")
    print("════════════════════════════════════════════════════════")
    print(f"Server: {base_url}")
    print()
    
    # Test sequence
    success_count = 0
    total_tests = 5
    
    # 1. Health check
    if test_health(base_url):
        success_count += 1
    
    # 2. Create license
    license_key = test_create_license(base_url, args.admin_key)
    if license_key:
        success_count += 1
    else:
        print("\n❌ Cannot continue without license key")
        sys.exit(1)
    
    # 3. Activate
    token = test_activate(base_url, license_key)
    if token:
        success_count += 1
    else:
        print("\n❌ Cannot continue without token")
        sys.exit(1)
    
    # 4. Refresh
    if test_refresh(base_url, token):
        success_count += 1
    
    # 5. Deactivate
    if test_deactivate(base_url, token):
        success_count += 1
    
    # Summary
    print("\n" + "=" * 60)
    print(f" Results: {success_count}/{total_tests} tests passed")
    print("=" * 60)
    
    if success_count == total_tests:
        print("✅ All tests passed!")
        sys.exit(0)
    else:
        print(f"❌ {total_tests - success_count} test(s) failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
