Fix the following verified bugs in the Signer PRIME project. Make minimal, targeted changes; don't refactor unrelated code.

1. licensing/license_manager.py — LicenseManager.refresh_async() creates a RefreshWorker(QThread)
   as a local variable with no reference kept and no parent set, so PyQt can garbage-collect it
   mid-execution, silently breaking license refresh. Fix: store the worker on the manager instance
   (e.g. self._refresh_workers = set(); add worker on start, remove it in a slot connected to
   worker.finished after the on_done callback runs) so it can't be collected while running, and
   clean up properly afterward (worker.deleteLater()). Apply the same pattern anywhere else in the
   codebase that creates a QThread without keeping a persistent reference.

2. updater/updater_main.py — In apply_delta_update(), the variable `backed_up_files = []` is declared
   inside the `try` block AFTER the manifest-read and zip-extraction steps. If either of those steps
   raises, the `except` block's rollback loop `for backed_up_file in backed_up_files:` throws a
   NameError because the variable doesn't exist yet, masking the real error and skipping rollback.
   Fix: move `backed_up_files = []` to before the `try:` block (right after `extraction_dir = ...`).

3. signer-license-server: Server never verifies Ed25519 signatures on tokens submitted back to it.
   app/crypto.py only has sign_token()/parse_token() (parse_token does NOT check the signature).
   - Add a verify_token_signature(token_str, public_key) function to app/crypto.py that derives the
     Ed25519 public key from the loaded private key and verifies the signature (mirroring
     licensing/public_key.py::verify_token on the client), returning (valid, payload, error).
   - In app/services/license_service.py, use this new verification function instead of parse_token()
     in both refresh_license() and deactivate_device(), rejecting with 401 INVALID_TOKEN on signature
     failure.
   - Additionally, deactivate_device() currently has NO secondary check (no fingerprint match) before
     deactivating a device by device_id alone — this allows deactivating arbitrary devices if a
     device_id ever leaks. Add a required `fingerprint_hash` field to DeactivateRequest in
     app/schemas.py, and in LicenseService.deactivate_device() verify it matches the stored
     device.fingerprint_hash (like refresh_license does) before deactivating, returning 403
     FINGERPRINT_MISMATCH otherwise.
   - Update the client to match: licensing/license_client.py::deactivate() and
     licensing/license_manager.py::deactivate_this_device() must send fingerprint_hash in the request
     body (self.fingerprint is already computed in LicenseManager).
   - Update signer-license-server/tests to cover: forged/unsigned token rejected on refresh and
     deactivate; deactivate with mismatched fingerprint rejected.

4. ui/widgets/settings_page.py::_export_models — two references to
   theme_manager.tokens['text_muted'] which does not exist in either theme's token dict
   (ui/themes/modern_dark.py / modern_light.py). Replace both with 'text_secondary'.

5. signer.spec — the PyArmor runtime auto-include glob only checks
   os.path.join(ROOT, 'build', 'obfuscated', 'pyarmor_runtime_*') non-recursively. Inspect
   scripts/build/obfuscate_licensing.py to see where PyArmor actually places the runtime directory
   (it may be nested under build/obfuscated/licensing/ if using in-place obfuscation of that
   package). Make the glob recursive (glob.glob(os.path.join(_obfuscated_root, '**',
   'pyarmor_runtime_*'), recursive=True)) and dedupe, so the correct runtime directory (with its
   real relative path preserved) is always found and bundled regardless of nesting depth.

6. main.py::_on_license_status_changed — connects window.results_saved to
   _show_license_expired_and_quit every time this callback fires (every 6h) without disconnecting,
   causing duplicate connections over long-running sessions. Use
   window.results_saved.connect(_show_license_expired_and_quit, Qt.ConnectionType.UniqueConnection)
   (wrapped in try/except TypeError, since Qt raises if already connected) or track a boolean to
   only connect once.

After each fix, run the existing relevant tests (tests/test_licensing.py,
signer-license-server/tests/) and add regression tests for items 1-3 specifically, since those are
security/reliability sensitive.