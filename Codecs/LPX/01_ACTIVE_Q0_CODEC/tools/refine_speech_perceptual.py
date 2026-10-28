"""Explicit full-waveform v5 objective search with unchanged automatic floors.

The selected stream must pass the existing PCM/PWM no_regression gate. Keep
the raw best feasible objective alternative separate for blind listening; an
objective improvement is not evidence that an audio change is audible.
"""
from __future__ import annotations

import argparse
import json
from numbers import Integral
from pathlib import Path
import time

import numpy as np
import speech_compact as compact
from refine_speech_compact import no_regression, quality
from speech_objective import SpeechObjective
from standard_metrics import pwm_duties


def refine(reference, blob, decoder, max_bytes, *, mode='perceptual',
           gamma1=.9, gamma2=.6, **search_settings):
    """Return conservative bytes/PCM/report and a separate listening candidate.

    Reconstruct each returned stream through the receiver and independent
    integer model, and independently repeat the automatic quality gate. The
    input may exceed the cap, as supported by the trajectory refiner; returned
    candidates must fit, and a missing conservative fit remains explicit.
    """
    from refine_speech_trajectory import refine as trajectory_refine
    if (isinstance(max_bytes, (bool, np.bool_)) or not isinstance(max_bytes, Integral)
            or not 22 <= max_bytes <= 65535):
        raise ValueError('Expected a complete-file byte cap in 22..65535')
    if any(name in search_settings for name in ('objective', 'objective_name', 'selection')):
        raise ValueError('Objective wrapper preserves conservative selection')
    started = time.perf_counter()
    objective = SpeechObjective.from_v5(reference, blob, mode=mode,
                                       gamma1=gamma1, gamma2=gamma2)
    samples = len(reference)
    reference = np.asarray(reference)
    checked = {}

    def verify(data, enforce_cap):
        if data is None:
            return None
        if enforce_cap and len(data) > max_bytes:
            raise AssertionError('Objective candidate exceeds complete-file cap')
        data = bytes(data)
        if data not in checked:
            pcm = decoder.decode_one_s16(data, samples)
            if pcm is None or not np.array_equal(pcm, compact.decode_model(data)):
                raise AssertionError('Objective candidate native/model mismatch')
            if not np.array_equal(decoder.decode_one(data, samples), pwm_duties(pcm)):
                raise AssertionError('Objective candidate native PWM mismatch')
            checked[data] = (pcm, quality(reference, pcm), objective(pcm))
        return checked[data]

    baseline = verify(blob, False)
    selected, pcm, report, raw = trajectory_refine(
        reference, blob, decoder, max_bytes, objective=objective,
        objective_name=objective.name, selection='conservative', **search_settings)
    actual = verify(selected, True)
    alternative = verify(raw, True)
    if actual is not None:
        if not np.array_equal(actual[0], pcm):
            raise AssertionError('Objective selected snapshot mismatch')
        if not no_regression(actual[1], baseline[1]):
            raise AssertionError('Objective wrapper conservative gate failed')
    elif pcm is not None:
        raise AssertionError('Missing selected stream has a PCM snapshot')
    report = dict(report)
    report.update(objective=objective.describe(), baseline=baseline[1],
                  selected=None if actual is None else actual[1],
                  baseline_objective=baseline[2],
                  selected_objective=None if actual is None else actual[2],
                  raw_best=None if alternative is None else alternative[1],
                  raw_objective=None if alternative is None else alternative[2],
                  raw_conservative_floors_passed=False if alternative is None else
                      bool(no_regression(alternative[1], baseline[1])),
                  raw_listening_candidate_separate=True,
                  native_model_pwm_exact=True, automatic_floors_unchanged=True,
                  wrapper_seconds=time.perf_counter() - started)
    return selected, pcm, report, raw


def main():
    import soundfile as sf
    from batch_decoder import BatchSession
    from output_paths import protect_outputs
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference', type=Path)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--max-bytes', required=True, type=int)
    parser.add_argument('--objective', choices=('sse', 'perceptual'), default='perceptual')
    parser.add_argument('--gamma1', type=float, default=.9)
    parser.add_argument('--gamma2', type=float, default=.6)
    parser.add_argument('--frames', type=int, default=8)
    parser.add_argument('--window-frames', type=int, default=2)
    parser.add_argument('--beam', type=int, default=3)
    parser.add_argument('--evaluations', type=int, default=512)
    args = parser.parse_args()
    paths = [args.output / name for name in ('audio.l4hy', 'decoded.wav', 'raw.l4hy',
                                             'raw.wav', 'report.json')]
    protect_outputs([args.reference, args.input], paths)
    if any(path.exists() for path in paths):
        raise ValueError('Use fresh output paths so a no-fit result cannot leave stale audio')
    reference, rate = sf.read(args.reference, dtype='int16')
    if rate != 8000:
        raise ValueError('Reference must be 8 kHz')
    with BatchSession('batch', speech=True, speech_compact=True, compact_only=True) as decoder:
        selected, pcm, report, raw = refine(
            reference, args.input.read_bytes(), decoder, args.max_bytes,
            mode=args.objective, gamma1=args.gamma1, gamma2=args.gamma2,
            frame_limit=args.frames, window_frames=args.window_frames,
            beam_width=args.beam, max_evaluations=args.evaluations)
        args.output.mkdir(parents=True, exist_ok=True)
        if selected is not None:
            paths[0].write_bytes(selected)
            sf.write(paths[1], pcm, 8000, subtype='PCM_16')
        if raw is not None:
            paths[2].write_bytes(raw)
            sf.write(paths[3], decoder.decode_one_s16(raw, len(reference)), 8000, subtype='PCM_16')
    paths[4].write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'objective': args.objective, 'selected_bytes':
                     None if selected is None else len(selected), 'raw_bytes':
                     None if raw is None else len(raw),
                     'seconds': report['wrapper_seconds']}))


if __name__ == '__main__':
    main()
