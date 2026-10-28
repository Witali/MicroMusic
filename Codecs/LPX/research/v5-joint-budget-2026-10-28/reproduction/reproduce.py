"""Restore exact study scripts and run them from their recorded ignored paths."""
from __future__ import annotations
import argparse
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import runpy
import sys

BUNDLE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def install(root, manifest):
    build = (root/'build').resolve()
    for name, item in manifest['assets'].items():
        source = BUNDLE/name
        target = (root/item['recorded_origin']).resolve()
        if not source.resolve().is_relative_to(BUNDLE) or not target.is_relative_to(build):
            raise ValueError('Reproduction asset path escapes its intended directory')
        if sha(source) != item['sha256']:
            raise ValueError('Reproduction asset hash mismatch: '+name)
        if target.exists():
            if not target.is_file() or sha(target) != item['sha256']:
                raise ValueError('Existing study asset differs; preserve it before installing: '+item['recorded_origin'])
        else:
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(source.read_bytes())


def verify(root, manifest):
    for name, item in manifest['assets'].items():
        if sha(BUNDLE/name) != item['sha256'] or sha(root/item['recorded_origin']) != item['sha256']:
            raise ValueError('Installed study asset hash mismatch: '+name)
    for name, expected in manifest['benchmark_source_inventory'].items():
        if sha(root/name) != expected:
            raise ValueError('Recorded benchmark source differs: '+name)
    for name, expected in manifest['packages'].items():
        if version(name) != expected:
            raise ValueError('Recorded package version differs: '+name)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path.cwd())
    parser.add_argument('action',choices=('install','verify','fit','audit'))
    parser.add_argument('--branch',choices=('full','lsf-only'),default='full')
    parser.add_argument('--shard',type=int,choices=(0,1,2),default=0)
    args=parser.parse_args()
    root=args.repo.resolve()
    if not (root/'Codecs/LPX/01_ACTIVE_Q0_CODEC/src/Lpx4HybridCore.cpp').is_file():
        raise ValueError('--repo must identify the repository root')
    manifest=json.loads((BUNDLE/'source-manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema')!='lpx-v5-study-reproduction-v1':
        raise ValueError('Unsupported reproduction manifest')
    if args.action=='install':
        install(root,manifest)
        print('Exact study assets installed under ignored build/v5-joint/corpus.')
        return
    verify(root,manifest)
    if args.action=='verify':
        print('Recorded study assets, decoder/tool sources and package versions match.')
        return
    os.chdir(root)
    sys.path.insert(0,str(root/'Codecs/LPX/01_ACTIVE_Q0_CODEC/tools'))
    base=root/'build/v5-joint/corpus'
    if args.action=='fit':
        script=base/'benchmark.py'
        sys.argv=[str(script),'--manifest',str(base/'strong-private.json'),
            '--subset',str(base/f'subsets/all-shard-{args.shard}.json'),
            '--output',str(base/args.branch/f'shard-{args.shard}')]
        if args.branch=='lsf-only':
            sys.argv.append('--no-refit')
    else:
        script=base/'audit.py'
        sys.argv=[str(script),args.branch]
    runpy.run_path(str(script),run_name='__main__')


if __name__=='__main__': main()
