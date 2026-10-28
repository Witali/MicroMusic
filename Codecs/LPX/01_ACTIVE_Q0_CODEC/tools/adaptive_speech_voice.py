"""Bounded, deterministic host search over existing v5 voice operators.

Every contender is serialized and decoded before selection. This controller
finds the best measured contender in its finite search, not a global optimum.
The decoder, bitstream and integer output transfer remain unchanged.
"""
from __future__ import annotations

from numbers import Integral
import time

import numpy as np

import speech_compact as compact
import speech_v4
from encode_speech_voice import prepare_level, _quality
from enhance_speech_compact import enhance
from refine_speech_compact import no_regression, refine as refine_header
from refine_speech_lpc import refine, SEARCH_PRESETS
from speech_rate_allocation import bit_accounting, extra_capacity
from speech_noise_objective import NoiseObjective
from standard_metrics import pwm_duties, pwm_pcm16
from tune_pcm16 import set_header
from voice_character import compare_voice, track_pitch


def _integer(value, low, high, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral) or not low <= value <= high:
        raise ValueError('Invalid ' + name)
    return int(value)


def _clipped(pcm):
    data = np.asarray(pcm, np.int64)
    return int(np.count_nonzero((data <= -32768) | (data >= 32767)))


def _validate_settings(max_refinement_calls, lpc_preset, extra_full_evaluations,
                       firmware_cost, max_flash_bytes):
    _integer(max_refinement_calls, 0, 32, 'refinement call limit')
    _integer(extra_full_evaluations, 1, 512, 'extra full evaluation limit')
    if lpc_preset not in SEARCH_PRESETS:
        raise ValueError('Unknown LPC search preset')
    if firmware_cost is not None and not callable(firmware_cost):
        raise ValueError('Expected complete firmware cost callback')
    if max_flash_bytes is not None:
        _integer(max_flash_bytes, 1, 2**32 - 1, 'full Flash cap')
        if firmware_cost is None:
            raise ValueError('A Flash cap requires actual complete-image measurement')


