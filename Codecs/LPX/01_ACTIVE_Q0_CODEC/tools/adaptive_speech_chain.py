"""Retain bounded voice-search prefixes and admit complete v5 recordings.

All quality and byte decisions concern the complete ordered reset chain.
Local histories specify candidates, never cached whole-record metric claims.
The baseline and supplied earlier incumbents remain in the measured pool.
"""
from __future__ import annotations

from numbers import Integral
import time

import numpy as np

import adaptive_speech_voice as local_search
import speech_compact as compact
from refine_speech_compact import quality, no_regression
from speech_chain_history import retained_prefixes
from speech_noise_objective import NoiseObjective
from standard_metrics import pwm_duties, pwm_pcm16
from voice_character import track_pitch, compare_voice
from voice_input import plan_level, quantize_target


def _integer(value, lower, upper, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral) or not lower <= value <= upper:
        raise ValueError('Invalid ' + name)
    return int(value)


def _inputs(reference, baseline_streams):
    ref = np.asarray(reference)
    if (ref.ndim != 1 or ref.dtype.kind not in 'iu' or not len(ref)
            or np.any(ref < -32768) or np.any(ref > 32767)):
        raise ValueError('Expected complete mono PCM16 reference')
    if isinstance(baseline_streams, (bytes, bytearray, str)):
        raise ValueError('Expected ordered reset streams')
    baseline = tuple(bytes(blob) for blob in baseline_streams)
    if not 1 <= len(baseline) <= 255:
        raise ValueError('Expected 1..255 ordered reset streams')
    geometry = [compact.unpack(blob)[:2] for blob in baseline]
    if (any(not 1 <= n <= 64000 or len(blob) > 65535
            for blob, (n, _) in zip(baseline, geometry))
            or sum(n for n, _ in geometry) != len(ref)):
        raise ValueError('Reset streams do not cover the complete reference')
    return ref.astype(np.int16, copy=True), baseline, geometry


def choose_budget(rows, max_bytes, *, max_flash_bytes=None):
    """Choose from freshly measured whole rows; data and Flash caps differ."""
    cap = _integer(max_bytes, 22, 255 * 65535, 'complete chain byte cap')
    if max_flash_bytes is not None:
        _integer(max_flash_bytes, 1, 2**32 - 1, 'full Flash cap')
        if any(row.get('full_flash_bytes') is None for row in rows):
            raise ValueError('A Flash cap requires actual complete-image measurements')
    fitting = [row for row in rows if row['stream_bytes'] <= cap
               and (max_flash_bytes is None or row['full_flash_bytes'] <= max_flash_bytes)]
    eligible = [row for row in fitting if row['automatic_quality_eligible']]
    key = lambda row: (row['score'], row['stream_bytes'], row['id'])
    return dict(cap=cap, full_flash_cap=max_flash_bytes,
        selected_id=None if not eligible else min(eligible, key=key)['id'],
        raw_id=None if not fitting else min(fitting, key=key)['id'],
        fitting_chains=len(fitting), eligible_chains=len(eligible),
        no_fit=not fitting, no_automatic_admission=not eligible)


def _measure(target, pcm, speech, track, noise):
    voice = noise.voice_objective
    domains = (pcm, pwm_pcm16(pcm))
    summaries = [noise.summary(domain) for domain in domains]
    scores = [float(voice(domain) + summary['score'])
              for domain, summary in zip(domains, summaries)]
    if not np.isfinite(scores).all():
        raise ValueError('Whole-record objective must be finite')
    return dict(metrics=quality(target, pcm, speech),
        voice=compare_voice(target, pcm, reference_track=track),
        pwm_voice=compare_voice(target, domains[1], reference_track=track),
        noise=summaries[0], pwm_noise=summaries[1], domain_scores=scores,
        score=float(np.mean(scores)),
        clipped_samples=int(np.count_nonzero((pcm <= -32768) | (pcm >= 32767))),
        voice_components=voice.components(pcm), pwm_voice_components=voice.components(domains[1]))


