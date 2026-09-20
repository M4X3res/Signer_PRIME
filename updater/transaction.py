"""Validated, reversible file updates. Uses only the standard library."""
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path, PureWindowsPath


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def safe_path(root, name):
    win = PureWindowsPath(name)
    if not name or win.is_absolute() or win.drive or ':' in name or '\\' in name:
        raise ValueError(f'Invalid update path: {name}')
    if any(p in ('', '.', '..') or p.endswith((' ', '.')) for p in name.split('/')):
        raise ValueError(f'Invalid update path: {name}')
    target = root.joinpath(*name.split('/'))
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError(f'Update path escapes installation: {name}')
    return target


def inventory(root):
    return {p.relative_to(root).as_posix(): digest(p) for p in sorted(root.rglob('*'))
            if p.is_file() and p.name != 'manifest.json'}


def validate_files(root, files):
    for name, expected in files.items():
        path = safe_path(root, name)
        if not path.is_file() or digest(path) != expected:
            raise ValueError(f'File differs from manifest: {name}')


def install_files(source, install, changed, removed, target_files):
    """Rollback replacements, deletions and additions on any caught failure."""
    names = list(changed) + list(removed)
    if len({n.casefold() for n in names}) != len(names):
        raise ValueError('Duplicate update paths')
    targets = {n: safe_path(install, n) for n in names}
    for n in changed:
        if not safe_path(source, n).is_file():
            raise ValueError(f'Missing update file: {n}')
    backup = Path(tempfile.mkdtemp(prefix='signer-backup-', dir=install.parent))
    previous = set()
    touched = []
    try:
        for n, path in targets.items():
            if path.exists():
                saved = safe_path(backup, n)
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, saved)
                previous.add(n)
        for n in changed:
            path = targets[n]
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, staging = tempfile.mkstemp(prefix='.signer-update-', dir=path.parent)
            os.close(fd)
            try:
                shutil.copy2(safe_path(source, n), staging)
                touched.append(n)
                os.replace(staging, path)
            finally:
                Path(staging).unlink(missing_ok=True)
        for n in removed:
            touched.append(n)
            targets[n].unlink(missing_ok=True)
        validate_files(install, target_files)
    except Exception:
        try:
            for n in reversed(touched):
                if n in previous:
                    shutil.copy2(safe_path(backup, n), targets[n])
                else:
                    targets[n].unlink(missing_ok=True)
        except Exception as error:
            raise RuntimeError(f'Rollback incomplete; backup retained at {backup}') from error
        shutil.rmtree(backup)
        raise
    shutil.rmtree(backup)


def install_release(source, install, changed, removed, target_files, version):
    """Commit the installed file list in the same rollback transaction."""
    manifest = source / 'manifest.json'
    manifest.write_text(json.dumps({'version': version, 'files': target_files}), encoding='utf-8')
    install_files(source, install, list(changed) + ['manifest.json'], removed,
                  {**target_files, 'manifest.json': digest(manifest)})


def apply_full(source, install, manifest):
    target = manifest['files']
    validate_files(source, target)
    version = json.loads((source/'version.json').read_text(encoding='utf-8-sig'))['version']
    if version != manifest['version']:
        raise ValueError('Full update target version mismatch')
    previous = {}
    if (install/'version.json').exists():
        current = json.loads((install/'version.json').read_text(encoding='utf-8-sig'))['version']
        previous = manifest.get('previous_files', {}).get(current)
        if previous is None and (install/'manifest.json').exists():
            installed = json.loads((install/'manifest.json').read_text(encoding='utf-8-sig'))
            if installed.get('version') == current:
                previous = installed['files']
        if previous is None:
            raise ValueError('No file inventory for installed version; prepare release with its baseline')
    removed = sorted(set(previous) - set(target))
    # Never silently discard a locally changed file absent from the new release.
    for name in removed:
        path = safe_path(install, name)
        if path.exists() and (not path.is_file() or digest(path) != previous[name]):
            raise ValueError(f'Obsolete file was modified locally: {name}')
    install_release(source, install, target, removed, target, version)


def apply_delta(temp, manifest_path, install):
    data = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    current = json.loads((install/'version.json').read_text(encoding='utf-8-sig'))['version']
    if current != data['from_version']:
        raise ValueError('Delta source version does not match installation')
    validate_files(install, data['source_files'])
    archive = safe_path(temp, f"delta-from-{data['from_version']}.zip")
    if digest(archive) != data['archive_sha256']:
        raise ValueError('Delta checksum mismatch')
    changed, removed = data['changed_or_added'], data['removed']
    target = data['target_files']
    expected_changed = {n for n,h in target.items() if data['source_files'].get(n) != h}
    if set(changed) != expected_changed or set(removed) != set(data['source_files']) - set(target):
        raise ValueError('Delta manifest has inconsistent file lists')
    with tempfile.TemporaryDirectory(prefix='signer-delta-', dir=temp) as directory:
        extracted = Path(directory)
        with zipfile.ZipFile(archive) as zf:
            if sorted(zf.namelist()) != sorted(changed):
                raise ValueError('Delta archive contents differ from manifest')
            for name in zf.namelist():
                path = safe_path(extracted, name)
                path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(name) as source, path.open('wb') as destination:
                    shutil.copyfileobj(source, destination)
        validate_files(extracted, {n: target[n] for n in changed})
        version_file = extracted/'version.json' if 'version.json' in changed else install/'version.json'
        if json.loads(version_file.read_text(encoding='utf-8-sig'))['version'] != data['to_version']:
            raise ValueError('Delta target version mismatch')
        install_release(extracted, install, changed, removed, target, data['to_version'])
