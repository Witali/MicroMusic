"""Frozen round2 P3 integration comparison; reserve bindings stay ignored."""
from pathlib import Path
import argparse
import copy
import importlib.util
import json
import math
import os
import platform
import re
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
ACTIVE = REPO / 'Codecs/LPX/01_ACTIVE_Q0_CODEC'
BUILD = REPO / 'build/compact-quality/round2'
PRIVATE = REPO / 'build/compact-quality/round2-heldout/targets-private.json'
PREDECESSOR = 'a7eca3a57f40feaacc2c4ad1c7d855dd4a52868c'
GATE = REPO / 'build/compact-quality/round2-integration-independent/receipt.json'
SPEC = importlib.util.spec_from_file_location('frozen_original_pair', HERE.parent / 'compare.py')
PAIR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PAIR)
CHANGED = {
    'LpxAccuracy.cpp': 'a7206f9e34c62f35fbf89c54d135bbd59b699abb9de2670271686bd909d7d91c',
    'LpxAccuracy.h': '1d20e25688aa42c74afeff70bf9d2798e312ec33143882e0827e62c7a7b8abfa',
    'LpxAdaptiveController.h': 'ffcdc8533e31bc4c19fbdfbaa0d041b823294ddfbc6c741af9ffec30a30ee38d',
}


def build(variant):
    config = REPO / 'web-player/scripts/lib/lpx-build.mjs'
    text = config.read_text()
    names = re.findall(r"'([^']+\.cpp)'", text.split('export const hostSources=host([')[1].split(']);')[0])
    defines = re.findall(r"'([^']+)'", text.split('export const portableDefines=[')[1].split('];')[0])
    production = [ACTIVE / 'src/Lpx4HybridCore.cpp', ACTIVE / 'host/LpxEncoder.cpp',
                  *(ACTIVE / 'host' / name for name in names)]
    inputs = sorted(set(production + list((ACTIVE / 'host').glob('*.h'))
                        + list((ACTIVE / 'host').glob('*.inc')) + list((ACTIVE / 'src').glob('*.h'))
                        + list((ACTIVE / 'src').glob('*.inc')) + [config]))
    unchanged = {}
    predecessor_inputs = {}
    for path in inputs:
        name = PAIR.rel(path)
        old = PAIR.git('show', PREDECESSOR + ':' + name).replace(b'\r\n', b'\n')
        current = path.read_bytes().replace(b'\r\n', b'\n')
        predecessor_inputs[name] = PAIR.hashlib.sha256(old).hexdigest()
        if path.parent == ACTIVE / 'host' and path.name in CHANGED:
            if PAIR.sha(path) != CHANGED[path.name]:
                raise RuntimeError('Integration source changed before freeze')
        elif old != current:
            raise RuntimeError('Unrelated production input changed: ' + name)
        else:
            unchanged[name] = PAIR.hashlib.sha256(current).hexdigest()
    dependencies = [HERE / 'benchmark.cpp', Path(__file__).resolve(), HERE / 'P3_PROTOCOL.md',
                    HERE.parent / 'benchmark_ensemble.cpp',
                    REPO / 'Codecs/LPX/research/lbg1-2026-11-26/probe.cpp']
    hashes = {PAIR.rel(path): PAIR.sha(path) for path in inputs + dependencies}
    binary = BUILD / 'bin' / variant
    binary.parent.mkdir(parents=True, exist_ok=True)
    command = ['g++', '-O3', '-std=c++11', '-ffp-contract=off', '-DNDEBUG',
               *('-D' + d for d in defines),
               '-DLPX_ENCODER_COMPACT_ENSEMBLE=' + ('1' if variant == 'enabled' else '0'),
               '-include', PAIR.rel(ACTIVE / 'host/LpxHostWorkspace.h'),
               '-I' + PAIR.rel(ACTIVE / 'src'), '-I' + PAIR.rel(ACTIVE / 'host'),
               *(PAIR.rel(path) for path in production), PAIR.rel(HERE / 'benchmark.cpp'),
               '-o', PAIR.rel(binary)]
    receipt = BUILD / ('build-' + variant + '.json')
    if receipt.exists():
        previous = json.loads(receipt.read_text())
        if previous.get('sources') == hashes and binary.exists() and previous['binary_sha256'] == PAIR.sha(binary):
            return previous
        # Python orchestration is provenance, not a C++ compiler input. A
        # report-only revision can reuse the exact binary with an explicit
        # receipt update; the first pilot's original receipt remains preserved.
        runner = PAIR.rel(Path(__file__))
        changed = {name for name in set(previous.get('sources', {})) | set(hashes)
                   if previous.get('sources', {}).get(name) != hashes.get(name)}
        if (changed == {runner} and previous.get('command') == command
                and binary.exists() and previous['binary_sha256'] == PAIR.sha(binary)):
            old_runner = previous['sources'][runner]
            previous['sources'] = hashes
            previous.setdefault('orchestration_updates', []).append(dict(
                previous_runner_sha256=old_runner, runner_sha256=hashes[runner],
                reason='Report-only baseline-frozen STOI membership and immutable pilot reuse; compiled inputs, flags and binary unchanged.'))
            PAIR.write(receipt, previous)
            return previous
    subprocess.run(command, cwd=REPO, check=True)
    if hashes != {name: PAIR.sha(REPO / name) for name in hashes}:
        raise RuntimeError('Source changed during compilation')
    model = next((line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines()
                  if line.startswith('model name')), 'unknown')
    result = dict(schema='lpx-p3-round2-build-v1', variant=variant, predecessor=PREDECESSOR,
                  compiler=subprocess.check_output(['g++', '--version'], text=True).splitlines()[0],
                  command=command, sources=hashes, binary_sha256=PAIR.sha(binary),
                  unchanged_production_inputs=unchanged, predecessor_inputs=predecessor_inputs,
                  environment=dict(system=platform.system(), release=platform.release(),
                                   machine=platform.machine(), logical_cpus=os.cpu_count(), cpu_model=model))
    PAIR.write(receipt, result)
    return result


