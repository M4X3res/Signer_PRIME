import json
import tempfile
import unittest
from pathlib import Path
from scripts.build.installer_config import generate


class InstallerConfigTests(unittest.TestCase):
    def test_actual_version_and_volume_sizes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);current=root/'current';release=root/'release'
            current.mkdir();release.mkdir()
            (current/'version.json').write_text(json.dumps({'version':'2.3.4'}))
            for name in ('Signer.exe','Updater.exe','7z.exe','7z.dll','manifest.json'):
                (current/name).write_bytes(b'fixture')
            (release/'Signer.7z.001').write_bytes(b'12345')
            (release/'Signer.7z.002').write_bytes(b'123')
            generate(current,release)
            constants=(release/'installer_release.iss').read_text()
            self.assertIn('AppVersion "2.3.4"',constants)
            self.assertIn('SIGNER_PART_COUNT 2',constants)
            sizes=(release/'installer_sizes.iss').read_text()
            self.assertIn('1: Result := 5;',sizes)
            self.assertIn('2: Result := 3;',sizes)
            downloads=(release/'installer_downloads.iss').read_text()
            self.assertIn('DestDir: "{code:GetWorkDir}"',downloads)
            self.assertIn('AfterInstall: PreparePayload',downloads)
            self.assertIn('Hash: "',downloads)
            payload=(release/'installer_payload.iss').read_text()
            self.assertIn('{code:GetWorkDir}\\Signer_payload\\Signer\\Signer.exe',payload)
            self.assertNotIn('{tmp}',downloads+payload)
            (release/'Signer.7z.001').unlink()
            with self.assertRaises(ValueError): generate(current,release)


if __name__=='__main__': unittest.main()
