"""Read-only verification of retained private outputs and anonymous export.

No search, tuning, target preparation or audio publication occurs here.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--packages', type=Path)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--public', type=Path, required=True)
parser.add_argument('--validation', type=Path, required=True)


def validate(args):
    import run_campaign as runner
    runner.initialize(args.packages)
    e, np, sparse = runner.e, runner.np, runner.sparse
    from refine_speech_compact import no_regression
    from refine_sparse80 import voice_floor
    from refine_sparse80_pulses import band_error_floors
    from native_receiver import NativeReceiver
    out = runner.private_output(args.output)
    freeze = runner.frozen(out)
    public = runner.read(args.public)
    if public['completed_cases'] != 27 or [c['ordinal'] for c in public['cases']] != [c['ordinal'] for c in freeze['cases']]:
        raise ValueError('Anonymous export does not contain all original cases in stable order')
    if len([c for c in public['cases'] if c['split'] == 'heldout_speech']) != 10:
        raise ValueError('Original heldout denominator changed')
    # Only software provenance may contain hashes. Public case rows must not
    # leak any identifying paths, payloads, exact wire symbols or fingerprints.
    def safe(value, location=()):
        if isinstance(value, dict):
            for key, item in value.items():
                numeric_screen_count = (location == ('counters',) and key in
                    ('symbol_screens', 'symbol_screen_samples') and type(item) is int and item >= 0)
                if (not numeric_screen_count and any(word in key.lower() for word in
                        ('sha256', 'fingerprint', 'symbol', 'filename', 'source_file', 'target_file'))):
                    raise ValueError('Anonymous per-case output contains a private binding field')
                safe(item, location + (key,))
        elif isinstance(value, list):
            for item in value:
                safe(item, location)
        elif isinstance(value, str):
            if ':\\' in value or '/mnt/' in value or len(value) == 64 and all(c in '0123456789abcdef' for c in value):
                raise ValueError('Anonymous per-case output contains a private path or hash')
    safe(public['cases'])
    counters = dict(cases=0, immutable_leaf_streams=0, native_model_variant_replays=0,
                    byte_and_field_checks=0, final_floor_checks=0)
    wall = time.perf_counter()
    with NativeReceiver('common') as common, NativeReceiver('v5-only') as only:
        receiver = e.bridge_receiver(common, only)
        for case, public_row in zip(freeze['cases'], public['cases']):
            folder = out / ('case-%03d' % case['ordinal'])
            pointer = runner.read(folder / 'result-pointer-private.json')
            receipt = runner.read(runner.checked(folder, pointer['receipt_file'], pointer['receipt_sha256']))
            if receipt['status'] != 'PASS' or receipt['source_freeze_sha256'] != runner.digest(runner.encoded(freeze)):
                raise ValueError('Case completion is not bound to the frozen implementation')
            if (pointer['selected_file'] != 'final-exhaustive.lpx'
                    or pointer['selected_sha256'] != receipt['variants']['exhaustive']['final']['sha256']):
                raise ValueError('Authoritative result pointer differs from its final exhaustive selection')
            blob = (folder / 'baseline.lpx').read_bytes()
            layout = e.parse_layout(blob)
            fields = sparse.unpack(blob)
            reference = np.frombuffer((folder / 'target.pcm16').read_bytes(), dtype='<i2').copy()
            if public_row != runner.public_case(receipt):
                raise ValueError('Public row differs from the strict numeric whitelist')
            for name, expected in receipt['artifacts'].items():
                runner.checked(folder, name, expected)
            if (receipt['counters']['leaves'] != 324 or receipt['counters']['symbol_screens'] != 2048
                    or receipt['counters']['full_model_checks'] != 325
                    or receipt['counters']['native_oracle_calls'] != 321
                    or receipt['counters']['full_metric_evaluations'] != 1 + sum(
                        len(rows) for rows in receipt['admission']['candidates'].values())):
                raise ValueError('Recorded deterministic evaluation bounds changed')
            for row in receipt['leaves']:
                candidate = (folder / row['file']).read_bytes()
                changed = sparse.unpack(candidate)
                if (len(candidate) != len(blob) or changed[:3] != fields[:3] or changed[4:] != fields[4:]
                        or runner.digest(candidate) != row['sha256']):
                    raise ValueError('Retained leaf changed bytes or non-pulse fields')
                allowed = set()
                for packet in range(row['frame'] * 4, row['frame'] * 4 + 4):
                    allowed.update(range(layout.pulse_offsets[packet], layout.pulse_offsets[packet] + 7))
                for at, (a, b) in enumerate(zip(blob, candidate)):
                    for bit in range(8):
                        if (a ^ b) & (1 << bit) and at * 8 + bit not in allowed:
                            raise ValueError('Retained leaf changed an original non-editable bit')
                counters['immutable_leaf_streams'] += 1
            replayed = {}
            for topology, variants in receipt['variants'].items():
                for kind, row in variants.items():
                    stem = kind + '-' + topology
                    candidate = (folder / (stem + '.lpx')).read_bytes()
                    if runner.digest(candidate) != row['sha256'] or len(candidate) != len(blob):
                        raise ValueError('Raw/final stream digest or original complete bytes changed')
                    if candidate not in replayed:
                        modeled = sparse.decode_model(candidate)
                        pcm, pwm = e._oracle(receiver, candidate, modeled)
                        replayed[candidate] = pcm, pwm
                        counters['native_model_variant_replays'] += 1
                    pcm, pwm = replayed[candidate]
                    if ((folder / (stem + '.pcm16')).read_bytes() != pcm.astype('<i2').tobytes()
                            or (folder / (stem + '.pwm8')).read_bytes() != pwm.tobytes()):
                        raise ValueError('Retained raw/final waveform is not exact native output')
                    counters['byte_and_field_checks'] += 1
                    if kind != 'final':
                        continue
                    baseline = receipt['baseline']['metrics']
                    after = row['metrics']
                    if (not no_regression(after['metrics'], baseline['metrics'])
                            or not all(voice_floor(a, b) for a, b in zip(after['voice'], baseline['voice']))
                            or not all(a <= b for a, b in zip(after['clipped'], baseline['clipped']))
                            or not band_error_floors(row['bands']['pwm8'], receipt['baseline']['bands']['pwm8'])):
                        raise ValueError('Final selection violates its own protected baseline floors')
                    if row['changed']:
                        entries = receipt['admission']['candidates'][topology]
                        matching = [entry for entry in entries if entry['sha256'] == row['sha256']]
                        if (not matching or not all(matching[0]['floors'].values())
                                or after['score'] >= baseline['score'] - 1e-12
                                or after['pwm_joint_score'] >= baseline['pwm_joint_score'] - 1e-12):
                            raise ValueError('Final changed output did not pass its own independent topology admission')
                    elif candidate != blob:
                        raise ValueError('Unchanged selection is not the exact original rollback')
                    counters['final_floor_checks'] += 1
            counters['cases'] += 1
    # Rebuild all anonymous aggregates from the immutable per-case receipts.
    regenerated = runner.export(out, None)
    if regenerated != public:
        raise ValueError('Anonymous aggregate differs from retained case data')
    validation = dict(schema='lpx-sparse2-results-validation-v1', status='PASS', counters=counters,
        wall_seconds=time.perf_counter() - wall, source_freeze_unchanged=True,
        every_case_own_final_round3_baseline=True, every_saved_target_unchanged=True,
        every_leaf_original_bitmask_and_length_exact=True, final_native_model_pcm_pwm_exact=True,
        independent_topology_admission_floors=True, fixed_heldout_and_stoi_denominators=True,
        public_rows_and_aggregates_exact=True, public_private_fields_excluded=True,
        validator_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='Read-only post-search artifact validation; no rerun search, subjective or AVR evidence')
    destination = args.validation.resolve()
    destination.relative_to(HERE.resolve())
    runner.write(destination, validation)
    print(json.dumps(dict(status='PASS', **counters)), flush=True)


if __name__ == '__main__':
    args = parser.parse_args()
    try:
        validate(args)
    except Exception as error:
        # Identifying failure details stay in the already private output root.
        import traceback
        (args.output / 'validation-error-private.log').write_text(traceback.format_exc(), encoding='utf-8')
        print(json.dumps(dict(status='INFRASTRUCTURE_STOP', exception=type(error).__name__)), flush=True)
        sys.exit(2)