def inventory():
    private = json.loads(PRIVATE.read_text())
    if private.get('schema') != 'lpx-p3-round2-heldout-targets-private-v1' or len(private['cases']) != 8:
        raise RuntimeError('Fixed eight-source reserve inventory required')
    rows = []
    for value in private['cases']:
        source = PRIVATE.parent / value['target_file']
        if (value['rate'] != 8000 or value['samples'] != 32000
                or source.stat().st_size != 64000 or PAIR.sha(source) != value['target_sha256']):
            raise RuntimeError('Frozen reserve target mismatch')
        rows.append(dict(name=f"reserve-{value['ordinal']:02d}", group='reserve', ordinal=value['ordinal'],
                         source=PAIR.rel(source), source_sha256=value['target_sha256']))
    original = json.loads((HERE.parent / 'results-matrix.json').read_text())
    for clip in PAIR.CLIPS:
        old = next(r for r in original['cases'] if r['name'] == clip + '-p3-pcm')
        source = REPO / old['source']
        if PAIR.sha(source) != old['source_sha256']:
            raise RuntimeError('Development source changed')
        rows.insert(len(rows) - 8, dict(name=clip, group='development', source=old['source'],
                                       source_sha256=old['source_sha256']))
    return rows, original


def gate():
    receipt = json.loads(GATE.read_text())
    if receipt.get('passed') is not True:
        raise RuntimeError('Independent mechanism gate must pass before speech')
    sources = receipt.get('implementation_sha256', {})
    for name, digest in CHANGED.items():
        matches = [value for key, value in sources.items() if key == name or key.endswith('/' + name)]
        if matches != [digest]:
            raise RuntimeError('Gate did not bind current integration source')
    return PAIR.sha(GATE)


def public_row(row):
    result = copy.deepcopy(row)
    if result['group'] == 'reserve':
        for key in ('source', 'source_sha256', 'artifacts'):
            result.pop(key, None)
    return result


