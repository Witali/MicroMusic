"""Validate frozen round2 artifacts/privacy; never run an encoder."""
from pathlib import Path
import hashlib
import importlib.util
import json

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('round2_frozen', HERE / 'compare.py')
RUN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUN)
REPO = RUN.REPO


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    public_path = HERE / 'results-matrix.json'
    public = json.loads(public_path.read_text())
    private = json.loads((RUN.BUILD / 'journal-matrix-private.json').read_text())
    assert public['complete'] and private['complete']
    assert len(private['cases']) == 24 and len({r['name'] for r in private['cases']}) == 24
    assert public['builds'] == private['builds']
    RUN.verify_builds(private['builds'])
    assert private['reserve_inventory_sha256'] == sha(RUN.PRIVATE)
    assert private['original_matrix_sha256'] == sha(HERE.parent / 'results-matrix.json')
    assert public['cases'] == [RUN.public_row(r) for r in private['cases']]
    assert public['summary'] == RUN.summary(private['cases'])
    assert sum(r['reused_verified_pilot'] for r in private['cases']) == 1
    assert next(r for r in private['cases'] if r['reused_verified_pilot'])['name'] == 'chego-pcm'
    old_pilot = HERE / 'results-pilot.json'
    assert sha(old_pilot) == 'aa957eae4e486f7184f287aa3cf382c46e87d221bfd1c932b11b8eae5319d2ae'
    gate_hash = RUN.gate()
    assert gate_hash == public['independent_gate_sha256']
    original = json.loads((HERE.parent / 'results-matrix.json').read_text())
    inventory = json.loads(RUN.PRIVATE.read_text())
    target_by_ordinal = {r['ordinal']: r for r in inventory['cases']}
    public_text = public_path.read_text()
    artifact_checks = source_checks = development_exact = 0
    for row in private['cases']:
        source = REPO / row['source']
        assert sha(source) == row['source_sha256']
        source_checks += 1
        assert row['global_error'] == 0 and row['selector_replay_exact']
        assert row['stage']['search_calls'] == 1
        assert row['baseline']['bytes'] == row['stage']['baseline_bytes_B0']
        assert row['selected_output']['bytes'] <= row['baseline']['bytes']
        assert row['selected_changed'] == bool(row['stage']['selected'])
        assert row['selected_output']['host_accuracy'] == (4 if row['selected_changed'] else 3)
        assert row['production_pitch_guard_selected']
        assert row['stoi_eligible_from_baseline'] == [RUN.finite_stoi(v) for v in row['baseline']['quality']['stoi']]
        for label, files in row['artifacts'].items():
            for item in files.values():
                assert sha(REPO / item['path']) == item['sha256']
                artifact_checks += 1
        expected_label = 'raw_candidate' if row['selected_changed'] else 'baseline'
        for extension, item in row['artifacts']['selected_output'].items():
            assert item['sha256'] == row['artifacts'][expected_label][extension]['sha256']
        if row['group'] == 'development':
            clip = row['name'].rsplit('-', 1)[0]
            old = next(r for r in original['cases'] if r['name'] == clip + '-p3-' + row['target'])
            for extension in ('lpx', 'pcm'):
                assert row['artifacts']['baseline'][extension]['sha256'] == old['artifacts']['baseline'][extension]['sha256']
            development_exact += 1
        else:
            target = target_by_ordinal[row['ordinal']]
            assert row['source_sha256'] == target['target_sha256']
            assert source.stat().st_size == 64000 and row['samples'] == 32000
            # Source/artifact names and cryptographic fingerprints must not
            # appear in retained public reports, even inside another field.
            assert row['source'] not in public_text
            assert row['source_sha256'] not in public_text
            for files in row['artifacts'].values():
                for item in files.values():
                    assert item['path'] not in public_text and item['sha256'] not in public_text
            for field in ('source_file_sha256', 'source_pcm_sha256', 'target_sha256'):
                assert target[field] not in public_text
    assert artifact_checks == 216 and source_checks == 24 and development_exact == 8
    for group, count in (('development', 4), ('reserve', 8)):
        for target in ('pcm', 'pwm'):
            aggregate = public['summary'][group][target]
            assert aggregate['cases'] == count
            eligibility = aggregate['outputs']['baseline']['baseline_eligible_stoi_cases']
            assert all(output['baseline_eligible_stoi_cases'] == eligibility
                       for output in aggregate['outputs'].values())
    assert sha(HERE.parent / 'results-matrix.json') == 'c9c4d75bdebcb6ca80e376fc053e1a456389bc667f5f67505eb3bd2f796bdcf1'
    assert sha(HERE.parent / 'results-neighbors-matrix.json') == '2bb57d254ca4d1a8b7e6ca9b8b0a06d08e467c12b01116ff8e95dfd602b4933d'
    assert sha(HERE.parent / 'results-ensemble-matrix.json') == '349ca6c74828d7e23b5eb3036dfc5e109f76523b6757b07d3fcf4abceea67a24'
    result = dict(schema='lpx-p3-round2-retained-validation-v1',
        method='Hash/geometry/privacy validation only; no encoding or metric search. Public and ignored private records agree numerically. Reserve source/artifact bindings are checked locally and excluded from this retained receipt.',
        public_matrix_sha256=sha(public_path), immutable_pilot_sha256=sha(old_pilot),
        validator_sha256=sha(Path(__file__)), runner_sha256=sha(HERE / 'compare.py'),
        independent_gate_sha256=gate_hash, artifact_hash_checks=artifact_checks,
        source_hash_checks=source_checks, development_disabled_exact_cases=development_exact,
        cases=24, reserve_cases=16, reused_pilots=1, native_and_selector_flags_verified=True,
        all_selected_within_same_B0=True, baseline_frozen_stoi_membership=True,
        reserve_bindings_private=True, prior_results_unchanged=True)
    RUN.PAIR.write(HERE / 'validation.json', result)
    print('Validated 24 cases / 216 artifacts; reserve bindings remain private')


if __name__ == '__main__':
    main()
