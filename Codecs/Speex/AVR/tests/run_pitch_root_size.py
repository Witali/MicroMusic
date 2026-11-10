#!/usr/bin/env python3
"""Freeze and compare the finite pitch lookup in complete ASM images only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--avr-gcc', required=True)
    parser.add_argument('--node', required=True)
    parser.add_argument('--wb-corpus', type=Path)
    parser.add_argument('--nb-corpus', type=Path)
    parser.add_argument('--out', type=Path, default=ROOT / 'build/pitch-root-reproduce')
    parser.add_argument('--scalar-reference', type=Path, default=ROOT / 'build/nb1-pitch-unit')
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    out = args.out.resolve()
    if not out.is_relative_to((ROOT / 'build').resolve()):
        raise ValueError('Output must stay under the codec build directory')
    if not args.prepare_only and not (args.wb_corpus and args.nb_corpus):
        parser.error('Both independent corpus directories are required')
    if not args.scalar_reference.is_dir():
        parser.error('Build/verify the four isolated nb1-pitch-unit fixtures first')
    shutil.copytree(ROOT / 'tests/pitch-root-size', out)
    source = out / 'source'
    for part in ['src', 'tools', 'vendor', 'patches', 'handoff', 'tests']:
        if (ROOT / part).is_dir():
            shutil.copytree(ROOT / part, source / part, ignore=shutil.ignore_patterns('__pycache__'))
    (source / 'reports').mkdir()
    shutil.copyfile(ROOT / 'reports/nb1-pitch-unit.json', source / 'reports/nb1-pitch-unit.json')
    shutil.copytree(args.scalar_reference, out / 'scalar-prior')
    files = sorted(path for path in source.rglob('*') if path.is_file())
    manifest = {path.relative_to(source).as_posix(): hashlib.sha256(
        path.read_bytes().replace(b'\r\n', b'\n')).hexdigest() for path in files}
    prior = json.loads((source / 'reports/nb1-pitch-unit.json').read_text())
    for name, digest in prior['sourceSha256'].items():
        assert manifest[name] == digest, name
    (out / 'source.json').write_text(json.dumps(dict(scope='Frozen source snapshot for paired ASM pitch-root controls',
        sourceHashConvention='SHA256 LF-normalized source bytes', sourceSha256=manifest), indent=2) + '\n', encoding='utf-8')
    if args.prepare_only:
        print('Prepared frozen source and finite scalar references; no decoder executed')
        return
    environment = dict(os.environ, AVR8JS_PACKAGE=str(ROOT / 'package.json'))
    subprocess.run([sys.executable, out / 'build_admission.py', '--avr-gcc', args.avr_gcc], check=True)
    subprocess.run([sys.executable, out / 'run_screen.py', '--node', args.node,
                    '--wb-corpus', args.wb_corpus, '--nb-corpus', args.nb_corpus], env=environment, check=True)
    print('Completed paired ASM PCM/reset/timing screens; isolated C primitives only')


if __name__ == '__main__':
    main()
