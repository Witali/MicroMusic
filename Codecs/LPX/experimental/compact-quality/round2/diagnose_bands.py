"""Anonymous posthoc diagnostics of selected reserve outputs; no encoding."""
from pathlib import Path
import copy
import importlib.util
import json
import math
import subprocess

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('round2_frozen', HERE / 'compare.py')
RUN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUN)
REPO = RUN.REPO
MATRIX_SHA = 'b5a5a92df4bf0c782c40c669ef499a74488867d15eca9bb11a000331755a5c98'
DIAGNOSTIC_SHA = '894e1a2315929496df53494d02b0258b6f6fe8e68029e72524360f616bca5294'


def selected_names(value):
    if isinstance(value, dict):
        return {key.replace('raw', 'selected'): selected_names(item) for key, item in value.items()}
    if isinstance(value, list):
        return [selected_names(item) for item in value]
    return value


def build(base):
    original = HERE.parent / 'ensemble_diagnostics.cpp'
    if RUN.PAIR.sha(original) != DIAGNOSTIC_SHA:
        raise RuntimeError('Frozen diagnostic implementation changed')
    source = original.read_text()
    marker = '        std::cout<<",\\\"total_error_raw\\\":";value(b.totalError[path]);\n'
    extra = '''        std::cout<<",\\\"total_temporal_baseline\\\":";value(a.totalTemporalError[path]);
        std::cout<<",\\\"total_temporal_raw\\\":";value(b.totalTemporalError[path]);
        std::cout<<",\\\"balanced_error_baseline\\\":";value(a.balancedError[path]);
        std::cout<<",\\\"balanced_error_raw\\\":";value(b.balancedError[path]);
        std::cout<<",\\\"balanced_temporal_baseline\\\":";value(a.balancedTemporalError[path]);
        std::cout<<",\\\"balanced_temporal_raw\\\":";value(b.balancedTemporalError[path]);
'''
    if source.count(marker) != 1:
        raise RuntimeError('Expected exactly one print-only insertion site')
    generated = RUN.BUILD / 'ensemble-diagnostics-print.cpp'
    generated.write_text(source.replace(marker, marker + extra, 1), encoding='utf-8', newline='\n')
    binary = RUN.BUILD / 'bin/selected-band-diagnostics'
    command = base['command'].copy()
    old = RUN.PAIR.rel(HERE / 'benchmark.cpp')
    if command.count(old) != 1:
        raise RuntimeError('Unexpected source composition')
    command[command.index(old)] = RUN.PAIR.rel(generated)
    command.insert(command.index('-o'), '-I' + RUN.PAIR.rel(HERE.parent))
    command[command.index('-o') + 1] = RUN.PAIR.rel(binary)
    sources = {**base['sources'], RUN.PAIR.rel(original): DIAGNOSTIC_SHA,
               RUN.PAIR.rel(generated): RUN.PAIR.sha(generated),
               RUN.PAIR.rel(Path(__file__)): RUN.PAIR.sha(Path(__file__))}
    subprocess.run(command, cwd=REPO, check=True)
    if sources != {name: RUN.PAIR.sha(REPO / name) for name in sources}:
        raise RuntimeError('Diagnostic source changed')
    receipt = dict(schema='lpx-p3-round2-band-diagnostic-build-v1', command=command,
        sources=sources, compiler=base['compiler'], binary_sha256=RUN.PAIR.sha(binary),
        environment=base['environment'], print_only_insertion_sites=1,
        method='Reuses the frozen earlier diagnostic arithmetic and guard crosschecks. One checked source insertion prints existing aggregate fields only; it changes no calculation, threshold or encoder call.')
    RUN.PAIR.write(RUN.BUILD / 'build-selected-band-diagnostics.json', receipt)
    return binary, receipt


def summary(rows):
    result = {}
    for target in ('pcm', 'pwm'):
        cases = [r for r in rows if r['target'] == target]
        paths = {}
        for path in ('pcm',) if target == 'pcm' else ('pcm', 'pwm'):
            values = [next(v for v in r['fullband'] if v['path'] == path) for r in cases]
            bands = [b for v in values for b in v['bands'] if b['supported']]
            errors = [b for b in bands if b['error_floor_rejected']]
            retention = [b for b in bands if b['retention_floor_rejected']]
            octaves = [next(v for v in r['octaves'] if v['path'] == path) for r in cases]
            paths[path] = dict(cases=len(cases), supported_band_case_pairs=len(bands),
                magnitude_error_regression_cases=sum(any(b['error_floor_rejected'] for b in v['bands']) for v in values),
                magnitude_error_regression_bands=len(errors),
                worst_error_increase=max((b['error_delta'] for b in errors), default=0),
                worst_relative_error_increase_percent=max((b['error_relative_delta_percent'] for b in errors
                    if b['error_relative_delta_percent'] is not None), default=0),
                lower_retention_cases=sum(any(b['retention_floor_rejected'] for b in v['bands']) for v in values),
                lower_retention_bands=len(retention),
                worst_retention_delta_percentage_points=min((b['retention_delta_percentage_points'] for b in retention), default=0),
                added_octave_windows=sum(v['added_octave_windows'] for v in octaves),
                aggregate_floor_failure_cases=sum(v['aggregate_floor_failure'] for v in values),
                mean_total_error_baseline=sum(v['total_error_baseline'] for v in values)/len(values),
                mean_total_error_selected=sum(v['total_error_selected'] for v in values)/len(values),
                mean_balanced_error_baseline=sum(v['balanced_error_baseline'] for v in values)/len(values),
                mean_balanced_error_selected=sum(v['balanced_error_selected'] for v in values)/len(values),
                mean_balanced_temporal_baseline=sum(v['balanced_temporal_baseline'] for v in values)/len(values),
                mean_balanced_temporal_selected=sum(v['balanced_temporal_selected'] for v in values)/len(values))
        result[target] = dict(cases=len(cases), selected_changes=sum(r['selected_changed'] for r in cases), paths=paths)
    return result


