"""Independent runtime, exact job inventory and reference-domain audit adjunct."""
import argparse
from collections import defaultdict
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import os
import shutil
import subprocess
import sys


def main(args):
    sha = lambda data: hashlib.sha256(data).hexdigest()
    load = lambda path: json.loads(path.read_text())
    binding = load(args.study / 'binding-private.json')
    compiler = Path(shutil.which('g++'))
    environment = {'python': sys.version, 'platform': platform.platform(),
        'packages': {name: version(name) for name in ('numpy', 'numba', 'scipy', 'pystoi', 'soundfile')},
        'compiler_file_sha256': sha(compiler.read_bytes()),
        'compiler_version': subprocess.check_output([str(compiler), '--version'], text=True).splitlines()[0],
        'threads': {name: os.environ.get(name) for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'NUMBA_NUM_THREADS')}}
    assert environment == binding['environment']
    groups = defaultdict(list)
    for record in binding['records']:
        groups[record['private_case_id']].append(record)
        assert len(Path(record['reference']['path']).read_bytes()) == record['reference']['file_bytes']
    assert len(groups) == 49
    import numpy as np
    import soundfile as sf
    quiet = []
    targeted = 0
    for ordinal, pair in enumerate(groups.values()):
        assert len(pair) == 2 and {r['profile'] for r in pair} == {4, 6}
        assert len({r['reference']['pcm16_sha256'] for r in pair}) == len({r['samples'] for r in pair}) == 1
        record = pair[0]
        ref, rate = sf.read(record['reference']['path'], dtype='int16')
        assert rate == 8000 and ref.ndim == 1 and len(ref) == record['samples']
        assert sha(ref.astype('<i2').tobytes()) == record['reference']['pcm16_sha256']
        if float(np.std(ref.astype(np.float64))) < 256:
            assert len(ref) <= 64000 and all(len(r['segments']) == 1 for r in pair)
            quiet.append(ordinal)
        if record['reference']['pcm16_sha256'] == binding['targeted_reference_pcm16_sha256']:
            targeted += 1
    assert quiet == binding['quiet_source_ordinals'] and len(quiet) == 4 and targeted == 1
    expected = {args.study / 'records' / ('source-%03d' % job['source_ordinal']) / ('profile-%d' % binding['records'][job['record_index']]['profile']) / job['mode'] for job in binding['jobs']}
    assert len(expected) == 106
    actual_reports = {p.parent for p in (args.study / 'records').rglob('record-private.json')}
    actual_markers = {p.parent for p in (args.study / 'records').rglob('complete-private.json')}
    attempts = list((args.study / 'records').rglob('attempt-*-private.json'))
    assert actual_reports == actual_markers == expected
    assert len(attempts) == 106 and {p.parent.parent for p in attempts} == expected
    assert all(load(p)['status'] == 'complete' and load(p)['active_segment'] is None for p in attempts)
    assert sum(load(p)['completed_v4_native_fit_calls'] for p in attempts) == 386
    assert {p.name for p in (args.study / 'workers').glob('*-private.json')} == {'shard-0-private.json', 'shard-1-private.json'}
    assert args.output.resolve().is_relative_to((args.source_root / 'build').resolve())
    result = {'schema': 'lpx-quiet-voice-independent-context-audit-v1', 'status': 'passed',
        'prepared_python_packages_compiler_and_threads_match': True,
        'sources_with_exactly_both_profiles_and_same_reference': 49,
        'whole_single_reset_auto_source_count': 4, 'targeted_sources': 1, 'targeted_profiles': 2,
        'exact_record_marker_and_attempt_inventory': 106,
        'total_all_attempts_observed_native_v4_fits': 386,
        'unexpected_job_folders_or_attempts_or_worker_receipts': 0,
        'scope': 'Read-only adjunct to the numerical saved-output audit; no fits or target measurements. No private identities, media fingerprints or paths are exported.',
        'audit_source_sha256': sha(Path(__file__).read_bytes())}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args())
