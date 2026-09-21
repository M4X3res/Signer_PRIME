"""Generate Inno Setup constants from the actual prepared release."""
import json
import re
import hashlib
from pathlib import Path


def generate(current: Path, release: Path):
    version = json.loads((current/'version.json').read_text(encoding='utf-8-sig'))['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:\.\d+)?', version):
        raise ValueError('Installer requires a numeric three/four-component version')
    for name in ('Signer.exe', 'Updater.exe', '7z.exe', '7z.dll', 'manifest.json'):
        if not (current/name).is_file():
            raise ValueError(f'Missing installation component: {name}')
    parts = sorted(release.glob('Signer.7z.*'))
    if not parts or [p.name for p in parts] != [f'Signer.7z.{i:03d}' for i in range(1,len(parts)+1)]:
        raise ValueError('Archive volumes are missing or not sequential')
    if any(p.stat().st_size == 0 for p in parts):
        raise ValueError('Empty archive volume')
    sizes = [p.stat().st_size for p in parts]
    extracted = sum(p.stat().st_size for p in current.rglob('*') if p.is_file())
    constants = (f'#define AppVersion "{version}"\n'
                 f'#define RELEASE_TAG "v{version}"\n'
                 f'#define SIGNER_PART_COUNT {len(parts)}\n'
                 f'#define SIGNER_DISK_SPACE {sum(sizes)+2*extracted+500_000_000}\n')
    (release/'installer_release.iss').write_text(constants,encoding='utf-8')
    cases = '\n'.join(f'    {i}: Result := {size};' for i,size in enumerate(sizes,1))
    (release/'installer_sizes.iss').write_text('  case PartIndex of\n'+cases+'\n  else\n    Result := 0;\n  end;\n',encoding='utf-8')
    downloads = []
    for part, size in zip(parts, sizes):
        h = hashlib.sha256()
        with part.open('rb') as stream:
            for block in iter(lambda: stream.read(1024*1024), b''):
                h.update(block)
        downloads.append(f'Source: "{{#RELEASE_BASE_URL}}/{part.name}"; DestDir: "{{code:GetWorkDir}}"; '
                         f'DestName: "{part.name}"; ExternalSize: {size}; Hash: "{h.hexdigest()}"; '
                         'Flags: external download ignoreversion uninsneveruninstall')
    downloads.append('Source: "{#RELEASE_BASE_URL}/checksum.sha256"; DestDir: "{code:GetWorkDir}"; '
                     'DestName: "checksum.sha256"; ExternalSize: 2048; '
                     'Flags: external download ignoreversion uninsneveruninstall; AfterInstall: PreparePayload')
    (release/'installer_downloads.iss').write_text('\n'.join(downloads)+'\n',encoding='utf-8')
    payload = []
    for path in sorted(current.rglob('*')):
        if not path.is_file():
            continue
        relative = path.relative_to(current)
        if any(c in str(relative) for c in ('"', '{', '}', '\n', '\r')):
            raise ValueError(f'Unsupported installer filename: {relative}')
        parent = str(relative.parent).replace('/', '\\')
        suffix = '' if parent == '.' else '\\'+parent
        payload.append(f'Source: "{{code:GetWorkDir}}\\Signer_payload\\Signer\\{relative}"; '
                       f'DestDir: "{{app}}\\Signer{suffix}"; ExternalSize: {path.stat().st_size}; '
                       'Flags: external ignoreversion uninsrestartdelete')
    (release/'installer_payload.iss').write_text('\n'.join(payload)+'\n',encoding='utf-8')


if __name__ == '__main__':
    generate(Path('dist/Signer'),Path('release'))