def summary(rows):
    result = {}
    for group in ('development', 'reserve'):
        result[group] = {}
        for target in ('pcm', 'pwm'):
            cases = [r for r in rows if r['group'] == group and r['target'] == target]
            if not cases:
                continue
            outputs = {}
            membership = [[index for index, row in enumerate(cases)
                           if finite_stoi(row['baseline']['quality']['stoi'][path])]
                          for path in (0, 1)]
            for label in ('baseline', 'raw_candidate', 'selected_output'):
                values = [r[label] for r in cases]
                stoi = [[values[index]['quality']['stoi'][path] for index in membership[path]]
                        for path in (0, 1)]
                missing = [sum(not finite_stoi(value) for value in path) for path in stoi]
                outputs[label] = dict(bytes=sum(v['bytes'] for v in values),
                    pcm_sse=sum(v['quality']['pcm_sse'] for v in values),
                    pwm_sse=sum(v['quality']['pwm_sse'] for v in values),
                    mean_stoi=[sum(v) / len(v) if v and not missing[path] else None
                               for path, v in enumerate(stoi)],
                    baseline_eligible_stoi_cases=[len(v) for v in membership],
                    missing_eligible_stoi_cases=missing,
                    available_stoi_cases=[len(stoi[path]) - missing[path] for path in (0, 1)],
                    spectral_bits=sum(v['bits']['spectral_total'] for v in values))
            result[group][target] = dict(cases=len(cases), selected_changes=sum(r['selected_changed'] for r in cases),
                raw_changes=sum(r['raw_changed'] for r in cases), optional_errors=sum(r['stage']['error'] != 0 for r in cases),
                disabled_whole_seconds=sum(r['disabled_timing']['whole_encode_seconds'] for r in cases),
                enabled_whole_seconds=sum(r['whole_encode_seconds'] for r in cases),
                enabled_whole_cpu_seconds=sum(r['whole_encode_cpu_seconds'] for r in cases),
                isolated_optional_phase_seconds=None, search_calls=sum(r['stage']['search_calls'] for r in cases),
                parameter_trials=sum(r['stage']['parameter_trials'] for r in cases),
                pulse_trials=sum(r['stage']['pulse_trials'] for r in cases), outputs=outputs)
    return result


def finite_stoi(value):
    return value is not None and math.isfinite(value)


def same_compiled_builds(before, after):
    runner = PAIR.rel(Path(__file__))
    return all(before[variant]['command'] == after[variant]['command']
        and before[variant]['binary_sha256'] == after[variant]['binary_sha256']
        and {k: v for k, v in before[variant]['sources'].items() if k != runner}
            == {k: v for k, v in after[variant]['sources'].items() if k != runner}
        for variant in ('disabled', 'enabled'))


