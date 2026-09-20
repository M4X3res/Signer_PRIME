"""Reject the known development key before building a distributable release."""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from licensing.public_key import LICENSE_PUBLIC_KEY_PEM, DEV_KEY_SHA256

if hashlib.sha256(LICENSE_PUBLIC_KEY_PEM.encode()).hexdigest() == DEV_KEY_SHA256:
    raise SystemExit('Release blocked: replace the development public key with the public key of the production license server.')
print('Production public key check passed')
