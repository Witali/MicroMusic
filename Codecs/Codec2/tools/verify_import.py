#!/usr/bin/env python3
"""Verify the immutable Codec2 import against every original ZIP and Git blob.

Only Python's standard library is required. This command does not run archive
scripts, compile firmware, or write files.
"""
import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def verify(git_ref=None):
    manifest = json.loads((ROOT / 'IMPORT_MANIFEST.json').read_text(encoding='utf-8'))
    original = (ROOT / manifest['original_archive_path']).read_bytes()
    require(sha256(original) == manifest['archive_sha256'], 'Original ZIP hash differs')
    archives = {}
    inventory = []
    reports = []

    def inspect(data, chain):
        z = zipfile.ZipFile(io.BytesIO(data))
        archives[tuple(chain)] = z
        names = z.namelist()
        require(len(set(n.casefold() for n in names)) == len(names), f'Duplicate paths: {chain}')
        inventory.append({'archive_chain': chain, 'sha256': sha256(data), 'entries': len(names)})
        for info in z.infolist():
            name = info.filename
            p = PurePosixPath(name)
            require(not p.is_absolute() and '..' not in p.parts and '\\' not in name and ':' not in name,
                    f'Unsafe archive path: {name}')
            require(p.suffix.lower() not in ('.mid', '.midi', '.smf'), f'MIDI source: {name}')
            require('.git' not in p.parts, f'Unexpected Git metadata: {name}')
            payload = z.read(info)  # Also checks CRC for entries without a SHA256SUMS record.
            if name.endswith('SHA256SUMS.txt'):
                prefix = name[:-len('SHA256SUMS.txt')]
                report = {'archive_chain': chain, 'path': name, 'matched': 0,
                          'missing': [], 'mismatched': []}
                for line in payload.decode().splitlines():
                    expected, rel = line.split(None, 1)
                    rel = rel.lstrip('*')
                    full = prefix + rel
                    if full not in names:
                        report['missing'].append(rel)
                    elif sha256(z.read(full)) != expected:
                        report['mismatched'].append(rel)
                    else:
                        report['matched'] += 1
                reports.append(report)
            if name.lower().endswith('.zip'):
                inspect(payload, chain + [name])

    inspect(original, [])
    require(inventory == manifest['archive_inventory'], 'Nested ZIP inventory differs')
    require(reports == manifest['original_checksum_reports'], 'Original SHA256SUMS results differ')
    require(all(not report['mismatched'] for report in reports), 'Original checksum mismatch')
    blobs = {manifest['original_archive_path']: original}
    mapped = {}
    for entry in manifest['retained']:
        name = entry['path']
        require(name not in blobs, f'Duplicate retained path: {name}')
        z = archives[tuple(entry['archive_chain'])]
        payload = z.read(entry['entry'])
        require(len(payload) == entry['bytes'] and sha256(payload) == entry['sha256'],
                f'Manifest hash/size differs: {name}')
        require(list(z.getinfo(entry['entry']).date_time) == entry['zip_timestamp'],
                f'ZIP timestamp differs: {name}')
        require((ROOT / name).read_bytes() == payload, f'Working file differs: {name}')
        mapped.setdefault(entry['stage'], []).append(entry)
        blobs[name] = payload

    for stage in manifest['stages']:
        chain = stage['source_archive_chain']
        prefix = stage['source_prefix']
        expected = []
        for info in archives[tuple(chain)].infolist():
            name = info.filename
            if info.is_dir() or not name.startswith(prefix):
                continue
            if stage['id'] == 'continuation-r3' and name.startswith('Codec2_Tiny13_Quality_R2/'):
                continue
            expected.append((name, stage['path'] + '/' + name[len(prefix):]))
        actual = mapped.get(stage['id'], [])
        require(Counter(expected) == Counter((e['entry'], e['path']) for e in actual),
                f'Incomplete stage: {stage["id"]}')
        require(len(actual) == stage['files'], f'Stage count differs: {stage["id"]}')
        require(all(e['archive_chain'] == chain for e in actual), f'Stage source differs: {stage["id"]}')
    require(set(mapped) == {s['id'] for s in manifest['stages']}, 'Unknown retained stage')
    baseline = archives[('BASELINE_R2_UNMODIFIED.zip',)]
    outer = archives[()]
    require(set(baseline.namelist()) == {n for n in outer.namelist()
                                       if n.startswith('Codec2_Tiny13_Quality_R2/')}, 'R2 paths differ')
    require(all(baseline.read(n) == outer.read(n) for n in baseline.namelist()), 'R2 bytes differ')
    require(manifest['r2_expanded_matches_baseline_zip'] is True, 'R2 comparison not recorded')

    if git_ref:
        ordered = sorted(blobs)
        requests = ''.join(f'{git_ref}:Codecs/Codec2/{name}\n' for name in ordered).encode('utf-8')
        result = subprocess.run(['git', '-C', str(ROOT), 'cat-file', '--batch'], input=requests,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        stream = io.BytesIO(result.stdout)
        for name in ordered:
            header = stream.readline().split()
            require(len(header) == 3 and header[1] == b'blob', f'Git blob missing: {name}')
            size = int(header[2])
            require(stream.read(size) == blobs[name], f'Git bytes differ: {name}')
            require(stream.read(1) == b'\n', 'Invalid Git batch response')
        require(not stream.read(), 'Extra Git batch data')

    print(f'PASS: {len(manifest["stages"])} stages, {len(manifest["retained"])} extracted files, '
          f'{len(inventory)} ZIP occurrences, {sum(i["entries"] for i in inventory)} archive entries.')
    print('PASS: original ZIP, complete stage coverage, SHA-256/CRC, and identical R2 copies.')
    if git_ref:
        print(f'PASS: {len(blobs)} committed blobs match the original archive at {git_ref}.')
    missing = {name for report in reports for name in report['missing']}
    print(f'Known source omission: {len(missing)} R1 Python cache files listed but absent in its ZIP.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--git-ref', help='Also compare committed bytes, for example HEAD')
    args = parser.parse_args()
    try:
        verify(args.git_ref)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        parser.exit(1, f'FAIL: {error}\n')