def verify_builds(builds):
    for variant, receipt in builds.items():
        if receipt['sources'] != {name: PAIR.sha(REPO / name) for name in receipt['sources']}:
            raise RuntimeError('Frozen software changed')
        if PAIR.sha(BUILD / 'bin' / variant) != receipt['binary_sha256']:
            raise RuntimeError('Frozen binary changed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-only', action='store_true')
    parser.add_argument('--phase', choices=('pilot', 'matrix'), default='pilot')
    args = parser.parse_args()
    builds = {variant: build(variant) for variant in ('disabled', 'enabled')}
    if args.build_only:
        print('Built frozen enabled/disabled round2 integration')
        return
    gate_hash = gate()
    sources, original = inventory()
    private_hash = PAIR.sha(PRIVATE)
    original_hash = PAIR.sha(HERE.parent / 'results-matrix.json')
    rows = []
    for source in sources:
        for target in ('pcm', 'pwm'):
            if args.phase == 'pilot' and (source['name'] != 'chego' or target != 'pcm'):
                continue
            name = source['name'] + '-' + target
            reused = False
            if args.phase == 'matrix' and name == 'chego-pcm':
                pilot = json.loads((BUILD / 'journal-pilot-private.json').read_text())
                if not same_compiled_builds(pilot['builds'], builds) or not pilot['complete'] or pilot['reserve_inventory_sha256'] != private_hash:
                    raise RuntimeError('Pilot binding changed')
                row = copy.deepcopy(pilot['cases'][0])
                for files in row['artifacts'].values():
                    for item in files.values():
                        if PAIR.sha(REPO / item['path']) != item['sha256']:
                            raise RuntimeError('Pilot artifact changed')
                reused = True
            else:
                path = REPO / source['source']
                if PAIR.sha(path) != source['source_sha256']:
                    raise RuntimeError('Frozen target changed')
                directory = BUILD / 'runs' / args.phase / name
                directory.mkdir(parents=True, exist_ok=True)
                disabled, enabled = directory / 'disabled', directory / 'enabled'
                baseline = PAIR.run([BUILD / 'bin/disabled', path, disabled, target, '-'])
                if source['group'] == 'development':
                    expected = next(r for r in original['cases'] if r['name'] == source['name'] + '-p3-' + target)
                    if PAIR.sha(Path(str(disabled) + '.lpx')) != expected['artifacts']['baseline']['lpx']['sha256']:
                        raise RuntimeError('Explicit switch-off differs from frozen original')
                row = PAIR.run([BUILD / 'bin/enabled', path, enabled, target, str(disabled) + '.lpx'])
                row.update(source, name=name, target=target, baseline=baseline['selected_output'],
                           disabled_timing={key: baseline[key] for key in ('whole_encode_seconds', 'whole_encode_cpu_seconds')},
                           artifacts=dict(baseline=PAIR.artifacts(disabled),
                                          raw_candidate=PAIR.artifacts(Path(str(enabled) + '-raw')),
                                          selected_output=PAIR.artifacts(enabled)))
            row['reused_verified_pilot'] = reused
            row['stoi_eligible_from_baseline'] = [finite_stoi(v) for v in row['baseline']['quality']['stoi']]
            rows.append(row)
            verify_builds(builds)
            if PAIR.sha(PRIVATE) != private_hash or PAIR.sha(HERE.parent / 'results-matrix.json') != original_hash:
                raise RuntimeError('Frozen inventory or predecessor result changed')
            private_result = dict(schema='lpx-p3-round2-private-journal-v1', phase=args.phase, complete=False,
                                  builds=builds, reserve_inventory_sha256=private_hash, original_matrix_sha256=original_hash,
                                  cases=rows)
            public = dict(schema='lpx-p3-round2-public-results-v1', phase=args.phase, complete=False,
                builds=builds, protocol_sha256=PAIR.sha(HERE / 'P3_PROTOCOL.md'), independent_gate_sha256=gate_hash,
                method='Finished prior P3 is the immutable B0 floor. One existing fine-grid search per eligible enabled encode, unchanged production selector and guards. Raw and selected outputs are separate. Strict capped retention is posthoc only. No gain/delay/source fitting or criterion tuning. Whole disabled/enabled encode wall and CPU times include capture/validation work inside encodeAccuracy but exclude separate output diagnostics; isolated optional phase time is unmeasured. Single-run host time differences are not controlled speed ratios. PWM diagnostics are inactive for PCM selection. Reserve sources and artifacts are bound only in the ignored private journal. STOI membership is fixed from the disabled baseline per case/path for every variant; a missing eligible value makes that group mean unavailable with an explicit count. All sources remain in case/byte/error denominators.',
                reserve_binding_verified=True, cases=[public_row(r) for r in rows], summary=summary(rows))
            PAIR.write(BUILD / ('journal-' + args.phase + '-private.json'), private_result)
            PAIR.write(HERE / ('results-' + args.phase + '.json'), public)
            print(f"{name}: {row['baseline']['bytes']} -> {row['selected_output']['bytes']} bytes; selected={row['selected_changed']}; optional_status={row['stage']['status']}", flush=True)
    private_result['complete'] = public['complete'] = True
    PAIR.write(BUILD / ('journal-' + args.phase + '-private.json'), private_result)
    PAIR.write(HERE / ('results-' + args.phase + '.json'), public)
    print(PAIR.rel(HERE / ('results-' + args.phase + '.json')), flush=True)


if __name__ == '__main__':
    main()
