"""Compile/run a tiny local-only installer to verify target-disk downloads."""
import hashlib
import http.server
import subprocess
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ISCC = Path(r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe')


def main():
    with tempfile.TemporaryDirectory(prefix='signer-installer-test-') as directory:
        root = Path(directory)
        target = root/'chosen target with spaces'
        data = b'local installer test payload\n' * 100
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            def log_message(self, *args):
                pass
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            script = root/'fixture.iss'
            script.write_text(f'''
[Setup]
AppName=Signer Workspace Test
AppVersion=0.0.0
DefaultDirName={target}
OutputDir={root}
OutputBaseFilename=workspace-test
PrivilegesRequired=lowest
Uninstallable=no
CreateUninstallRegKey=no
DisableProgramGroupPage=yes
DisableWelcomePage=yes
[Files]
Source: "http://127.0.0.1:{server.server_port}/payload"; DestDir: "{{code:GetWorkDir}}"; DestName: "download.bin"; ExternalSize: {len(data)}; Hash: "{hashlib.sha256(data).hexdigest()}"; Flags: external download ignoreversion; AfterInstall: PreparePayload
Source: "{{code:GetWorkDir}}\\staged.bin"; DestDir: "{{app}}"; DestName: "installed.bin"; ExternalSize: {len(data)}; Flags: external ignoreversion
[Code]
#include "{ROOT / 'installer/DiskWorkspace.iss'}"
procedure PreparePayload;
begin
  if not CopyFile(GetWorkDir('') + '\\download.bin', GetWorkDir('') + '\\staged.bin', False) then
    RaiseException('Staging failed');
  SaveStringToFile(ExpandConstant('{{app}}\\workspace-path.txt'), GetWorkDir(''), False);
end;
''', encoding='utf-8-sig')
            result = subprocess.run([str(ISCC), str(script)], capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError(result.stdout + result.stderr)
            run = subprocess.run([str(root/'workspace-test.exe'), '/VERYSILENT', '/SUPPRESSMSGBOXES',
                                  '/NORESTART', f'/LOG={root / "install.log"}'], timeout=60)
            if run.returncode:
                raise RuntimeError((root/'install.log').read_text(encoding='utf-8-sig',errors='replace'))
            assert (target/'installed.bin').read_bytes() == data
            workspace = Path((target/'workspace-path.txt').read_text())
            assert workspace.parent.resolve() == target.resolve(), workspace
            assert not workspace.exists(), 'Workspace not cleaned'
            print('PASS: native HTTP download and staging on chosen target, installed bytes match, workspace removed')
            data = b'corrupted payload'
            failed_target = root/'failed target'
            failed = subprocess.run([str(root/'workspace-test.exe'), '/VERYSILENT', '/SUPPRESSMSGBOXES',
                                     '/NORESTART', f'/DIR={failed_target}', f'/LOG={root / "failure.log"}'], timeout=60)
            assert failed.returncode != 0, 'Checksum error accepted'
            assert not (failed_target/'installed.bin').exists()
            assert not list(failed_target.glob('sgn*.tmp')), 'Failed download workspace not cleaned'
            print('PASS: corrupt download rejected and workspace cleaned on failure')
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    main()
