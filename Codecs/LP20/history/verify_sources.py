"""Verify recovered source bytes without importing or executing historical code."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def git(*args):
    try:
        return subprocess.check_output(['git', *args], cwd=REPO, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        if str(REPO).startswith('/mnt/'):
            windows = str(REPO)[5].upper() + ':/' + str(REPO)[7:]
            return subprocess.check_output(['git.exe', '-C', windows, *args], stderr=subprocess.DEVNULL)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--index', action='store_true', help='Also verify all original source blobs in the Git index')
    mode.add_argument('--staged-only', action='store_true', help='Verify only staged snapshot blobs against the manifests')
    args = parser.parse_args()
    expected = {}
    counts = {}
    for version in ('v19', 'v45', 'v49', 'v51', 'v52'):
        directory = HERE / 'snapshots' / version
        manifest = directory / 'SOURCE.json'
        record = json.loads(manifest.read_text(encoding='utf-8'))
        names = set()
        for item in record['files']:
            relative = PurePosixPath(item['path'])
            if relative.is_absolute() or '..' in relative.parts or '\\' in item['path'] or ':' in item['path']:
                raise ValueError('Unsafe manifest path')
            path = directory.joinpath(*relative.parts)
            data = path.read_bytes()
            if len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256']:
                raise ValueError('Original source hash mismatch: ' + version + '/' + item['path'])
            name = path.relative_to(REPO).as_posix()
            if name in expected:
                raise ValueError('Duplicate source entry')
            expected[name] = data
            names.add(item['path'])
        actual = {p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file()}
        if actual != names | {'SOURCE.json'}:
            raise ValueError('Unexpected or missing snapshot file: ' + version)
        expected[manifest.relative_to(REPO).as_posix()] = manifest.read_bytes()
        counts[version] = len(names)
    checked = 0
    if args.index or args.staged_only:
        selected = set(expected)
        if args.staged_only:
            staged = git('diff', '--cached', '--name-only', '-z').decode().split('\0')
            prefix = (HERE / 'snapshots').relative_to(REPO).as_posix() + '/'
            selected = {name for name in staged if name.startswith(prefix)}
            if not selected <= set(expected):
                raise ValueError('Unexpected staged snapshot file')
        for name in sorted(selected):
            if git('show', ':' + name) != expected[name]:
                raise ValueError('Git blob differs from verified source: ' + name)
            checked += 1
    print(json.dumps(dict(original_files=sum(counts.values()), provenance_manifests=len(counts),
                          snapshots=counts, index_blobs_checked=checked, status='PASS'), indent=2))


if __name__ == '__main__':
    main()
