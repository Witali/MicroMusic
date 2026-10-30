"""Recheck saved target winners and export anonymous numerical evidence.

No fitting or refinement. Private bindings/media fingerprints are verified
locally and never copied into the public projection. The complete search pool
was not retained for this exploratory target run; only its endpoints are audited.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import soundfile as sf

from batch_decoder import BatchSession
import speech_compact as compact
from encode_speech_voice import _quality
from speech_noise_objective import NoiseObjective
from standard_metrics import pwm_duties, pwm_pcm16
from voice_character import track_pitch, compare_voice


def sha(data):
    return hashlib.sha256(data).hexdigest()


def close(actual, expected):
    if isinstance(expected, dict):
        for key, value in expected.items():
            close(actual[key], value)
    elif isinstance(expected, list):
        if len(actual) != len(expected):
            raise AssertionError('Different array geometry')
        for left, right in zip(actual, expected):
            close(left, right)
    elif isinstance(expected, float):
        if not np.isfinite(actual) or abs(actual-expected) > 1e-12:
            raise AssertionError('Saved numerical outcome differs')
    elif actual != expected:
        raise AssertionError('Saved target claim differs')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-root', 'study', 'reference', 'baseline', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    root, study = args.source_root.resolve(), args.study.resolve()
    if args.output.exists():
        raise ValueError('Use a fresh projection filename')
    binding = json.loads((study/'binding-private.json').read_text(encoding='utf-8-sig'))
    for relative, digest in binding['core'].items():
        if sha((root/relative).read_bytes()) != digest:
            raise ValueError('The frozen implementation changed')
    for module in (compact,):
        if Path(module.__file__).resolve().parent != root/'Codecs/LPX/01_ACTIVE_Q0_CODEC/tools':
            raise ValueError('A local primitive belongs to another checkout')
    ref, rate = sf.read(args.reference, dtype='int16')
    baseline = args.baseline.read_bytes()
    if (rate != 8000 or ref.ndim != 1 or len(ref) != binding['samples']
            or sha(ref.astype('<i2').tobytes()) != binding['target_sha256']
            or sha(baseline) != binding['control_sha256']):
        raise ValueError('Saved source/control binding differs')
    track = track_pitch(ref)
    noise = NoiseObjective(ref, track.period)
    voice = noise.voice_objective
    native_comparisons = 0
    with BatchSession('batch', speech=True, speech_compact=True) as common, BatchSession(
            'batch', speech=True, speech_compact=True, compact_only=True) as only:
        def measure(blob):
            nonlocal native_comparisons
            pcm = compact.decode_model(blob)
            for receiver in (common, only):
                for actual, expected in ((receiver.decode_one_s16(blob, len(ref)), pcm),
                        (receiver.decode_one(blob, len(ref)), pwm_duties(pcm))):
                    if actual is None or not np.array_equal(actual, expected):
                        raise AssertionError('Target endpoint native/model mismatch')
                    native_comparisons += 1
            domains = [pcm, pwm_pcm16(pcm)]
            summaries = [noise.summary(data) for data in domains]
            scores = [voice(data)+item['score'] for data,item in zip(domains,summaries)]
            return dict(file_bytes=len(blob), metrics=_quality(ref,pcm,True),
                voice=compare_voice(ref,pcm,reference_track=track),
                pwm_voice=compare_voice(ref,domains[1],reference_track=track),
                noise=summaries[0],pwm_noise=summaries[1],domain_scores=scores,
                score=float(np.mean(scores)),clipped_samples=int(np.count_nonzero(
                    (pcm.astype(np.int64)<=-32768)|(pcm.astype(np.int64)>=32767))))
        control = measure(baseline)
        rows = []
        for cap in binding['caps']:
            folder = study/('cap-'+str(cap))
            marker = json.loads((folder/'complete-private.json').read_text())
            report = json.loads((folder/'report-private.json').read_text())
            blob = (folder/'selected.l4hy').read_bytes()
            if not marker['guard_pass'] or sha(blob) != marker['selected_sha256']:
                raise ValueError('Endpoint completion proof differs')
            actual = measure(blob)
            close(report['candidates'][report['selected_id']],actual)
            close(report['candidates'][0],control)
            if len(blob)>cap or report['refinement_calls'] != binding['max_refinement_calls']:
                raise ValueError('Search byte/work bound differs')
            rows.append(dict(cap=cap,selected=actual,refinement_calls=report['refinement_calls'],
                measured_pool_rows=len(report['candidates']),seconds=report['seconds']))
    result = dict(schema='lpx-adaptive-target-endpoints-v2',samples=len(ref),rate_hz=rate,
        declared_input_gain=binding['gain'],producer_head=binding['head'],
        producer_code_sha256=binding['core'],new_seed_fits=0,
        control=control,caps=rows,native_output_domain_comparisons=native_comparisons,
        native_sample_domain_comparisons=native_comparisons*len(ref),
        all_saved_endpoints_native_model_exact=True,
        full_search_pool_independently_audited=False,
        listening=dict(compared_caps=[1800,2060],outcome='inconclusive',larger_variant_adopted=False),
        scope='One targeted source; endpoint audit only; objective gains are not perceptual percentages or corpus-general evidence.')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(result,stream,indent=2,allow_nan=False)
        stream.write('\n')
    print(json.dumps(dict(status='pass',endpoints=len(rows)+1,native_domain_comparisons=native_comparisons)))


if __name__ == '__main__':
    main()
