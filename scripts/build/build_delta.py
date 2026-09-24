"""Create a release inventory and deltas from preserved clean release builds."""
import argparse
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from updater.transaction import digest, inventory, FULL_UPDATE_ONLY_VERSIONS, REQUIRED_205_BASES


MAX_DELTA_BYTES = 1_900_000_000


def build(current, output, bases, previous_inventories=None):
    bases = list(bases)
    output.mkdir(parents=True, exist_ok=True)
    version = json.loads((current/'version.json').read_text(encoding='utf-8-sig'))['version']
    target = inventory(current)
    previous = dict(previous_inventories or {})
    previous.update({
        json.loads((base/'version.json').read_text(encoding='utf-8-sig'))['version']: inventory(base)
        for base in bases})
    if version == '2.0.5' and not REQUIRED_205_BASES.issubset(previous):
        raise ValueError('Release 2.0.5 requires preserved inventories for 2.0.3 and 2.0.4')
    manifest = {'version': version, 'files': target, 'previous_files': previous}
    (current/'manifest.json').write_text(json.dumps({'version': version, 'files': target}, indent=2), encoding='utf-8')
    (output/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    for base in bases:
        old_version = json.loads((base/'version.json').read_text(encoding='utf-8-sig'))['version']
        if old_version == version:
            raise ValueError('Source and target versions must differ')
        import re
        if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)*', old_version):
            raise ValueError('Invalid source version')
        if old_version in FULL_UPDATE_ONLY_VERSIONS:
            # Keep its inventory in manifest.previous_files for apply_full,
            # but remove stale delta assets that would trigger the broken client path.
            for suffix in ('.zip', '.json'):
                (output / f'delta-from-{old_version}{suffix}').unlink(missing_ok=True)
            print(f'{old_version}: full automatic update required by legacy launcher')
            continue
        source = inventory(base)
        changed = sorted(n for n,h in target.items() if source.get(n) != h)
        removed = sorted(set(source)-set(target))
        archive = output/f'delta-from-{old_version}.zip'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zf:
            for name in changed:
                zf.write(current/name, name)
        if archive.stat().st_size > MAX_DELTA_BYTES:
            archive.unlink()
            (output/f'delta-from-{old_version}.json').unlink(missing_ok=True)
            print(f'Delta from {old_version} exceeds the asset budget; use the full update')
            continue
        data = dict(from_version=old_version, to_version=version, source_files=source,
                    target_files=target, changed_or_added=changed, removed=removed,
                    archive_sha256=digest(archive))
        (output/f'delta-from-{old_version}.json').write_text(json.dumps(data, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--current', type=Path, default=Path('dist/Signer'))
    parser.add_argument('--output', type=Path, default=Path('release'))
    parser.add_argument('--inventories', type=Path, default=Path('release_inventories'))
    parser.add_argument('--bases', type=Path, default=Path('release_baselines'))
    args = parser.parse_args()
    version = json.loads((args.current/'version.json').read_text(encoding='utf-8-sig'))['version']
    import re
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)*', version):
        raise ValueError('Invalid target version')
    snapshot = args.bases/version
    if snapshot.exists() and inventory(snapshot) != inventory(args.current):
        raise ValueError('This version already has a different build; increment version.json')
    bases = [p for p in args.bases.iterdir() if p != snapshot and p.is_dir() and (p/'version.json').exists()] if args.bases.exists() else []
    previous = {}
    if args.inventories.exists():
        for path in args.inventories.glob('*.json'):
            data = json.loads(path.read_text(encoding='utf-8-sig'))
            if data['version'] == version:
                if data['files'] != inventory(args.current):
                    raise ValueError('Version already identifies another build; increment version.json')
            else:
                previous[data['version']] = data['files']
    build(args.current, args.output, bases, previous)
    if not snapshot.exists():
        import shutil
        args.bases.mkdir(parents=True, exist_ok=True)
        shutil.copytree(args.current, snapshot)
    print(f'Created manifest and {len(bases)} delta(s)')