def _admission(row, baseline):
    return dict(old_pcm_pwm_floors_passed=bool(no_regression(row['metrics'], baseline['metrics'])),
        clipped_sample_floor_passed=row['clipped_samples'] <= baseline['clipped_samples'],
        pcm_period_coverage_floor_passed=(row['voice']['within_tolerance_frames']
                                        >= baseline['voice']['within_tolerance_frames']),
        pwm_period_coverage_floor_passed=(row['pwm_voice']['within_tolerance_frames']
                                        >= baseline['pwm_voice']['within_tolerance_frames']),
        joint_objective_nonregression=row['score'] <= baseline['score'] + 1e-12)


def select_candidates(reference, baseline_streams, histories, decoder, *, max_bytes,
                      compact_decoder=None, speech=True, incumbents=(), candidate_sink=None,
                      firmware_cost=None, max_flash_bytes=None):
    """Measure retained prefixes; return selected streams/PCM/report/raw.

    Histories contain ``index``, actual ``pool`` bytes, and a local adaptive
    ``report``. They may cover only some resets. Local score/eligibility fields
    recover snapshots; all final native/model output and whole quality gates
    are recomputed here. Extra ``incumbents`` are complete ordered byte tuples,
    not trusted metric claims. Sink receives (whole candidate ID, stream tuple).
    """
    started = time.perf_counter()
    target, baseline, geometry = _inputs(reference, baseline_streams)
    cap = _integer(max_bytes, 22, 255 * 65535, 'complete chain byte cap')
    local_search._validate_settings(0, 'default', 1, firmware_cost, max_flash_bytes)
    if decoder is None or candidate_sink is not None and not callable(candidate_sink):
        raise ValueError('Expected a native decoder and optional callable candidate sink')
    histories = list(histories)
    chains = retained_prefixes(baseline, histories, incumbents)
    # Verify every supplied history blob's geometry, including unselected rows.
    for history in histories:
        if any(compact.unpack(blob)[:2] != geometry[history['index']] for blob in history['pool']):
            raise ValueError('A local history changed reset geometry/profile')
    track = track_pitch(target)
    noise = NoiseObjective(target, track.period)
    decoded, rows, selected_pcm = {}, [], None
    counters = dict(unique_reset_streams=0, model_samples=0,
                    native_output_domain_comparisons=0, whole_metric_rows=0)
    for chain in chains:
        parts = []
        for blob, expected in zip(chain['streams'], geometry):
            if compact.unpack(blob)[:2] != expected:
                raise ValueError('A retained chain changed reset geometry/profile')
            if blob not in decoded:
                pcm = compact.decode_model(blob)
                if len(pcm) != expected[0]:
                    raise AssertionError('Model output length differs from reset geometry')
                expected_duty = pwm_duties(pcm)
                for receiver in (decoder, compact_decoder):
                    if receiver is None:
                        continue
                    actual = receiver.decode_one_s16(blob, len(pcm))
                    duty = receiver.decode_one(blob, len(pcm))
                    if (actual is None or duty is None or not np.array_equal(actual, pcm)
                            or not np.array_equal(duty, expected_duty)):
                        raise AssertionError('Whole-chain native/model PCM/PWM mismatch')
                    counters['native_output_domain_comparisons'] += 2
                decoded[blob] = pcm
                counters['unique_reset_streams'] += 1
                counters['model_samples'] += len(pcm)
            parts.append(decoded[blob])
        pcm = np.concatenate(parts)
        value = _measure(target, pcm, bool(speech), track, noise)
        counters['whole_metric_rows'] += 1
        row = dict(id=chain['id'], labels=list(chain['labels']), stream_bytes=chain['stream_bytes'],
                   full_flash_bytes=None, **value)
        if firmware_cost is not None:
            row['full_flash_bytes'] = _integer(firmware_cost(chain['streams']), 1, 2**32 - 1,
                                               'measured complete image size')
        flags = _admission(row, row if not rows else rows[0])
        row.update(flags, automatic_quality_eligible=all(flags.values()))
        rows.append(row)
        # Retain PCM only while it can be the current selected winner.
        decision = choose_budget(rows, cap, max_flash_bytes=max_flash_bytes)
        if decision['selected_id'] == row['id']:
            selected_pcm = pcm
        if candidate_sink is not None:
            candidate_sink(row['id'], chain['streams'])
    decision = choose_budget(rows, cap, max_flash_bytes=max_flash_bytes)
    frontier, best_score = [], float('inf')
    for row in sorted(rows, key=lambda r: (r['stream_bytes'], r['score'], r['id'])):
        if row['automatic_quality_eligible'] and row['score'] < best_score:
            frontier.append(row['id'])
            best_score = row['score']
    selected_id, raw_id = decision['selected_id'], decision['raw_id']
    report = dict(schema='lpx-v5-adaptive-chain-v1', samples=len(target),
        reset_segments=len(baseline), profiles=[p for _, p in geometry],
        complete_byte_cap=cap, full_flash_measured=firmware_cost is not None,
        full_flash_cap=max_flash_bytes, candidates=rows, frontier=frontier, decision=decision,
        selected_id=selected_id, raw_id=raw_id,
        selected_bytes=None if selected_id is None else rows[selected_id]['stream_bytes'],
        raw_bytes=None if raw_id is None else rows[raw_id]['stream_bytes'],
        selected_differs_from_control=selected_id is not None and selected_id != 0,
        source_refinement_calls=sum(len(h['report']['stages']) for h in histories),
        new_refinement_calls=0, segment_searches=[
            dict(index=h['index'], report=h['report']) for h in histories],
        validation=counters, native_common_and_model_exact=True,
        native_v5_only_checked=compact_decoder is not None, decoder_and_format_unchanged=True,
        objective=dict(voice=noise.voice_objective.describe(), noise=noise.describe(),
            domains=['native_pcm16', 'fixed_pwm8'], aggregation='mean of voice + noise'),
        seconds=time.perf_counter()-started,
        scope='Bounded common-depth snapshots; whole gates are fresh. Data-byte frontier is not a full-Flash frontier or listening evidence.')
    return (None if selected_id is None else chains[selected_id]['streams'],
            None if selected_id is None else selected_pcm, report,
            None if raw_id is None else chains[raw_id]['streams'])


