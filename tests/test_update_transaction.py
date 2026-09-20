import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.build.build_delta import build
from updater.transaction import apply_delta, apply_full, digest, install_files, inventory, safe_path
from updater.updater import verify_checksum


class UpdateTests(unittest.TestCase):
    def test_timeout_never_starts_installation(self):
        from updater import updater_main
        from unittest.mock import Mock
        args = ['Updater', '--pid', '123', '--temp', 'temp', '--install', 'install',
                '--exe', 'Signer.exe', '--7z', '7z.exe']
        with patch('sys.argv', args), patch.object(updater_main, 'setup_logging', return_value=Mock()), \
                patch.object(updater_main, 'wait_for_process_exit', return_value=False), \
                patch.object(updater_main, 'show_error_messagebox'), \
                patch.object(updater_main, 'extract_update') as extract, \
                patch.object(updater_main, 'apply_delta_update') as delta, \
                patch.object(updater_main.subprocess, 'Popen') as launch:
            with self.assertRaises(SystemExit) as error:
                updater_main.main()
            self.assertEqual(error.exception.code, 1)
            extract.assert_not_called()
            delta.assert_not_called()
            launch.assert_not_called()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.old, self.new, self.release = [self.root/n for n in ('old','new','release')]
        self.old.mkdir(); self.new.mkdir()
        for directory, version in ((self.old,'1.0.0'), (self.new,'1.0.1')):
            (directory/'version.json').write_text(json.dumps({'version':version}))
            (directory/'model.bin').write_bytes(b'unchanged weights')
            (directory/'Signer.exe').write_bytes(version.encode())
        (self.old/'removed.txt').write_text('old')
        (self.new/'added.txt').write_text('new')
        build(self.new,self.release,[self.old])

    def test_delta_excludes_unchanged_model_and_installs(self):
        import zipfile
        with zipfile.ZipFile(self.release/'delta-from-1.0.0.zip') as archive:
            self.assertNotIn('model.bin',archive.namelist())
        apply_delta(self.release,self.release/'delta-from-1.0.0.json',self.old)
        self.assertEqual(inventory(self.old),inventory(self.new))

    def test_modified_installation_is_rejected(self):
        (self.old/'model.bin').write_bytes(b'changed locally')
        before=inventory(self.old)
        with self.assertRaises(ValueError):
            apply_delta(self.release,self.release/'delta-from-1.0.0.json',self.old)
        self.assertEqual(before,inventory(self.old))

    def test_full_update_removes_only_old_release_files(self):
        (self.old/'user.geojson').write_text('user results')
        manifest = json.loads((self.release/'manifest.json').read_text())
        apply_full(self.new, self.old, manifest)
        self.assertFalse((self.old/'removed.txt').exists())
        self.assertEqual((self.old/'user.geojson').read_text(), 'user results')
        self.assertEqual(json.loads((self.old/'manifest.json').read_text())['version'], '1.0.1')

    def test_full_update_rollback_restores_removed_files_and_manifest(self):
        manifest = json.loads((self.release/'manifest.json').read_text())
        (self.old/'manifest.json').write_text('previous inventory')
        before = inventory(self.old)
        from updater.transaction import validate_files
        def fail_after_install(root, files):
            if root == self.old:
                raise OSError('validation failed')
            validate_files(root, files)
        with patch('updater.transaction.validate_files', side_effect=fail_after_install):
            with self.assertRaises(OSError):
                apply_full(self.new, self.old, manifest)
        self.assertEqual(inventory(self.old), before)
        self.assertEqual((self.old/'manifest.json').read_text(), 'previous inventory')

    def test_full_update_does_not_delete_locally_modified_obsolete_file(self):
        (self.old/'removed.txt').write_text('local edits')
        before = inventory(self.old)
        with self.assertRaises(ValueError):
            apply_full(self.new, self.old, json.loads((self.release/'manifest.json').read_text()))
        self.assertEqual(inventory(self.old), before)

    def test_missing_baseline_fails_before_modifying_installation(self):
        before = inventory(self.old)
        manifest = json.loads((self.release/'manifest.json').read_text())
        manifest.pop('previous_files')
        with self.assertRaises(ValueError):
            apply_full(self.new, self.old, manifest)
        self.assertEqual(inventory(self.old), before)

    def test_full_update_can_use_installed_inventory(self):
        manifest = json.loads((self.release/'manifest.json').read_text())
        (self.old/'manifest.json').write_text(json.dumps({
            'version': '1.0.0', 'files': manifest['previous_files']['1.0.0']}))
        manifest.pop('previous_files')
        apply_full(self.new, self.old, manifest)
        self.assertFalse((self.old/'removed.txt').exists())

    def test_rollback_restores_deleted_and_removes_added(self):
        before=inventory(self.old)
        with patch('updater.transaction.validate_files',side_effect=ValueError('injected failure')):
            with self.assertRaises(ValueError):
                install_files(self.new,self.old,['Signer.exe','added.txt'],['removed.txt'],{})
        self.assertEqual(before,inventory(self.old))

    def test_paths_cannot_escape(self):
        for name in ('../outside','C:/outside','a/../../outside','a\\b','a:stream','/outside'):
            with self.subTest(name=name),self.assertRaises(ValueError):
                safe_path(self.old,name)

    def test_full_archive_root_is_not_nested_in_installation(self):
        import shutil
        from types import SimpleNamespace
        from updater.updater_main import extract_update
        (self.release/'Signer.7z.001').write_bytes(b'fixture')
        sevenzip=self.root/'7z.exe';sevenzip.write_bytes(b'fixture')
        def extract(command, **kwargs):
            destination=Path(next(arg[2:] for arg in command if arg.startswith('-o')))
            shutil.copytree(self.new,destination/'Signer')
            return SimpleNamespace(returncode=0,stdout='',stderr='')
        with patch('updater.updater_main.subprocess.run',side_effect=extract):
            self.assertTrue(extract_update(self.release,self.old,sevenzip))
        self.assertEqual((self.old/'Signer.exe').read_bytes(),b'1.0.1')
        self.assertFalse((self.old/'Signer').exists())

    def test_replacement_failure_rolls_back(self):
        import os
        original=os.replace
        before=inventory(self.old)
        def fail_second(source, target):
            if Path(target).name=='added.txt':
                raise PermissionError('locked file')
            return original(source,target)
        with patch('updater.transaction.os.replace',side_effect=fail_second):
            with self.assertRaises(PermissionError):
                install_files(self.new,self.old,['Signer.exe','added.txt'],[],{})
        self.assertEqual(before,inventory(self.old))

    def test_corrupt_archive_rejected(self):
        (self.release/'delta-from-1.0.0.zip').write_bytes(b'broken')
        before=inventory(self.old)
        with self.assertRaises(ValueError):
            apply_delta(self.release,self.release/'delta-from-1.0.0.json',self.old)
        self.assertEqual(before,inventory(self.old))

    def test_missing_full_volume_rejected_and_bom_supported(self):
        (self.release/'checksum.sha256').write_text('0'*64+'  Signer.7z.001',encoding='utf-8-sig')
        self.assertFalse(verify_checksum(self.release))
        volume=self.release/'Signer.7z.001';volume.write_bytes(b'archive')
        (self.release/'checksum.sha256').write_text(digest(volume)+'  Signer.7z.001',encoding='utf-8-sig')
        self.assertTrue(verify_checksum(self.release))


if __name__=='__main__': unittest.main()

