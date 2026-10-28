"""Opt-in v5 re-encoding with quiet/voice diagnostics and explicit level policy.

All search runs on the host. Existing streams remain controls; actual complete
bytes, PCM/PWM floors and source-bound voice proxies decide conservative output.
Raw alternatives are returned separately. Automatic quiet amplification is an
explicit option and changes playback level; it is never a hidden gain fit.
"""
from __future__ import annotations

import argparse
import json
from numbers import Integral
from pathlib import Path
import time

import numpy as np

import speech_compact as compact
import speech_v4
from speech_voice_objective import VoiceObjective
from standard_metrics import error_metrics, pwm_duties, pwm_pcm16
from refine_speech_compact import no_regression, quality as speech_quality
from voice_character import track_pitch, compare_voice
from voice_input import plan_level, quantize_target, load_voice_wav


def prepare_level(reference, policy='preserve'):
    """Return owned PCM16 target and declared power-of-two playback gain."""
    ref = np.asarray(reference)
    if (ref.ndim != 1 or ref.dtype.kind not in 'iu' or not 1 <= len(ref) <= 64000
            or int(ref.min()) < -32768 or int(ref.max()) > 32767):
        raise ValueError('Expected 1..64000 original PCM16 samples')
    if policy not in ('preserve', 'auto-quiet'):
        raise ValueError('Expected preserve or explicit auto-quiet level policy')
    values = ref.astype(np.int64)
    plan = plan_level(values, policy)
    target, clipped = quantize_target(values, plan)
    if clipped:
        raise AssertionError('Declared quiet gain clipped the input')
    return target, plan


def _quality(reference, pcm, speech):
    if speech:
        # Existing speech policy turns unavailable/nonfinite STOI into None;
        # NaN must never silently pass a numerical less-than floor check.
        return speech_quality(reference, pcm)
    return dict(pcm16=error_metrics(reference, pcm, speech),
                pwm8=error_metrics(reference, pwm_pcm16(pcm), speech))


def _voice_gate(new, old):
    if new['within_tolerance_frames'] < old['within_tolerance_frames']:
        return False
    if new['decoded_collapsed_active_frames'] > old['decoded_collapsed_active_frames']:
        return False
    for key in ('fixed_decoded_period_error_mean', 'relative_spectral_shape_rms_db_mean'):
        before, after = old[key], new[key]
        if before is not None and (after is None or after > before + 1e-12):
            return False
    return True