def main():
    public_path = HERE / 'results-matrix.json'
    if RUN.PAIR.sha(public_path) != MATRIX_SHA:
        raise RuntimeError('Expected frozen complete matrix')
    public = json.loads(public_path.read_text())
    private = json.loads((RUN.BUILD / 'journal-matrix-private.json').read_text())
    if not public['complete'] or not private['complete']:
        raise RuntimeError('Matrix is incomplete')
    RUN.verify_builds(private['builds'])
    binary, build_receipt = build(private['builds']['enabled'])
    rows = []
    bindings = []
    for old in private['cases']:
        if old['group'] != 'reserve':
            continue
        source = REPO / old['source']
        if RUN.PAIR.sha(source) != old['source_sha256']:
            raise RuntimeError('Frozen target changed')
        for files in old['artifacts'].values():
            for item in files.values():
                if RUN.PAIR.sha(REPO / item['path']) != item['sha256']:
                    raise RuntimeError('Frozen output changed')
        measured = RUN.PAIR.run([binary, source,
            REPO / old['artifacts']['baseline']['lpx']['path'],
            REPO / old['artifacts']['selected_output']['lpx']['path'], old['target']])
        row = selected_names(measured)
        row.update(name=old['name'], ordinal=old['ordinal'], target=old['target'],
                   selected_changed=old['selected_changed'])
        retention_pass = True
        for path in row['fullband']:
            path['aggregate_floor_failure'] = any(path[next_key] > path[old_key] + 1e-12
                for next_key, old_key in [('total_error_selected', 'total_error_baseline'),
                    ('balanced_error_selected', 'balanced_error_baseline'),
                    ('balanced_temporal_selected', 'balanced_temporal_baseline')])
            if path['aggregate_floor_failure']:
                raise RuntimeError('Selected stream violates existing aggregate floor')
            retention_pass &= not path['total_error_regressed'] and not any(
                b['error_floor_rejected'] or b['retention_floor_rejected'] for b in path['bands'])
            for band in path['bands']:
                band.pop('source_power', None)
        if retention_pass != old['research_retention_guard_selected']:
            raise RuntimeError('Posthoc retention rule differs from frozen diagnostic')
        if any(path['added_octave_windows'] for path in row['octaves']):
            raise RuntimeError('Selected output added an octave label')
        rows.append(row)
        bindings.append(dict(name=old['name'], source=old['source'], source_sha256=old['source_sha256'],
                             artifacts=old['artifacts']))
    if len(rows) != 16 or RUN.PAIR.sha(public_path) != MATRIX_SHA:
        raise RuntimeError('Wrong case count or changed primary result')
    result = dict(schema='lpx-p3-round2-selected-band-diagnostics-v1', posthoc=True,
        method='Read-only replay of all16 selected reserve outputs versus their own disabled baselines, including unchanged outputs. No encoder or search call, source/gain/delay fitting, criterion change or retrospective reclassification. Magnitude/temporal errors use existing source-fixed FullBand definitions; summary means are unweighted per-case normalized errors. Capped retention and individual band errors are diagnostics, not additional production acceptance criteria. Only active paths are reported; octave labels are heuristic observations, not verified F0. Source identities, paths, audio fingerprints and payloads stay in the ignored private journal.',
        primary_public_matrix_sha256=MATRIX_SHA, software_build=build_receipt,
        private_bindings_verified=True, cases=rows, summary=summary(rows))
    encoded = json.dumps(result)
    for binding in bindings:
        if binding['source'] in encoded or binding['source_sha256'] in encoded:
            raise RuntimeError('Private source binding leaked into public diagnostic')
        for files in binding['artifacts'].values():
            for item in files.values():
                if item['path'] in encoded or item['sha256'] in encoded:
                    raise RuntimeError('Private artifact binding leaked into public diagnostic')
    RUN.PAIR.write(RUN.BUILD / 'selected-band-diagnostics-private.json', dict(
        schema='lpx-p3-round2-selected-band-private-bindings-v1', source_bindings=bindings,
        primary_journal_sha256=RUN.PAIR.sha(RUN.BUILD / 'journal-matrix-private.json')))
    RUN.PAIR.write(HERE / 'selected-band-diagnostics.json', result)
    print('Measured16 anonymous reserve selections; primary results and criteria unchanged')


if __name__ == '__main__':
    main()
