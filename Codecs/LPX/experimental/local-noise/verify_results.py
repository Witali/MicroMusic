"""Check retained reports against local frozen inputs, artifacts and test receipt.

Run after prepare_sources.py, compare.py and the independent tests. This checks
hashes and reported contracts; native sample-by-sample decoding is performed by
benchmark.cpp and tests/local_noise.cpp when those artifacts are generated.
"""
from pathlib import Path
import hashlib
import importlib.util
import json

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
SPEC = importlib.util.spec_from_file_location('local_noise_compare', HERE / 'compare.py')
COMPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COMPARE)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    artifact_checks = 0
    reports = []
    first_build = None
    descriptors = {}
    expected_counts = {'pilot': 2, 'matrix': 16, 'heldout': 4}
    for phase, expected in expected_counts.items():
        path = HERE / f'results-{phase}.json'
        report = json.loads(path.read_text())
        require(report['complete'] and len(report['cases']) == expected,
                f'Incomplete {phase} report')
        build = report['build']
        require(sha(REPO / 'build/local-noise/benchmark') == build['binary_sha256'],
                'Compiled benchmark changed')
        require(first_build is None or first_build == build, 'Build differs between phases')
        first_build = build
        for name, expected_sha in build['sources'].items():
            require(sha(REPO / name) == expected_sha, f'Build input changed: {name}')
        revision, production = COMPARE.verify_baseline([REPO / name for name in build['sources']])
        require(revision == build['baseline_revision'] and
                production == build['baseline_sources_normalized_sha256'],
                'Pinned production baseline changed')
        require(sha(REPO / report['retained_pwm_reference']) ==
                report['retained_pwm_reference_sha256'], 'Retained PWM reference changed')
        for case in report['cases']:
            require(sha(REPO / case['source']) == case['source_sha256'], 'Source changed')
            require(case['native_model_exact'] and case['pulse_only_same_complete_bytes'],
                    'Native decode or size contract failed')
            source_key = (case['source_sha256'], case['sample_rate'])
            frozen = case['source_windows']
            require(source_key not in descriptors or descriptors[source_key] == frozen,
                    'Source analysis differs between targets or accuracy levels')
            descriptors[source_key] = frozen
            for variant, artifact in case['artifacts'].items():
                for extension in ('lpx', 'pcm', 'model'):
                    require(sha(REPO / artifact[extension]) == artifact[extension + '_sha256'],
                            f'Changed artifact: {case["name"]}/{variant}/{extension}')
                    artifact_checks += 1
                require((REPO / artifact['lpx']).stat().st_size ==
                        case['outputs'][variant]['bytes'] == case['outputs']['baseline']['bytes'],
                        'Complete file size differs')
                output = case['outputs'][variant]
                require(not any(output[key] for key in
                                ('changed_spectral_indices', 'changed_parameters', 'changed_extras')),
                        'A frozen non-pulse field changed')
            for variant in ('final-noise', 'final-sse'):
                for extension in ('lpx', 'pcm', 'model'):
                    require(case['artifacts'][variant][extension + '_sha256'] ==
                            case['artifacts']['baseline'][extension + '_sha256'],
                            'Frozen result no longer equals its own baseline')
            require(case['search']['accepted'] == 0 and
                    case['search']['admitted_proposals'] == 0, 'Frozen admission result changed')
        for target, totals in report['summary'].items():
            rows = [case for case in report['cases'] if case['quality_target'] == target]
            require(len(rows) == totals['cases'], 'Aggregate case count differs')
            for variant, total in totals['outputs'].items():
                require(sum(case['outputs'][variant]['bytes'] for case in rows) == total['bytes'],
                        'Aggregate size differs')
                for key in ('pcm_sse', 'pwm_sse'):
                    require(sum(case['outputs'][variant][key] for case in rows) == total[key],
                            'Aggregate SSE differs')
        reports.append({'phase': phase, 'cases': len(report['cases']), 'sha256': sha(path)})
    test_receipt = json.loads((REPO / 'build/local-noise-independent-tests/receipt.json').read_text())
    for name, expected_sha in test_receipt['sources'].items():
        require(sha(REPO / name) == expected_sha, f'Test input changed: {name}')
    require(set(test_receipt['results']) == {'metric', 'fallback', 'search', 'admission'} and
            all(value.startswith('PASS ') for value in test_receipt['results'].values()),
            'Independent tests are incomplete')
    result = dict(artifact_hash_checks=artifact_checks, source_descriptor_sets=len(descriptors),
                  phases=reports, independent_test_groups=4,
                  final_noise_and_control_exact_baselines=True,
                  production_baseline=first_build['baseline_revision'])
    output = REPO / 'build/local-noise/verification.json'
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
