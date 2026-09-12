#!/usr/bin/env python3
"""
create_license_manual.py

CLI-обёртка для создания лицензий через admin API.
Использует переменные окружения LICENSE_SERVER_URL и ADMIN_API_KEY.

Usage:
    export LICENSE_SERVER_URL=http://localhost:8000
    export ADMIN_API_KEY=your_admin_key
    
    python scripts/create_license_manual.py --plan monthly --days 30 --devices 2
"""
import argparse
import os
import sys
import json

try:
    import requests
except ImportError:
    print("ERROR: requests library not found. Install: pip install requests", file=sys.stderr)
    sys.exit(1)


def create_license(server_url: str, admin_key: str, plan: str, duration_days: int, max_devices: int) -> dict:
    """Вызвать admin API для создания лицензии."""
    
    url = f"{server_url.rstrip('/')}/api/admin/licenses"
    headers = {
        "X-Admin-Key": admin_key,
        "Content-Type": "application/json"
    }
    payload = {
        "plan": plan,
        "duration_days": duration_days,
        "max_devices": max_devices
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Failed to create license: {e}", file=sys.stderr)
        if hasattr(e.response, 'text'):
            print(f"Response: {e.response.text}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Create a license key via admin API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Monthly license for 2 devices
  python scripts/create_license_manual.py --plan monthly --days 30 --devices 2
  
  # Yearly license for 5 devices
  python scripts/create_license_manual.py --plan yearly --days 365 --devices 5

Environment Variables:
  LICENSE_SERVER_URL    License server URL (default: http://localhost:8000)
  ADMIN_API_KEY         Admin API key (required)
        """
    )
    
    parser.add_argument(
        "--plan",
        required=True,
        choices=["monthly", "quarterly", "yearly"],
        help="License plan type"
    )
    parser.add_argument(
        "--days",
        type=int,
        required=True,
        help="Duration in days (1-3650)"
    )
    parser.add_argument(
        "--devices",
        type=int,
        default=2,
        help="Maximum devices (1-10, default: 2)"
    )
    parser.add_argument(
        "--server-url",
        default=os.getenv("LICENSE_SERVER_URL", "http://localhost:8000"),
        help="License server URL (default: $LICENSE_SERVER_URL or http://localhost:8000)"
    )
    parser.add_argument(
        "--admin-key",
        default=os.getenv("ADMIN_API_KEY"),
        help="Admin API key (default: $ADMIN_API_KEY)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON (for scripting)"
    )
    
    args = parser.parse_args()
    
    # Валидация
    if not args.admin_key:
        print("ERROR: ADMIN_API_KEY not set. Use --admin-key or set ADMIN_API_KEY env var.", file=sys.stderr)
        sys.exit(1)
    
    if args.days < 1 or args.days > 3650:
        print("ERROR: Duration must be between 1 and 3650 days", file=sys.stderr)
        sys.exit(1)
    
    if args.devices < 1 or args.devices > 10:
        print("ERROR: Max devices must be between 1 and 10", file=sys.stderr)
        sys.exit(1)
    
    # Создание лицензии
    result = create_license(
        server_url=args.server_url,
        admin_key=args.admin_key,
        plan=args.plan,
        duration_days=args.days,
        max_devices=args.devices
    )
    
    # Вывод
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        # Только ключ в stdout для удобного копирования
        print(result["license_key"])


if __name__ == "__main__":
    main()