def refine_candidates(reference, baseline_streams, decoder, *, max_bytes, seeds=None,
                      anchors=None, segment_indices=None, compact_decoder=None, speech=True,
                      max_refinement_calls=4, lpc_preset='expanded', extra_full_evaluations=128,
                      incumbents=(), candidate_sink=None, firmware_cost=None, max_flash_bytes=None):
    """Run each requested local search once, retaining all complete prefixes."""
    started = time.perf_counter()
    target, baseline, geometry = _inputs(reference, baseline_streams)
    cap = _integer(max_bytes, 22, 255 * 65535, 'complete chain byte cap')
    local_search._validate_settings(max_refinement_calls, lpc_preset, extra_full_evaluations,
                                    firmware_cost, max_flash_bytes)
    if decoder is None or candidate_sink is not None and not callable(candidate_sink):
        raise ValueError('Expected a native decoder and optional callable candidate sink')
    seeds = [()] * len(baseline) if seeds is None else list(seeds)
    anchors = baseline if anchors is None else tuple(anchors)
    if len(seeds) != len(baseline) or len(anchors) != len(baseline):
        raise ValueError('Expected one seed pool and anchor per reset')
    indices = list(range(len(baseline))) if segment_indices is None else list(segment_indices)
    if (any(type(i) is not int or not 0 <= i < len(baseline) for i in indices)
            or indices != sorted(set(indices))):
        raise ValueError('Expected unique ordered searched reset indices')
    for index in indices:
        if isinstance(seeds[index], (bytes, bytearray, str)):
            raise ValueError('Expected a pool of seed streams per reset')
        seeds[index] = tuple(bytes(blob) for blob in seeds[index])
        if any(compact.unpack(blob)[:2] != geometry[index]
               for blob in (anchors[index], *seeds[index])):
            raise ValueError('A local anchor/seed changed reset geometry/profile')
    histories = []
    starts = np.cumsum([0] + [n for n, _ in geometry]).tolist()
    for index in indices:
        pool = []
        _, _, report, _ = local_search.refine_candidates(
            target[starts[index]:starts[index+1]], anchors[index], seeds[index], decoder,
            max_bytes=min(cap, 65535), compact_decoder=compact_decoder, speech=speech,
            max_refinement_calls=max_refinement_calls, lpc_preset=lpc_preset,
            extra_full_evaluations=extra_full_evaluations, candidate_sink=pool.append)
        histories.append(dict(index=index, pool=pool, report=report))
    selected, pcm, report, raw = select_candidates(target, baseline, histories, decoder,
        max_bytes=cap, compact_decoder=compact_decoder, speech=speech, incumbents=incumbents,
        candidate_sink=candidate_sink, firmware_cost=firmware_cost, max_flash_bytes=max_flash_bytes)
    report.update(new_refinement_calls=report['source_refinement_calls'],
                  max_refinement_calls_per_reset=int(max_refinement_calls),
                  seconds=time.perf_counter()-started)
    return selected, pcm, report, raw