def encode(reference, profile, decoder, *, baseline=None, max_bytes=None,
           pre_values=(0, 8192, 13926), level_policy='preserve', speech=True,
           compact_decoder=None, candidate_sink=None):
    """Return selected stream/PCM, numeric report and best raw feasible stream.

    ``decoder`` must support both legacy v4 and compact v5. ``compact_decoder``
    optionally provides a second independent native v5-only receiver. If level
    changes, a fresh legacy control is encoded at the declared new target level;
    it is not falsely compared with an original-level control. A supplied old
    stream still supplies its real complete-byte cap unless explicitly changed.
    Missing feasible output is None, never a larger silent fallback.
    """
    target, level = prepare_level(reference, level_policy)
    if candidate_sink is not None and not callable(candidate_sink):
        raise ValueError('Expected a callable candidate sink')
    if isinstance(profile, bool) or profile not in (4, 6):
        raise ValueError('Expected speech profile 4 or 6')
    values = tuple(pre_values)
    if (not 1 <= len(values) <= 8 or any(isinstance(v, (bool, np.bool_))
            or not isinstance(v, Integral) or not 0 <= v <= 16384 for v in values)):
        raise ValueError('Expected 1..8 valid preQ14 candidates')
    values = tuple(dict.fromkeys(map(int, values)))
    if max_bytes is not None and (isinstance(max_bytes, (bool, np.bool_))
            or not isinstance(max_bytes, Integral) or max_bytes < 22):
        raise ValueError('Expected complete-stream byte cap >=22')
    previous = None if baseline is None else bytes(baseline)
    if previous is not None:
        fields = compact.unpack(previous)
        if fields[0] != len(target) or fields[1] != profile:
            raise ValueError('Original stream profile/length does not match reference')
    begin = time.perf_counter()
    track = track_pitch(target)
    objective = VoiceObjective(target, track.period)
    trials = []
    fresh_fit_calls = 0

    def verify(blob, expected=None):
        modeled = compact.decode_model(blob)
        if expected is not None and not np.array_equal(modeled, expected):
            raise AssertionError('V4/v5 model outputs differ')
        for receiver in (decoder, compact_decoder):
            if receiver is None:
                continue
            actual = receiver.decode_one_s16(blob, len(target))
            pwm = receiver.decode_one(blob, len(target))
            if (actual is None or pwm is None or not np.array_equal(actual, modeled)
                    or not np.array_equal(pwm, pwm_duties(modeled))):
                raise AssertionError('Voice candidate native/model PCM/PWM mismatch')
        return modeled

    def fresh(pre, allow_zero):
        nonlocal fresh_fit_calls
        fresh_fit_calls += 1
        legacy, expected, work = speech_v4.encode(target, profile, decoder, pre=pre,
                                                 allow_zero_scale=allow_zero)
        blob, _ = compact.repack(legacy)
        pcm = verify(blob, expected)
        return blob, pcm, work

    if previous is not None and level['gain'] == 1:
        control, control_pcm = previous, verify(previous)
        control_kind = 'existing_original_level_v5'
    else:
        control, control_pcm, _ = fresh(13926, False)
        control_kind = 'fresh_legacy_at_declared_target_level'
    cap = int(max_bytes if max_bytes is not None else len(previous) if previous is not None else len(control))
    before = _quality(target, control_pcm, bool(speech))
    before_voice = compare_voice(target, control_pcm, reference_track=track)
    before_pwm_voice = compare_voice(target, pwm_pcm16(control_pcm), reference_track=track)
    target_pwm_voice = compare_voice(target, pwm_pcm16(target), reference_track=track)
    before_score = objective(control_pcm)
    if candidate_sink is not None:
        candidate_sink(control)
    selected = control if len(control) <= cap else None
    selected_pcm = control_pcm if selected is not None else None
    selected_score = before_score if selected is not None else np.inf
    raw = selected
    raw_score = selected_score
    chosen = dict(metrics=before, voice=before_voice, pwm_voice=before_pwm_voice) if selected is not None else None
    for pre in values:
        blob, pcm, work = fresh(pre, True)
        if candidate_sink is not None:
            candidate_sink(blob)
        score = objective(pcm)
        metrics = _quality(target, pcm, bool(speech))
        voice = compare_voice(target, pcm, reference_track=track)
        pwm_voice = compare_voice(target, pwm_pcm16(pcm), reference_track=track)
        fits = len(blob) <= cap
        old_floors = no_regression(metrics, before)
        pcm_voice_floors = _voice_gate(voice, before_voice)
        pwm_voice_floors = _voice_gate(pwm_voice, before_pwm_voice)
        voice_floors = pcm_voice_floors and pwm_voice_floors
        trials.append(dict(preQ14=pre, allow_zero_scale=True, file_bytes=len(blob),
            fits_complete_cap=fits, old_pcm_pwm_floors_passed=old_floors,
            voice_proxy_floors_passed=voice_floors, voice_score=score,
            pcm_voice_proxy_floors_passed=pcm_voice_floors,
            pwm_voice_proxy_floors_passed=pwm_voice_floors,
            components=objective.components(pcm), metrics=metrics, voice=voice, pwm_voice=pwm_voice,
            encoder_seconds=work['seconds']))
        if fits and score < raw_score:
            raw, raw_score = blob, score
        if fits and old_floors and voice_floors and score < selected_score:
            selected, selected_pcm, selected_score = blob, pcm, score
            chosen = dict(metrics=metrics, voice=voice, pwm_voice=pwm_voice)
    if selected is not None:
        verify(selected, selected_pcm)
    if raw is not None and raw != selected:
        verify(raw)
    report = dict(schema='lpx-v5-voice-encoder-v1', profile=profile, samples=len(target),
        complete_byte_cap=cap, level=level, control_kind=control_kind, fresh_fit_calls=fresh_fit_calls,
        control_bytes=len(control), baseline_metrics=before, baseline_voice=before_voice,
        baseline_pwm_voice=before_pwm_voice, target_pwm_voice=target_pwm_voice,
        voice_proxy_gate_domains=['native_pcm16', 'fixed_pwm8'],
        baseline_voice_score=before_score, objective=objective.describe(), trials=trials,
        selected_bytes=None if selected is None else len(selected), selected=chosen,
        selected_voice_score=None if selected is None else selected_score,
        selected_differs_from_control=selected is not None and selected != control,
        raw_bytes=None if raw is None else len(raw), raw_voice_score=None if raw is None else raw_score,
        raw_quality_adopted=raw is not None and raw == selected,
        native_common_and_model_exact=True, native_v5_only_checked=compact_decoder is not None,
        decoder_and_format_unchanged=True, seconds=time.perf_counter()-begin,
        scope='Finite opt-in candidate grid; missing pitch remains failure/unknown. No audibility or real-time claim.')
    return selected, selected_pcm, report, raw


