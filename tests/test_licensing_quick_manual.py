"""
Quick test of licensing module import.
"""
try:
    from licensing import LicenseManager, LicenseStatus
    print("[OK] Licensing module imports successfully")
    
    from licensing.device_fingerprint import get_device_fingerprint
    fp = get_device_fingerprint()
    print(f"[OK] Device fingerprint: {fp[:16]}...")
    
    from licensing.public_key import verify_token
    print("[OK] Public key module loads successfully")
    
    manager = LicenseManager()
    status = manager.check_local_status()
    print(f"[OK] License manager created, status: {status.value}")
    
    print("\n[SUCCESS] All licensing components working!")
    
except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
