"""Reproduce the post-study production-player subset using local tool paths.

The subset is fixed after the corpus result: every strict stream-byte saving
versus an accepted same-budget control, plus the accepted 95% point. This is
timing/cost admission, not another search or a listening evaluation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

from benchmark_speech_flash import source_hashes
from build_release_player import simulate
import speech_compact as compact
from standard_metrics import pwm_duties


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def source_inventory(root, active):
    files = [p for folder in (active / 'src', active / 'tools', active / 'examples/AVR_V5_PLAYER')
             for p in folder.iterdir() if p.is_file() and p.suffix in ('.cpp', '.h', '.py', '.inc')]
    files += [active.parent / 'validation/atmega328p' / name
              for name in ('sim_player.c', 'player_hardware.cpp')]
    return {p.relative_to(root).as_posix(): sha(p.read_bytes()) for p in sorted(files)}


def prepare(study, out):
    workers = [json.loads((study / 'workers' / f'{mode}-shard-{shard}.json').read_text())
               for mode in ('sse', 'perceptual') for shard in (0, 1)]
    assert all(w['status'] == 'complete' for w in workers)
    audit_data = (study / 'audit-anonymous.json').read_bytes()
    assert json.loads(audit_data)['status'] == 'complete'
    inputs = workers[0]['input_files_sha256']
    docs = []
    for path, digest in inputs.items():
        data = Path(path).read_bytes()
        assert sha(data) == digest
        docs.append(json.loads(data))
    old = {r['id']: r for d in docs if d.get('schema') == 'lpx-v5-encoder-quality-run-v1'
           for r in d['records']}
    chains = {}
    pairs = []

    def add_chain(entry, role, record):
        blobs = [Path(s['path']).read_bytes() for s in entry['segments']]
        assert all(len(b) == s['file_bytes'] and sha(b) == s['stream_sha256']
                   for b, s in zip(blobs, entry['segments']))
        key = tuple(sha(b) for b in blobs)
        if key not in chains:
            chains[key] = {'id': f'chain-{len(chains) + 1:03d}', 'segments': entry['segments'],
                           'samples': record['samples'], 'profile': record['profile'],
                           'stream_bytes': sum(map(len, blobs)), 'roles': []}
        chain = chains[key]
        assert chain['samples'] == record['samples'] and chain['profile'] == record['profile']
        chain['roles'].append(role)
        return chain['id']

    for worker in workers:
        for record in worker['records']:
            for budget in record['budgets']:
                selected = budget['selected']
                if selected is None or not budget['accepted_control_present']:
                    continue
                if not (selected['stream_bytes'] < budget['accepted_control_bytes']
                        or budget['percent'] == 95):
                    continue
                control = next(b for b in old[record['id']]['budgets']
                               if b['percent'] == budget['percent'])['selected']
                role = {'mode': worker['mode'], 'id': record['id'], 'percent': budget['percent']}
                control_id = add_chain(control, dict(role, role='old-accepted-control'), record)
                selected_id = add_chain(selected, dict(role, role='new-selected'), record)
                assert selected['automatic_floors_passed'] and selected['accepted_control_floors_passed']
                pairs.append(dict(role, control=control_id, selected=selected_id,
                                  profile=record['profile'], samples=record['samples'],
                                  control_bytes=control['stream_bytes'], selected_bytes=selected['stream_bytes']))
    binding = {'source': workers[0]['source'], 'study_inputs': inputs,
               'audit_sha256': sha(audit_data), 'chains': list(chains.values()), 'pairs': pairs,
               'reproduction_source_sha256': sha(Path(__file__).read_bytes())}
    assert not (out / 'bindings-private.json').exists(), 'Use a fresh admission output directory.'
    write(out / 'bindings-private.json', binding)
    print(json.dumps({'prepared': True, 'unique_chains': len(chains), 'images': len(chains) * 2}))


def measure(args, study, out):
    root = Path.cwd()
    active = root / 'Codecs/LPX/01_ACTIVE_Q0_CODEC'
    binding_data = (out / 'bindings-private.json').read_bytes()
    binding = json.loads(binding_data)
    source = source_inventory(root, active)
    assert source_hashes(active / 'src') == binding['source']['decoder']
    assert {p.name: sha(p.read_bytes()) for p in (active / 'tools').glob('*.py')} == binding['source']['tools']
    for path, digest in binding['study_inputs'].items():
        assert sha(Path(path).read_bytes()) == digest
    assert sha((study / 'audit-anonymous.json').read_bytes()) == binding['audit_sha256']
    observer_hash = sha(args.observer.read_bytes())
    begin = time.perf_counter()
    rows = []
    report = {'schema': 'lpx-v5-combined-player-private-v1', 'status': 'running',
              'source_sha256': source, 'runner_sha256': observer_hash,
              'bindings_sha256': sha(binding_data), 'script_sha256': sha(Path(__file__).read_bytes()),
              'queue': 256, 'prefill': 192, 'assembly': True, 'shard': args.shard, 'rows': rows}
    for index, entry in enumerate(binding['chains']):
        if index % 2 != args.shard:
            continue
        blobs = [Path(s['path']).read_bytes() for s in entry['segments']]
        assert all(len(b) == s['file_bytes'] and sha(b) == s['stream_sha256']
                   for b, s in zip(blobs, entry['segments']))
        assert sum(map(len, blobs)) == entry['stream_bytes']
        expected = b''.join(pwm_duties(compact.decode_model(b)).tobytes() for b in blobs)
        assert len(expected) == entry['samples']
        for irq in (0, 100):
            result = simulate(blobs, out / 'images' / entry['id'] / f'irq-{irq}', args.avr_bin,
                              args.observer, source=active, queue=256, prefill=192, irq=irq,
                              assembly=True, lib=args.simavr_lib, wsl=args.wsl, expected_pwm=expected)
            cost, observed = result['cost'], result['report']
            assert result['passed'] and cost['image_role'] == 'production-player'
            assert cost['embedded_streams_exact'] and cost['stream_bytes'] == entry['stream_bytes']
            assert cost['samples'] == entry['samples'] and cost['segments'] == len(blobs)
            assert observed['played'] == observed['produced'] == observed['timer_ticks'] == observed['timer_events'] == entry['samples']
            assert cost['queue'] == 256 and cost['prefill'] == 192 and cost['assembly_enabled']
            assert cost['extra_irq_cycles'] == irq and source_inventory(root, active) == source
            assert sha(args.observer.read_bytes()) == observer_hash
            assert (out / 'bindings-private.json').read_bytes() == binding_data
            rows.append({'chain_id': entry['id'], 'profile': entry['profile'], 'irq': irq, 'result': result})
            report['elapsed_seconds'] = time.perf_counter() - begin
            write(out / f'shard-{args.shard}-private.json', report)
            print(json.dumps({'shard': args.shard, 'images': len(rows), 'passed': True}), flush=True)
    assert len(rows) == 2 * sum(i % 2 == args.shard for i in range(len(binding['chains'])))
    assert source_inventory(root, active) == source
    report.update(status='complete', elapsed_seconds=time.perf_counter() - begin)
    write(out / f'shard-{args.shard}-private.json', report)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--shard', type=int, choices=(0, 1))
    parser.add_argument('--avr-bin', type=Path)
    parser.add_argument('--observer', type=Path)
    parser.add_argument('--simavr-lib', type=Path)
    parser.add_argument('--wsl', default='Ubuntu')
    args = parser.parse_args()
    study, out = args.study.resolve(), args.output.resolve()
    assert study.is_relative_to((Path.cwd() / 'build').resolve())
    assert out.is_relative_to((Path.cwd() / 'build').resolve())
    out.mkdir(parents=True, exist_ok=True)
    if args.prepare:
        prepare(study, out)
    else:
        assert args.shard is not None and args.avr_bin and args.observer and args.simavr_lib
        measure(args, study, out)
