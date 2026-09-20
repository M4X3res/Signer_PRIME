"""Online licensing regression tests, using ephemeral signed tokens and no network."""
import ast
import base64
import json
import logging
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PyQt6.QtCore import QCoreApplication, QEventLoop, QTimer, QThread
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from licensing.license_manager import LicenseManager, LicenseStatus
from licensing.license_client import LicenseClient, LicenseResponse
from licensing.access import online_action


class OnlineLicenseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.private = Ed25519PrivateKey.generate()
        public = self.private.public_key().public_bytes(serialization.Encoding.PEM,
                                                       serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        self.key_patch = patch('licensing.public_key.LICENSE_PUBLIC_KEY_PEM', public)
        self.key_patch.start(); self.addCleanup(self.key_patch.stop)
        self.client = Mock()
        with patch.object(LicenseManager, '_get_token_path', return_value=Path(self.temp.name)/'license.token'), \
             patch('licensing.license_manager.LicenseClient', return_value=self.client), \
             patch('licensing.license_manager.get_device_fingerprint', return_value='fixture'):
            self.manager = LicenseManager()
        self.manager._save_token(self.token())
        self.client.refresh.return_value = LicenseResponse(True, token=self.token())

    def token(self, **changes):
        payload = dict(status='active', license_key='fixture', device_id='fixture', plan='monthly',
                       current_period_end=int(time.time())+3600, issued_at=int(time.time())-1)
        payload.update(changes)
        data = json.dumps(payload).encode()
        encode = lambda value: base64.urlsafe_b64encode(value).rstrip(b'=').decode()
        return encode(data)+'.'+encode(self.private.sign(data))

    def test_offline_cached_token_is_not_authorization(self):
        self.client.refresh.return_value = LicenseResponse(False, error_code='CONNECTION_ERROR')
        self.assertEqual(self.manager.check_local_status(), LicenseStatus.VALID)
        self.assertEqual(self.manager._verify_access_internal()[0], LicenseStatus.NETWORK_ERROR)
        self.assertFalse(self.manager.has_online_access())
        self.assertTrue(self.manager.token_path.exists())

    def test_rejected_server_status_not_lost_after_token_deletion(self):
        for code in ('LICENSE_REVOKED', 'DEVICE_DEACTIVATED', 'FINGERPRINT_MISMATCH'):
            with self.subTest(code=code):
                self.manager._save_token(self.token())
                self.client.refresh.return_value = LicenseResponse(False, error_code=code)
                status, _ = self.manager._verify_access_internal()
                self.assertIn(status, (LicenseStatus.EXPIRED, LicenseStatus.REVOKED))
                self.assertEqual(self.manager._access_status, status)
                self.assertFalse(self.manager.token_path.exists())

    def test_bad_success_response_keeps_previous_token_and_blocks(self):
        before = self.manager.token_path.read_bytes()
        for token in (None, '', 'broken', self.token(status='revoked'), self.token(issued_at='bad'),
                      self.token(current_period_end=int(time.time())), self.token(device_id=None)):
            with self.subTest(token_type=type(token).__name__):
                self.client.refresh.return_value = LicenseResponse(True, token=token)
                self.assertNotEqual(self.manager._verify_access_internal()[0], LicenseStatus.VALID)
                self.assertEqual(before, self.manager.token_path.read_bytes())
                self.assertFalse(self.manager.has_online_access())

    def test_write_failure_is_not_success_and_keeps_old_token(self):
        before = self.manager.token_path.read_bytes()
        with patch('licensing.license_manager.os.replace', side_effect=PermissionError('read only')):
            self.assertEqual(self.manager._verify_access_internal()[0], LicenseStatus.NETWORK_ERROR)
        self.assertEqual(before, self.manager.token_path.read_bytes())
        self.assertEqual(list(Path(self.temp.name).glob('*.tmp')), [])

    def test_activation_rejects_missing_token(self):
        self.client.activate.return_value = LicenseResponse(True, token=None)
        with patch('licensing.license_manager.get_device_label', return_value='fixture'):
            self.assertFalse(self.manager.activate('fixture')[0])

    def test_no_periodic_expiry_but_subscription_expiry_is_enforced(self):
        self.assertEqual(self.manager._verify_access_internal()[0], LicenseStatus.VALID)
        now = time.monotonic()
        with patch('licensing.license_manager.time.monotonic', return_value=now + 301):
            self.assertTrue(self.manager.has_online_access())
        with patch('licensing.license_manager.time.monotonic', return_value=self.manager._online_until):
            self.assertFalse(self.manager.has_online_access())
        self.assertFalse(hasattr(self.manager, 'start_runtime_monitor'))

    def test_concurrent_ui_requests_use_one_worker_and_gui_callbacks(self):
        values = []
        loop = QEventLoop()
        def done(status, error):
            values.append((status, QThread.currentThread() == self.app.thread()))
            if len(values) == 2:
                QTimer.singleShot(10, loop.quit)
        self.manager.verify_access_async(done)
        self.manager.verify_access_async(done)
        QTimer.singleShot(3000, loop.quit)
        loop.exec()
        for worker in list(self.manager._verify_workers):
            worker.wait(3000)
        self.app.processEvents()
        self.assertEqual(values, [(LicenseStatus.VALID, True)]*2)
        self.assertEqual(self.client.refresh.call_count, 1)
        self.assertFalse(self.manager._verify_workers)

    def test_actions_run_before_check_and_ignore_double_clicks(self):
        callbacks = []
        manager = Mock()
        manager.verify_access_async.side_effect = callbacks.append
        manager.has_online_access.return_value = True
        class View:
            count = 0
            @online_action
            def start(self): self.count += 1
        view = View()
        with patch('licensing.access._manager', manager):
            view.start(); view.start()
            self.assertEqual(view.count, 1)
            self.assertEqual(len(callbacks), 1)
            callbacks.pop()(LicenseStatus.NETWORK_ERROR, 'offline')
            self.assertEqual(view.count, 1)
            view.start()
            callbacks.pop()(LicenseStatus.VALID, None)
            self.assertEqual(view.count, 2)

    def test_client_understands_fastapi_rejection(self):
        client = LicenseClient.__new__(LicenseClient)
        client.base_url = 'https://example.invalid'
        client._post_with_retry = Mock(return_value=Mock(status_code=403,
            json=lambda: {'detail': {'error_code':'DEVICE_DEACTIVATED','error':'revoked'}}))
        self.assertEqual(client.refresh('fixture','fixture').error_code, 'DEVICE_DEACTIVATED')

    def test_map_verifies_after_mutation_and_preserves_response(self):
        source = Path('server/map_server.py').read_text(encoding='utf-8-sig')
        node = next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='verify_license_after_action')
        node.decorator_list = []
        namespace = dict(request=types.SimpleNamespace(method='PATCH',path='/api/sign/fixture'))
        exec(compile(ast.Module(body=[node],type_ignores=[]),'map-guard','exec'),namespace)
        self.client.refresh.return_value = LicenseResponse(False,error_code='CONNECTION_ERROR')
        response = types.SimpleNamespace(status_code=200)
        with patch('licensing.access._manager',self.manager):
            self.assertIs(namespace['verify_license_after_action'](response), response)
        self.client.refresh.assert_called_once()
        self.assertFalse(self.manager.has_online_access())


if __name__ == '__main__': unittest.main()
