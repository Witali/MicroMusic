"""Remove redundant stored v5 extras without changing decoded PCM/PWM.

This is equality to the input codec stream, not losslessness to the source WAV.
Spectra, scale/lag/gain, base pulses, pre-emphasis and brightness are preserved.
Every public result is checked through both native layouts and the integer model.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
from pathlib import Path

import numpy as np
from numba import njit

from batch_decoder import BatchSession
from q0_model import table
import speech_compact as compact
from standard_metrics import pwm_duties


@njit(cache=True)
def _prune(params, pulses, extras, steps, samples):
    """Conservative q dependency DAG followed by an exact forward clipping pass."""
    live = np.empty(samples, np.bool_)
    for at in range(samples):
        live[at] = steps[params[at // 160, 0] * 8] != 0
    for at in range(samples - 1, -1, -1):
        _, lag, gain = params[at // 160]
        if live[at] and gain and at >= lag:
            live[at - lag] = True

    pruned = extras.copy()
    tail = unobservable = 0
    for index in range(len(pruned)):
        position, amplitude = pruned[index]
        if not amplitude:
            pruned[index, 0] = -1
            continue
        at = index * 40 + position
        if at >= samples:
            tail += 1
        elif not live[at]:
            unobservable += 1
        else:
            continue
        pruned[index, 0] = -1
        pruned[index, 1] = 0
    after_dead = pruned.copy()

    old_ring = np.zeros(256, np.int64)
    new_ring = np.zeros(256, np.int64)
    saturated = changed_dead_q = observable = 0
    for at in range(samples):
        scale, lag, gain = params[at // 160]
        position, amplitude = pulses[at // 20]
        base = amplitude if at % 20 == position else 0
        chunk = at // 40
        old_position, old_amplitude = extras[chunk]
        extra = old_amplitude if at % 40 == old_position else 0
        old_prediction = (gain * old_ring[(at - lag) & 255] + 8) >> 4
        old_q = min(31, max(-32, old_prediction + base + extra))

        prediction = (gain * new_ring[(at - lag) & 255] + 8) >> 4
        position, amplitude = pruned[chunk]
        extra = amplitude if at % 40 == position else 0
        without = min(31, max(-32, prediction + base))
        new_q = min(31, max(-32, prediction + base + extra))
        if extra and new_q == without:
            pruned[chunk, 0] = -1
            pruned[chunk, 1] = 0
            saturated += 1

        if live[at]:
            observable += 1
            if old_q != new_q:
                raise AssertionError('Observable excitation changed')
        elif old_q != new_q:
            changed_dead_q += 1
        if old_q * steps[scale * 8] != new_q * steps[scale * 8]:
            raise AssertionError('Excitation drive changed')
        old_ring[at & 255] = old_q
        new_ring[at & 255] = new_q
    return after_dead, pruned, tail, unobservable, saturated, observable, changed_dead_q


def _cleanup_once(blob):
    """Private deterministic transform; fixed-point checks never recurse into validation."""
    fields = compact.unpack(blob)
    samples, profile, spectra, params, pulses, pre, bright, extras = fields
    original_extras = np.asarray(extras, np.int64)
    forced = bool(blob[5] & 128)
    canonical, canonical_meta = compact.pack(*fields[:7], extras=extras, force_extras=forced)
    after_dead, final_extras, tail, dead, saturated, observable, changed_q = _prune(
        np.asarray(params, np.int64), np.asarray(pulses, np.int64),
        original_extras, table('scale_table.inc'), samples)
    dead_blob, _ = compact.pack(*fields[:7], extras=after_dead, force_extras=forced)
    saturated_blob, _ = compact.pack(*fields[:7], extras=final_extras, force_extras=forced)
    final, final_meta = compact.pack(*fields[:7], extras=final_extras)
    if not len(final) <= len(saturated_blob) <= len(dead_blob) <= len(canonical) <= len(blob):
        raise AssertionError('Exact cleanup grew serialized data')
    if compact.unpack(final)[:7] != fields[:7]:
        raise AssertionError('Non-extra v5 fields changed')
    report = {
        'samples': samples, 'profile': profile, 'stored_samples': len(spectra) * 320,
        'original_bytes': len(blob), 'canonical_bytes': len(canonical),
        'after_dead_bytes': len(dead_blob), 'after_saturated_bytes': len(saturated_blob),
        'file_bytes': len(final), 'saved_bytes': len(blob) - len(final),
        'canonical_repack_saved_bytes': len(blob) - len(canonical),
        'dead_active_removal_saved_bytes': len(canonical) - len(dead_blob),
        'saturated_active_removal_saved_bytes': len(dead_blob) - len(saturated_blob),
        'empty_marker_layer_saved_bytes': len(saturated_blob) - len(final),
        'legal_marker_one_amplitude_zero_count': int(np.count_nonzero(
            (original_extras[:, 0] >= 0) & (original_extras[:, 1] == 0))),
        'original_active_extras': int(np.count_nonzero(original_extras[:, 1])),
        'final_active_extras': int(np.count_nonzero(final_extras[:, 1])),
        'unplayed_tail_extras_removed': int(tail),
        'unobservable_extras_removed': int(dead),
        'saturation_equivalent_extras_removed': int(saturated),
        'observable_q_samples': int(observable), 'unobservable_q_samples': samples - int(observable),
        'changed_unobservable_q_samples': int(changed_q),
        'canonical_payload_bits': canonical_meta['payload_bits'],
        'final_payload_bits': final_meta['payload_bits'],
        'original_extra_marker_layer': forced, 'final_extra_marker_layer': final_meta['enhanced'],
        'non_extra_fields_preserved': True, 'mandatory_stored_tail_preserved': True,
        'nonzero_drive_exact': True,
    }
    return final, report


def cleanup(blob, *, common=None, compact_only=None):
    """Return (owned immutable stream, numeric report) after complete exact admission.

    Optional sessions must implement BatchSession's PCM16 and PWM methods. Reuse
    them across a corpus; absent sessions are created and closed here. Every real
    reset segment is transformed independently. No waveform metric or reference
    recording is used to decide which extras can be removed.
    """
    if not isinstance(blob, (bytes, bytearray, memoryview)):
        raise ValueError('Expected a complete v5 byte stream')
    original = bytes(blob)
    final, report = _cleanup_once(original)
    fixed, _ = _cleanup_once(final)
    if fixed != final:
        raise AssertionError('Exact cleanup is not idempotent')
    samples = report['samples']
    old_pcm = compact.decode_model(original)
    new_pcm = old_pcm if final == original else compact.decode_model(final)
    if not np.array_equal(old_pcm, new_pcm):
        raise AssertionError('Integer model PCM changed')
    expected_pwm = pwm_duties(old_pcm)
    unique = (original,) if original == final else (original, final)
    with ExitStack() as stack:
        if common is None:
            common = stack.enter_context(BatchSession('batch', v3_features=124,
                                                      speech=True, speech_compact=True))
        if compact_only is None:
            compact_only = stack.enter_context(BatchSession('batch', v3_features=124,
                                                            speech=True, speech_compact=True,
                                                            compact_only=True))
        for decoder in (common, compact_only):
            for candidate in unique:
                actual = decoder.decode_one_s16(candidate, samples)
                pwm = decoder.decode_one(candidate, samples)
                if actual is None or not np.array_equal(actual, old_pcm):
                    raise AssertionError('Native PCM differs from the original integer model')
                if pwm is None or not np.array_equal(pwm, expected_pwm):
                    raise AssertionError('Native PWM differs from the original integer model')
    report.update(idempotent=True, model_pcm_pwm_exact=True, native_common_pcm_pwm_exact=True,
                  native_v5_only_pcm_pwm_exact=True, unique_streams_verified=len(unique),
                  native_output_domain_comparisons=4 * len(unique), changed=original != final)
    return final, report


def main():
    from output_paths import protect_outputs
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    protect_outputs([args.input], [args.output])
    final, report = cleanup(args.input.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(final)
    print(json.dumps(report, allow_nan=False))


if __name__ == '__main__':
    main()
