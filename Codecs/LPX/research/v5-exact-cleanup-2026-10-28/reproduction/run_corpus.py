"""Run frozen exact-cleanup inputs, retaining private fingerprints in build/."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sys
import time

from batch_decoder import BatchSession
from benchmark_speech_flash import source_hashes
from cleanup_speech_compact import cleanup


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def save(path, value):
    path.write_bytes((json.dumps(value, indent=2, allow_nan=False) + '\n').encode())


def main(args):
    root = Path.cwd()
    active = root / 'Codecs/LPX/01_ACTIVE_Q0_CODEC'
    out = args.output.resolve()
    assert out.is_relative_to((root / 'build').resolve())
    binding_data = args.bindings.read_bytes()
    binding = json.loads(binding_data)
    source = binding['source']
    script_hash = sha(Path(__file__).read_bytes())
    libraries = {'common': sha(args.common_lib.read_bytes()), 'v5_only': sha(args.v5_lib.read_bytes())}

    def guards():
        assert source_hashes(active / 'src') == source['decoder']
        assert {p.name: sha(p.read_bytes()) for p in (active / 'tools').glob('*.py')} == source['tools']
        assert sha((active / 'tests/test_cleanup_speech_compact.py').read_bytes()) == source['test']
        assert sha((root / 'Codecs/LPX/research/v5-exact-cleanup-2026-10-28/PROTOCOL.md').read_bytes()) == source['protocol']
        assert args.bindings.read_bytes() == binding_data and sha(Path(__file__).read_bytes()) == script_hash
        assert sha(args.common_lib.read_bytes()) == libraries['common']
        assert sha(args.v5_lib.read_bytes()) == libraries['v5_only']

    guards()
    for path, digest in binding['input_files_sha256'].items():
        assert sha(Path(path).read_bytes()) == digest
    assert all(not Path(s['path']).resolve().is_relative_to(out / 'streams') for s in binding['streams'])
    identity = sha(canonical([sha(binding_data), script_hash, libraries]))
    (out / 'streams').mkdir(parents=True, exist_ok=True)
    (out / 'workers').mkdir(exist_ok=True)
    rows = []
    begin = time.perf_counter()
    cpu_begin = time.process_time()
    runtime = {'python': sys.version, 'platform': platform.platform(),
               'packages': {name: importlib.metadata.version(name)
                            for name in ('numpy', 'numba', 'scipy', 'soundfile')}}
    report = {'schema': 'lpx-v5-exact-cleanup-worker-private-v1', 'status': 'running',
              'source': source, 'runner_source_sha256': script_hash, 'identity': identity,
              'bindings_sha256': sha(binding_data), 'native_libraries_sha256': libraries,
              'runtime': runtime, 'shard': args.shard, 'shards': args.shards, 'rows': rows,
              'reused': 0, 'executed': 0}
    with BatchSession('batch', prebuilt=args.common_lib) as common, BatchSession('batch', prebuilt=args.v5_lib) as only:
        for index, stream in enumerate(binding['streams']):
            if index % args.shards != args.shard:
                continue
            blob = Path(stream['path']).read_bytes()
            assert len(blob) == stream['file_bytes'] and sha(blob) == stream['stream_sha256']
            cache = out / 'streams' / (stream['id'] + '.json')
            if cache.is_file():
                row = json.loads(cache.read_text())
                assert row['identity'] == identity and row['input_sha256'] == stream['stream_sha256']
                data = Path(row['output']).read_bytes()
                assert len(data) == row['report']['file_bytes'] and sha(data) == row['output_sha256']
                report['reused'] += 1
            else:
                t = time.perf_counter()
                c = time.process_time()
                new, details = cleanup(blob, common=common, compact_only=only)
                target = out / 'streams' / (stream['id'] + '.l4hy')
                if new == blob:
                    target = Path(stream['path'])
                else:
                    target.write_bytes(new)
                row = {'id': stream['id'], 'identity': identity, 'input_sha256': sha(blob),
                       'output': str(target.resolve()), 'output_sha256': sha(new), 'report': details,
                       'wall_seconds': time.perf_counter() - t, 'cpu_seconds': time.process_time() - c}
                save(cache, row)
                report['executed'] += 1
            rows.append(row)
            if len(rows) % 10 == 0:
                guards()
                report.update(wall_seconds=time.perf_counter() - begin,
                              cpu_seconds=time.process_time() - cpu_begin)
                save(out / 'workers' / f'shard-{args.shard}-private.json', report)
                print(json.dumps({'shard': args.shard, 'streams': len(rows),
                                  'changed': sum(r['report']['changed'] for r in rows),
                                  'saved_stream_bytes': sum(r['report']['saved_bytes'] for r in rows)}), flush=True)
    guards()
    for path, digest in binding['input_files_sha256'].items():
        assert sha(Path(path).read_bytes()) == digest
    assert len(rows) == sum(i % args.shards == args.shard for i in range(len(binding['streams'])))
    report.update(status='complete', wall_seconds=time.perf_counter() - begin,
                  cpu_seconds=time.process_time() - cpu_begin)
    save(out / 'workers' / f'shard-{args.shard}-private.json', report)
    print(json.dumps({'shard': args.shard, 'status': 'complete', 'streams': len(rows),
                      'changed': sum(r['report']['changed'] for r in rows),
                      'saved_stream_bytes': sum(r['report']['saved_bytes'] for r in rows)}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bindings', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--common-lib', required=True, type=Path)
    parser.add_argument('--v5-lib', required=True, type=Path)
    parser.add_argument('--shard', type=int, required=True)
    parser.add_argument('--shards', type=int, default=2)
    args = parser.parse_args()
    assert args.shards >= 1 and 0 <= args.shard < args.shards
    main(args)
