"""Independently recheck full native old/new chains and original frozen outputs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from batch_decoder import BatchSession
from benchmark_speech_flash import source_hashes
import speech_compact as compact


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    path.write_bytes((json.dumps(value, indent=2, allow_nan=False) + '\n').encode())


def main(args):
    root = Path.cwd()
    out = args.output.resolve()
    assert out.is_relative_to((root / 'build').resolve())
    binding_bytes = args.bindings.read_bytes()
    binding = json.loads(binding_bytes)
    workers = [json.loads((out / 'workers' / f'shard-{shard}-private.json').read_text())
               for shard in range(args.shards)]
    assert all(w['status'] == 'complete' and w['bindings_sha256'] == sha(binding_bytes) for w in workers)
    assert all(w['source'] == binding['source'] and w['identity'] == workers[0]['identity'] for w in workers)
    streams = {s['id']: s for s in binding['streams']}
    admitted = {r['id']: r for w in workers for r in w['rows']}
    assert set(admitted) == set(streams) and sum(len(w['rows']) for w in workers) == len(streams)
    active = root / 'Codecs/LPX/01_ACTIVE_Q0_CODEC'
    source = binding['source']
    script_hash = sha(Path(__file__).read_bytes())
    native = {'common': sha(args.common_lib.read_bytes()), 'v5_only': sha(args.v5_lib.read_bytes())}
    assert native == workers[0]['native_libraries_sha256']

    def guards():
        assert source_hashes(active / 'src') == source['decoder']
        assert {p.name: sha(p.read_bytes()) for p in (active / 'tools').glob('*.py')} == source['tools']
        assert sha((active / 'tests/test_cleanup_speech_compact.py').read_bytes()) == source['test']
        assert args.bindings.read_bytes() == binding_bytes and sha(Path(__file__).read_bytes()) == script_hash
        assert sha(args.common_lib.read_bytes()) == native['common'] and sha(args.v5_lib.read_bytes()) == native['v5_only']

    guards()
    original = {}
    for path, digest in binding['input_files_sha256'].items():
        data = Path(path).read_bytes()
        assert sha(data) == digest
        doc = json.loads(data)
        if doc.get('schema') in ('lpx-v5-encoder-quality-study-v1', 'lpx-v5-encoder-quality-nonspeech-v1'):
            source_set = 'original-speech' if doc['schema'] == 'lpx-v5-encoder-quality-study-v1' else 'original-nonspeech'
            for record in doc['records']:
                original[source_set, record['id']] = record
    expected = {}
    for request in binding['requests']:
        key = (request['source_set'], request['source_id_private'])
        if key in original:
            record = original[key]
            pair = (record['baseline_pcm16_sha256'], record['baseline_pwm_sha256'])
            if request['chain_id'] in expected:
                assert expected[request['chain_id']] == pair
            expected[request['chain_id']] = pair
    begun = time.perf_counter()
    rows = []
    comparisons = frozen = samples_checked = 0
    report = {'schema': 'lpx-v5-exact-cleanup-chain-audit-private-v1', 'status': 'running',
              'source': source, 'native_libraries_sha256': native, 'bindings_sha256': sha(binding_bytes),
              'auditor_source_sha256': script_hash, 'rows': rows}
    with BatchSession('batch', prebuilt=args.common_lib) as common, BatchSession('batch', prebuilt=args.v5_lib) as only:
        for chain in binding['chains']:
            input_blobs = []
            output_blobs = []
            for sid in chain['stream_ids']:
                s, a = streams[sid], admitted[sid]
                old, new = Path(s['path']).read_bytes(), Path(a['output']).read_bytes()
                assert sha(old) == s['stream_sha256'] == a['input_sha256'] and sha(new) == a['output_sha256']
                assert len(new) == a['report']['file_bytes'] <= len(old) == s['file_bytes']
                assert compact.unpack(old)[:7] == compact.unpack(new)[:7]
                assert all(a['report'][k] for k in ('idempotent', 'model_pcm_pwm_exact',
                    'native_common_pcm_pwm_exact', 'native_v5_only_pcm_pwm_exact', 'nonzero_drive_exact'))
                input_blobs.append(old); output_blobs.append(new)
            pcm_hash = pwm_hash = None
            for decoder in (common, only):
                p, w = hashlib.sha256(), hashlib.sha256()
                played = 0
                for sid, old, new in zip(chain['stream_ids'], input_blobs, output_blobs):
                    n = streams[sid]['samples']
                    a = decoder.decode_one_s16(old, n)
                    b = decoder.decode_one_s16(new, n)
                    c = decoder.decode_one(old, n)
                    d = decoder.decode_one(new, n)
                    assert a is not None and b is not None and c is not None and d is not None
                    assert len(a) == len(b) == len(c) == len(d) == n
                    assert np.array_equal(a, b) and np.array_equal(c, d)
                    p.update(a.astype('<i2', copy=False).tobytes()); w.update(c.tobytes())
                    played += n; comparisons += 2; samples_checked += 2 * n
                assert played == chain['samples']
                if pcm_hash is None:
                    pcm_hash, pwm_hash = p.hexdigest(), w.hexdigest()
                else:
                    assert (pcm_hash, pwm_hash) == (p.hexdigest(), w.hexdigest())
                if chain['id'] in expected:
                    assert (p.hexdigest(), w.hexdigest()) == expected[chain['id']]
                    frozen += 1
            rows.append({'id': chain['id'], 'samples': chain['samples'], 'profile': chain['profile'],
                         'segments': len(chain['stream_ids']), 'input_bytes': sum(map(len, input_blobs)),
                         'output_bytes': sum(map(len, output_blobs)),
                         'changed': input_blobs != output_blobs, 'saved_bytes': sum(map(len, input_blobs)) - sum(map(len, output_blobs)),
                         'pcm16_sha256': pcm_hash, 'pwm_sha256': pwm_hash,
                         'full_original_new_native_pcm_pwm_exact': True,
                         'frozen_original_chain_matched': chain['id'] in expected})
            if len(rows) % 20 == 0:
                guards()
                report.update(elapsed_seconds=time.perf_counter() - begun,
                              fresh_native_domain_pairs=comparisons, fresh_native_sample_domain_pairs=samples_checked,
                              frozen_original_layout_checks=frozen)
                save(out / 'chain-audit-private.json', report)
                print(json.dumps({'phase': 'chain-audit', 'chains': len(rows),
                                  'changed_chains': sum(r['changed'] for r in rows)}), flush=True)
    guards()
    for path, digest in binding['input_files_sha256'].items():
        assert sha(Path(path).read_bytes()) == digest
    report.update(status='complete', elapsed_seconds=time.perf_counter() - begun,
                  fresh_native_domain_pairs=comparisons, fresh_native_sample_domain_pairs=samples_checked,
                  frozen_original_layout_checks=frozen)
    save(out / 'chain-audit-private.json', report)
    print(json.dumps({'status': 'complete', 'chains': len(rows), 'changed_chains': sum(r['changed'] for r in rows),
                      'fresh_native_domain_pairs': comparisons, 'frozen_original_layout_checks': frozen}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bindings', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--common-lib', required=True, type=Path)
    parser.add_argument('--v5-lib', required=True, type=Path)
    parser.add_argument('--shards', type=int, default=2)
    main(parser.parse_args())