def main():
    import soundfile as sf
    from batch_decoder import BatchSession
    from output_paths import protect_outputs
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--profile', type=int, choices=(4, 6), default=4)
    parser.add_argument('--max-bytes', type=int)
    parser.add_argument('--level-policy', choices=('preserve', 'auto-quiet'), default='auto-quiet')
    parser.add_argument('--non-speech', action='store_true')
    parser.add_argument('--search-mode', choices=('adaptive', 'grid'), default='adaptive')
    parser.add_argument('--refinement-calls', type=int, default=4,
                        help='Bound expensive refinement calls; each has separate local work bounds')
    args = parser.parse_args()
    paths = [args.output/name for name in ('audio.l4hy', 'decoded.wav', 'raw.l4hy', 'raw.wav', 'report.json', 'target.wav')]
    inputs = [args.reference] + ([] if args.baseline is None else [args.baseline])
    protect_outputs(inputs, paths)
    if any(path.exists() for path in paths):
        raise ValueError('Use fresh output names; an absent result must not leave stale audio')
    reference, input_info = load_voice_wav(args.reference, args.level_policy)
    old = None if args.baseline is None else args.baseline.read_bytes()
    if old is not None:
        fields = compact.unpack(old)
        if fields[0] != len(reference) or fields[1] != args.profile:
            raise ValueError('Original stream profile/length does not match reference')
    gain_changed = input_info['input_level']['gain_power2_exponent'] != 0
    cap = args.max_bytes if args.max_bytes is not None else len(old) if old is not None else None
    with BatchSession('batch', speech=True, speech_compact=True) as common, BatchSession(
            'batch', speech=True, speech_compact=True, compact_only=True) as only:
        search = encode
        settings = {}
        if args.search_mode == 'adaptive':
            from adaptive_speech_voice import encode as search
            settings['max_refinement_calls'] = args.refinement_calls
        selected, pcm, report, raw = search(reference, args.profile, common,
            baseline=None if gain_changed else old, max_bytes=cap, level_policy='preserve',
            speech=not args.non_speech, compact_decoder=only, **settings)
    args.output.mkdir(parents=True, exist_ok=True)
    if selected is not None:
        paths[0].write_bytes(selected)
        sf.write(paths[1], pcm, 8000, subtype='PCM_16')
    if raw is not None:
        paths[2].write_bytes(raw)
        sf.write(paths[3], compact.decode_model(raw), 8000, subtype='PCM_16')
    sf.write(paths[5], reference, 8000, subtype='PCM_16')
    report['prepared_target_encoding_level'] = report['level']
    report['level'] = input_info['input_level']
    report['original_baseline_used_as_byte_cap_only'] = old is not None and gain_changed
    report['input_conversion'] = input_info
    report['search_mode'] = args.search_mode
    paths[4].write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('profile', 'samples', 'complete_byte_cap',
                                                 'selected_bytes', 'raw_bytes', 'seconds')}))


if __name__ == '__main__':
    main()