def refine_candidates(reference, control, seeds, decoder, *, max_bytes,
                      compact_decoder=None, speech=True, max_refinement_calls=4,
                      lpc_preset='expanded', extra_full_evaluations=128,
                      firmware_cost=None, max_flash_bytes=None, candidate_sink=None):
    """Return selected bytes/PCM/report/raw from reusable, verified seeds.

    Seeds are streams, not cached metric claims. All are rechecked against this
    exact target. A call budget bounds expensive operator calls; each operator
    retains its separate, reported local work bounds. No time limit is implied.
    ``firmware_cost(blob)`` optionally builds/measures a complete player image;
    a Flash limit requires this callback, never a guessed program-size constant.
    """
    target, _ = prepare_level(reference, 'preserve')
    cap = _integer(max_bytes, 22, 65535, 'complete byte cap')
    _validate_settings(max_refinement_calls, lpc_preset, extra_full_evaluations,
                       firmware_cost, max_flash_bytes)
    if candidate_sink is not None and not callable(candidate_sink):
        raise ValueError('Expected a callable candidate sink')
    limit = _integer(max_refinement_calls, 0, 32, 'refinement call limit')
    extra_limit = _integer(extra_full_evaluations, 1, 512, 'extra full evaluation limit')
    started = time.perf_counter()
    track = track_pitch(target)
    noise_objective = NoiseObjective(target, track.period)
    voice_objective = noise_objective.voice_objective
    pool, by_blob, stages, skipped = [], {}, [], []
    geometry = None

    def add(blob, origin):
        nonlocal geometry
        blob = bytes(blob)
        if blob in by_blob:
            return by_blob[blob]
        fields = compact.unpack(blob)
        if fields[0] != len(target):
            raise ValueError('Seed sample count differs from the declared target')
        if geometry is None:
            geometry = fields[:2]
        elif fields[:2] != geometry:
            raise ValueError('Seed profile/length differs from the control')
        pcm = compact.decode_model(blob)
        for receiver in (decoder, compact_decoder):
            if receiver is None:
                continue
            actual = receiver.decode_one_s16(blob, len(target))
            duty = receiver.decode_one(blob, len(target))
            if (actual is None or duty is None or not np.array_equal(actual, pcm)
                    or not np.array_equal(duty, pwm_duties(pcm))):
                raise AssertionError('Adaptive contender native/model PCM/PWM mismatch')
        pwm = pwm_pcm16(pcm)
        domains = [pcm, pwm]
        voice = [compare_voice(target, d, reference_track=track) for d in domains]
        noise = [noise_objective.summary(d) for d in domains]
        scores = [float(voice_objective(d) + summary['score']) for d, summary in zip(domains, noise)]
        flash = None if firmware_cost is None else _integer(
            firmware_cost(blob), 1, 2**32 - 1, 'measured full Flash size')
        row = dict(id=len(pool), origin=origin, file_bytes=len(blob),
            full_flash_bytes=flash, metrics=_quality(target, pcm, bool(speech)),
            voice=voice[0], pwm_voice=voice[1],
            noise=noise[0], pwm_noise=noise[1],
            domain_scores=scores, score=float(np.mean(scores)), clipped_samples=_clipped(pcm),
            fits_complete_cap=len(blob) <= cap,
            fits_flash_cap=max_flash_bytes is None or flash <= max_flash_bytes)
        item = (blob, pcm, row)
        pool.append(item)
        by_blob[blob] = item
        if candidate_sink is not None:
            candidate_sink(blob)
        return item

    baseline = add(control, 'control')
    base_row = baseline[2]

    def allowed(row):
        # Fine spectral and collapsed-window descriptors are retained as
        # diagnostics. Requiring all of them to improve independently blocked
        # useful joint changes in V1. The shared score now ranks that tradeoff.
        return bool(row['fits_complete_cap'] and row['fits_flash_cap']
            and row['score'] <= base_row['score'] + 1e-12
            and no_regression(row['metrics'], base_row['metrics'])
            and row['clipped_samples'] <= base_row['clipped_samples']
            and all(row[key]['within_tolerance_frames'] >= base_row[key]['within_tolerance_frames']
                    for key in ('voice', 'pwm_voice')))

    def ranked():
        return sorted((item for item in pool if item[2]['fits_complete_cap']
                       and item[2]['fits_flash_cap']),
                      key=lambda item: (item[2]['score'], len(item[0]), item[2]['id']))

    for seed in seeds:
        add(seed, 'seed')
    attempted = set()
    while len(stages) < limit:
        work = None
        work_pool = sorted(ranked(), key=lambda item: (
            not allowed(item[2]), item[2]['score'], len(item[0]), item[2]['id']))
        for item in work_pool:
            blob, _, row = item
            for operator in ('extras', 'header_filters', 'joint_lpc_excitation'):
                key = (blob, operator)
                if key in attempted:
                    continue
                attempted.add(key)
                if row['origin'] == operator:
                    skipped.append(dict(parent=row['id'], operator=operator,
                                        reason='alternate_operators_before_repeating'))
                    continue
                if operator == 'extras':
                    fields = compact.unpack(blob)
                    layout = bit_accounting(fields[2], fields[1], fields[7])
                    if any(amp for _, amp in fields[7]):
                        skipped.append(dict(parent=row['id'], operator=operator,
                                            reason='existing_extras_preserved'))
                        continue
                    capacity = extra_capacity(layout['spectrum_bits'], len(fields[2]),
                                              fields[1], cap, (len(target) + 39)//40)
                    if not capacity:
                        skipped.append(dict(parent=row['id'], operator=operator,
                                            reason='no_capacity_after_all_marker_bits'))
                        continue
                work = item, operator
                break
            if work is not None:
                break
        if work is None:
            break
        (blob, _, row), operator = work
        if operator == 'extras':
            fields = compact.unpack(blob)
            legacy = speech_v4.pack(*fields[:7])
            # The legacy adapter is used only for a stream with no extras;
            # its compact repack must preserve every reconstructed sample.
            repacked, _ = compact.repack(legacy)
            if not np.array_equal(compact.decode_model(repacked), by_blob[blob][1]):
                raise AssertionError('Lossless no-extras adapter changed samples')
            result, _, detail = enhance(target, legacy, decoder, cap, horizon=320,
                position_candidates=6, batch_size=16, max_full_evaluations=extra_limit, speech=bool(speech))
            alternatives = [result]
        elif operator == 'header_filters':
            result, _, detail = refine_header(target, blob, decoder, trial_limit=256, metric_limit=16,
                                              speech=bool(speech))
            pairs = [detail['raw_best_sse_header']] + [dict(preQ14=entry['preQ14'],
                brightQ14=entry['brightQ14']) for entry in detail['alternatives']]
            alternatives = [result] + [set_header(blob, pair['preQ14'], pair['brightQ14']) for pair in pairs]
        else:
            result, _, detail, raw = refine(target, blob, decoder, cap,
                                           speech=bool(speech), **SEARCH_PRESETS[lpc_preset])
            alternatives = [result, raw]
        ids = [add(candidate, operator)[2]['id'] for candidate in alternatives]
        # Operator reports may contain private stream fingerprints; report
        # only numerical work/settings here. Checkpoints stay private to callers.
        counters = {key: detail[key] for key in (
            'candidate_evaluations', 'full_evaluations', 'full_limit_reached',
            'spectral_trials', 'excitation_trials', 'full_metric_evaluations',
            'accepted_frames', 'extra_pulses', 'seconds') if key in detail}
        stages.append(dict(parent=row['id'], operator=operator, outputs=ids, work=counters))

    feasible = ranked()
    admissible = [item for item in feasible if allowed(item[2])]
    selected = admissible[0] if admissible else None
    raw = feasible[0] if feasible else None
    frontier, best_score = [], float('inf')
    for item in sorted(admissible, key=lambda item: (len(item[0]), item[2]['score'], item[2]['id'])):
        if item[2]['score'] < best_score:
            frontier.append(item[2]['id'])
            best_score = item[2]['score']
    for _, _, row in pool:
        row['admissible'] = allowed(row)
    report = dict(schema='lpx-v5-adaptive-voice-v2', samples=len(target), profile=geometry[1],
        complete_byte_cap=cap, full_flash_cap=max_flash_bytes,
        full_flash_measured=firmware_cost is not None,
        max_refinement_calls=limit, refinement_calls=len(stages),
        stopped_by='call_limit' if len(stages) == limit else 'finite_pool_exhausted',
        search_settings=dict(lpc_preset=lpc_preset, lpc=SEARCH_PRESETS[lpc_preset].copy(),
            header_trial_limit=256, header_metric_limit=16,
            extra_horizon=320, extra_positions=6, extra_batch_size=16,
            extra_full_evaluation_limit=extra_limit),
        objective=dict(voice=voice_objective.describe(), noise=noise_objective.describe(),
            domains=['native_pcm16', 'fixed_pwm8'], aggregation='mean of voice + noise'),
        candidates=[item[2] for item in pool], stages=stages, skipped=skipped,
        frontier=frontier, selected_id=None if selected is None else selected[2]['id'],
        selected_bytes=None if selected is None else len(selected[0]),
        selected_differs_from_control=selected is not None and selected[0] != bytes(control),
        raw_id=None if raw is None else raw[2]['id'],
        raw_bytes=None if raw is None else len(raw[0]),
        native_common_and_model_exact=True, native_v5_only_checked=compact_decoder is not None,
        decoder_and_format_unchanged=True, seconds=time.perf_counter()-started,
        scope='Best measured contender under explicit bounds; objective proxies are not listening or hardware evidence.')
    return (None if selected is None else selected[0], None if selected is None else selected[1],
            report, None if raw is None else raw[0])


def encode(reference, profile, decoder, *, baseline=None, max_bytes=None,
           pre_values=(0, 8192, 13926), level_policy='auto-quiet', speech=True,
           compact_decoder=None, max_refinement_calls=4, lpc_preset='expanded',
           extra_full_evaluations=128, firmware_cost=None, max_flash_bytes=None,
           candidate_sink=None):
    """One input-level decision, seed fitting, and shared bounded refinement."""
    from encode_speech_voice import encode as seed_encode
    started = time.perf_counter()
    _validate_settings(max_refinement_calls, lpc_preset, extra_full_evaluations,
                       firmware_cost, max_flash_bytes)
    if candidate_sink is not None and not callable(candidate_sink):
        raise ValueError('Expected a callable candidate sink')
    target, level = prepare_level(reference, level_policy)
    old = None if baseline is None else bytes(baseline)
    if old is not None and compact.unpack(old)[:2] != (len(target), profile):
        raise ValueError('Original stream profile/length does not match reference')
    cap = max_bytes if max_bytes is not None else len(old) if old is not None else None
    seeds = []
    seed_selected, _, seed_report, _ = seed_encode(target, profile, decoder,
        baseline=old if level['gain_power2_exponent'] == 0 else None, max_bytes=cap,
        pre_values=pre_values, level_policy='preserve', speech=speech,
        compact_decoder=compact_decoder, candidate_sink=lambda blob: seeds.append(blob))
    anchor = seeds[0] if seed_selected is None else seed_selected
    selected, pcm, report, raw = refine_candidates(target, anchor, seeds, decoder,
        max_bytes=seed_report['complete_byte_cap'], speech=speech,
        compact_decoder=compact_decoder, max_refinement_calls=max_refinement_calls,
        lpc_preset=lpc_preset, extra_full_evaluations=extra_full_evaluations,
        firmware_cost=firmware_cost, max_flash_bytes=max_flash_bytes, candidate_sink=candidate_sink)
    report.update(level=level, seed_search=seed_report,
        seed_seconds=seed_report['seconds'], refinement_seconds=report['seconds'],
        admission_anchor='conservative_seed_grid_selection' if seed_selected is not None else 'legacy_control',
        original_baseline_used_as_byte_cap_only=old is not None and level['gain_power2_exponent'] != 0)
    report['seconds'] = time.perf_counter() - started
    return selected, pcm, report, raw
