"""Posthoc guard diagnostics of saved changed ensemble outputs; no encoding."""
from pathlib import Path
import hashlib
import importlib.util
import json
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
BUILD = REPO / 'build/compact-quality'
SPEC = importlib.util.spec_from_file_location('frozen_p3_pair', HERE / 'compare.py')
PAIR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PAIR)
MATRIX = HERE / 'results-ensemble-matrix.json'
MATRIX_SHA = '349ca6c74828d7e23b5eb3036dfc5e109f76523b6757b07d3fcf4abceea67a24'


def main():
    if PAIR.sha(MATRIX) != MATRIX_SHA:
        raise RuntimeError('Frozen ensemble matrix changed')
    matrix = json.loads(MATRIX.read_text())
    base = json.loads((BUILD / 'build-ensemble.json').read_text())
    if matrix['build'] != base or not matrix['complete']:
        raise RuntimeError('Expected complete frozen build/matrix')
    inputs = {**base['sources'],
              PAIR.rel(HERE / 'ensemble_diagnostics.cpp'): PAIR.sha(HERE / 'ensemble_diagnostics.cpp'),
              PAIR.rel(Path(__file__)): PAIR.sha(Path(__file__))}
    if inputs != {name: PAIR.sha(REPO / name) for name in inputs}:
        raise RuntimeError('Frozen source input changed')
    binary = BUILD / 'bin/ensemble-diagnostics'
    command = base['command'].copy()
    old = PAIR.rel(HERE / 'benchmark_ensemble.cpp')
    if command.count(old) != 1:
        raise RuntimeError('Unexpected source composition')
    command[command.index(old)] = PAIR.rel(HERE / 'ensemble_diagnostics.cpp')
    command[command.index('-o') + 1] = PAIR.rel(binary)
    subprocess.run(command, cwd=REPO, check=True)
    build = dict(schema='lpx-ensemble-posthoc-diagnostic-build-v1', compiler=base['compiler'],
                 command=command, sources=inputs, binary_sha256=PAIR.sha(binary),
                 frozen_ensemble_binary_sha256=base['binary_sha256'], environment=base['environment'])
    PAIR.write(BUILD / 'build-ensemble-diagnostics.json', build)
    rows = []
    media_checks = 0
    for row in matrix['cases']:
        if not row['protection']['raw_changed']:
            continue
        source = REPO / row['source']
        if PAIR.sha(source) != row['source_sha256']:
            raise RuntimeError('Source changed')
        for files in row['artifacts'].values():
            for item in files.values():
                if PAIR.sha(REPO / item['path']) != item['sha256']:
                    raise RuntimeError('Saved artifact changed')
                media_checks += 1
        output = PAIR.run([binary, source,
                           REPO / row['artifacts']['baseline']['lpx']['path'],
                           REPO / row['artifacts']['raw-ensemble']['lpx']['path'], row['target']])
        # The independent reconstruction must match the already frozen flags.
        band_failure = any(path['total_error_regressed'] or any(
            band['error_floor_rejected'] or band['retention_floor_rejected']
            for band in path['bands']) for path in output['fullband'])
        pitch_failure = any(path['added_octave_windows'] for path in output['octaves'])
        if band_failure != bool(row['protection']['rejection_bits'] & 8):
            raise RuntimeError('FullBand diagnosis differs from frozen admission')
        if pitch_failure != bool(row['protection']['rejection_bits'] & 16):
            raise RuntimeError('Pitch diagnosis differs from frozen admission')
        output.update(name=row['name'], target=row['target'], source=row['source'],
                      source_sha256=row['source_sha256'], artifacts=row['artifacts'],
                      frozen_rejection_bits=row['protection']['rejection_bits'],
                      existing_selector_chose_raw=row['protection']['existing_selector_chose_ensemble'],
                      strict_protection_chose_raw=row['protection']['protected_ensemble_selected'])
        rows.append(output)
    if len(rows) != 3:
        raise RuntimeError('Expected exactly the three previously changed cases')
    if inputs != {name: PAIR.sha(REPO / name) for name in inputs} or PAIR.sha(MATRIX) != MATRIX_SHA:
        raise RuntimeError('Input changed during measurement')
    result = dict(
        schema='lpx-ensemble-posthoc-guard-diagnostics-v1', posthoc=True,
        method='Measurement only of the three changed saved raw outputs. No encoder, search, normalization, gain/delay fitting, criterion change or acceptance relaxation. Exact existing FullBand and PitchGuard decisions are cross-checked against the frozen rejection bits. Only active admission paths are listed: PCM only for the PCM target; PCM and PWM for the PWM target.',
        definitions={
            'band_error': 'Squared FFT-magnitude mismatch normalized by that source band power; lower is better. Band boundaries and source support use existing FullBandContext.',
            'retention': 'min(1, sqrt(output band power / source band power)); the guard rejects any supported-band decrease beyond its existing 1e-12 tolerance. This capped amplitude proxy is distinct from actual error.',
            'source_support': 'Band source power exceeds 1e-4 of total source power; whole-file source-fixed support.',
            'octave_window': '80 ms (640 samples), 20 ms hop (160 samples), existing source-frozen period estimator. Label bit1 means near half source frequency; bit2 means near double source frequency, each within100 cents. Labels are heuristic period observations, not verified true F0 or proof of audible pitch.',
            'window_counts': 'Overlapping windows are not independent events. Report start/end sample locations instead of treating counts as disjoint duration.',
            'interpretation': 'This posthoc diagnosis explains reasons for rejection; it does not change frozen decisions or establish audible severity. Any retained raw tradeoff remains rejected.'},
        frozen_matrix_sha256=MATRIX_SHA, build=build, saved_artifact_hash_checks=media_checks,
        cases=rows)
    PAIR.write(HERE / 'ensemble-diagnostics.json', result)
    print(PAIR.rel(HERE / 'ensemble-diagnostics.json'))


if __name__ == '__main__':
    main()
