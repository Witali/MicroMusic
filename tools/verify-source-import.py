#!/usr/bin/env python3
"""Verify retained source bytes and historical import snapshots without executing them."""
import argparse
import ast
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--history', action='store_true', help='Also verify every imported Git snapshot')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    index = json.loads((ROOT / 'SOURCE_IMPORTS.json').read_text(encoding='utf-8'))
    syntax = 0
    for row in index['current_files']:
        path = ROOT / row['path']
        path.resolve().relative_to(ROOT.resolve())
        content = path.read_bytes()
        assert hashlib.sha256(content).hexdigest() == row['sha256'], row['path']
        assert path.suffix.lower() not in {'.mid', '.midi', '.smf', '.zip', '.o', '.elf', '.hex', '.bin'}, path
        if path.suffix == '.py':
            ast.parse(content, filename=row['path'])
            syntax += 1
    checked = []
    if args.history:
        for stage in index['stages']:
            mapping = json.loads(git('show', stage['commit'] + ':' + stage['source_map']))
            for row in mapping['files']:
                checked.append((stage['commit'] + ':' + row['path'], row['sha256']))
        queries = ''.join(name + '\n' for name, _ in checked).encode()
        result = subprocess.run(['git', '-C', str(ROOT), 'cat-file', '--batch'], input=queries, capture_output=True, check=True).stdout
        offset = 0
        for name, expected in checked:
            end = result.index(b'\n', offset)
            header = result[offset:end].split()
            assert len(header) == 3 and header[1] == b'blob', (name, header)
            size = int(header[2])
            content = result[end + 1:end + 1 + size]
            assert hashlib.sha256(content).hexdigest() == expected, name
            offset = end + 2 + size
        assert offset == len(result)
    summary = {
        'current_files': len(index['current_files']),
        'python_sources_parsed': syntax,
        'historical_stages': len(index['stages']) if args.history else 0,
        'historical_files_verified': len(checked),
        'pass': True,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
