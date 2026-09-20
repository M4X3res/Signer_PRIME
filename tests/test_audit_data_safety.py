import ast
import concurrent.futures
import json
import logging
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.json_store import atomic_write_json, serialized_edit
from tests.test_audit_regressions import load_methods


class DataSafetyTests(unittest.TestCase):
    def test_failed_write_preserves_original_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'data.json'
            path.write_text('{"old": true}')
            for failure in ('json.dump', 'os.replace'):
                with patch('app.json_store.' + failure, side_effect=OSError('disk full')):
                    with self.assertRaises(OSError):
                        atomic_write_json(path, {'new': True})
                self.assertEqual(json.loads(path.read_text()), {'old': True})
                self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_concurrent_edits_keep_every_change(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'data.json'
            atomic_write_json(path, [])
            start = threading.Barrier(8)
            @serialized_edit
            def edit(value):
                data = json.loads(path.read_text())
                data.append(value)
                atomic_write_json(path, data)
            def run(value):
                start.wait(timeout=5)
                edit(value)
            with concurrent.futures.ThreadPoolExecutor(8) as pool:
                list(pool.map(run, range(8)))
            self.assertEqual(sorted(json.loads(path.read_text())), list(range(8)))
        tree = ast.parse(Path('server/map_server.py').read_text(encoding='utf-8-sig'))
        for name in ('api_sign_create', 'api_sign_update', 'api_sign_delete'):
            node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
            self.assertTrue(any(isinstance(d, ast.Name) and d.id == 'serialized_edit' for d in node.decorator_list))

    def test_bad_checkpoint_does_not_change_configuration(self):
        cfg = types.SimpleNamespace(INDEX_OF_FRAME=10, INDEX_OF_VIDEO=0)
        method = load_methods('processing/processing_controller.py', 'ProcessingController',
                              ['load_checkpoint'], config=cfg, logging=logging).load_checkpoint
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'checkpoint.pkl'
            path.touch()
            obj = types.SimpleNamespace(CHECKPOINT_PATH=str(path))
            with patch('joblib.load', return_value={'config': {'INDEX_OF_FRAME': 999}}):
                self.assertFalse(method(obj))
            self.assertEqual(vars(cfg), {'INDEX_OF_FRAME': 10, 'INDEX_OF_VIDEO': 0})
            self.assertFalse(obj._resume_from_checkpoint)

    def test_close_waits_for_actual_thread_after_controller_stops(self):
        timer = Mock()
        method = load_methods('ui/main_window.py', 'MainWindow', ['closeEvent'], QTimer=timer).closeEvent
        worker = Mock()
        worker.isRunning.return_value = True
        controller = Mock(is_running=False, _reader=None, _detector=worker, _detector_pool=None)
        window = types.SimpleNamespace(_controller=controller, page_errors=Mock(), page_map=Mock(), close=Mock())
        event = Mock()
        method(window, event)
        event.ignore.assert_called_once()
        event.accept.assert_not_called()
        controller.finish_and_save.assert_called_once()
        worker.wait.assert_not_called()
        worker.isRunning.return_value = False
        method(window, event)
        event.accept.assert_called_once()

    def test_update_extraction_uses_download_volume(self):
        for file, prefix, expected in (
                ('updater/transaction.py', 'signer-delta-', 'temp'),
                ('updater/updater_main.py', 'signer-full-', 'temp_dir')):
            tree = ast.parse(Path(file).read_text(encoding='utf-8-sig'))
            calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Attribute) and n.func.attr == 'TemporaryDirectory']
            call = next(n for n in calls if any(k.arg == 'prefix' and isinstance(k.value, ast.Constant)
                        and k.value.value == prefix for k in n.keywords))
            self.assertTrue(any(k.arg == 'dir' and isinstance(k.value, ast.Name)
                                and k.value.id == expected for k in call.keywords))
        from updater.updater import get_update_temp_dir
        with patch('sys.frozen', True, create=True), patch('sys.executable', str(Path('test-install/Signer.exe').resolve())):
            self.assertEqual(get_update_temp_dir().parent, Path('test-install').resolve())

    def test_update_folder_denial_is_reported(self):
        method = load_methods('ui/widgets/update_dialog.py', 'UpdateDialog',
                              ['_start_download'], logger=Mock())._start_download
        folder = Mock()
        folder.mkdir.side_effect = PermissionError('access denied')
        dialog = types.SimpleNamespace(_is_retry=True, temp_dir=folder,
                                       _on_download_error=Mock(), _show_progress_state=Mock())
        method(dialog)
        dialog._on_download_error.assert_called_once()
        dialog._show_progress_state.assert_not_called()


if __name__ == '__main__':
    unittest.main()