def encode(reference, baseline_streams, decoder, *, max_bytes=None, level_policy='preserve',
           pre_values=(0, 8192, 13926), compact_decoder=None, speech=True,
           baseline_at_target_level=True, **settings):
    """Fit seed grids at one whole-input level, then retain search prefixes.

    Supplied reset streams define geometry and the default total byte cap.
    When the declared gain changes, fresh target-level legacy controls replace
    original-level controls for quality admission, exactly as in single-reset
    encoding. They are fitted once per reset, before the three optional seeds.
    """
    from encode_speech_voice import encode as seed_encode
    started = time.perf_counter()
    if type(baseline_at_target_level) is not bool:
        raise ValueError('Expected an explicit baseline target-level declaration')
    if decoder is None or (settings.get('candidate_sink') is not None
                           and not callable(settings['candidate_sink'])):
        raise ValueError('Expected a native decoder and optional callable candidate sink')
    local_search._validate_settings(settings.get('max_refinement_calls', 4),
        settings.get('lpc_preset', 'expanded'), settings.get('extra_full_evaluations', 128),
        settings.get('firmware_cost'), settings.get('max_flash_bytes'))
    reference, original, geometry = _inputs(reference, baseline_streams)
    level = plan_level(reference, level_policy)
    target, clipped = quantize_target(reference, level)
    if clipped:
        raise AssertionError('Declared whole-input quiet gain clipped')
    cap = sum(map(len, original)) if max_bytes is None else max_bytes
    _integer(cap, 22, 255 * 65535, 'complete chain byte cap')
    controls, anchors, seeds, seed_reports = [], [], [], []
    same_level = baseline_at_target_level and level['gain_power2_exponent'] == 0
    start = 0
    for old, (count, profile) in zip(original, geometry):
        pool = []
        selected, _, report, _ = seed_encode(target[start:start+count], profile, decoder,
            baseline=old if same_level else None,
            max_bytes=min(cap, 65535), pre_values=pre_values, level_policy='preserve',
            speech=speech, compact_decoder=compact_decoder, candidate_sink=pool.append)
        controls.append(pool[0])
        anchors.append(pool[0] if selected is None else selected)
        seeds.append(pool)
        seed_reports.append(report)
        start += count
    selected, pcm, report, raw = refine_candidates(target, controls, decoder, max_bytes=cap,
        seeds=seeds, anchors=anchors, compact_decoder=compact_decoder, speech=speech, **settings)
    report.update(level=level, seed_searches=seed_reports,
        fresh_fit_calls=sum(row['fresh_fit_calls'] for row in seed_reports),
        original_baseline_used_as_byte_cap_only=not same_level,
        seconds=time.perf_counter()-started)
    return selected, pcm, report, raw
