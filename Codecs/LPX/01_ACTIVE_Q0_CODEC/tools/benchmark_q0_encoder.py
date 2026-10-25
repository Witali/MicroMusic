#!/usr/bin/env python3
"""Reproduce Q0 WAV/beam/joint experiments; retain metrics, keep audio external.

--corpus contains the four explicitly licensed files and sources.json listed
in the research report. --private-archive is optional and read-only. It is
used only to freeze/compare the historical training baseline, never copied
into a source release. Output media belong in an ignored build directory.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import time
import zipfile
import numpy as np
import soundfile as sf
from batch_decoder import BatchSession
from beam_excitation_pcm16 import optimize as beam_opt
from optimize_q0 import optimize as joint_opt, cost_probe, probe
from wav_lpc import load_wav
from wav_to_lpx4 import encode_segment, quality

ROOT = Path(__file__).resolve().parents[1]
LAMBDAS = (0., .0002, .001, .005, .02, .1, .5, 10.)


def run(corpus, output, report_path, private_archive=None, trials=1000, baseline_report=None):
    corpus, output, report_path = Path(corpus), Path(output), Path(report_path)
    output.mkdir(parents=True, exist_ok=True)
    sources = json.loads((corpus / 'sources.json').read_text(encoding='utf-8'))
    previous = json.loads(Path(baseline_report).read_text(encoding='utf-8')) if baseline_report else None
    cases = []
    for item in sources:
        path = corpus / (item['id'] + Path(item['url']).suffix)
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Corpus checksum mismatch: ' + item['id'])
        pcm, info = load_wav(path)
        pcm = pcm[:24000]  # Exact first three seconds, no trim/gain/alignment fitting.
        cases.append((item['id'], pcm, 'speech', item))
    music = ROOT.parent / '05_BENCHMARKS/INDEPENDENT_SPEECH_AND_MUSIC_2026-10-24/references/synthetic_music_12s.wav'
    pcm, _ = load_wav(music)
    cases.append(('synthetic_music', pcm[:24000], 'music',
                  {'source': str(music.relative_to(ROOT.parent)), 'sha256': hashlib.sha256(music.read_bytes()).hexdigest(),
                   'license': 'Original synthetic music from the imported project; no external recording'}))
    results = {'core_sha256': hashlib.sha256((ROOT / 'src/Lpx4HybridCore.cpp').read_bytes()).hexdigest(),
               'protocol': {'sample_rate': 8000, 'max_seconds': 3, 'target_codec_bps': 24000,
                            'lambda_grid': LAMBDAS, 'beam_trial_cap_per_configuration': trials,
                            'windows': '20 samples for beam 1/4/8/16, additionally 40 for beam 4',
                            'tail_samples': 80, 'tokens_per_window': 6,
                            'stoi_gate': 'No regression to starting stream, speech only',
                            'alignment': 'No fitted gain or temporal shift'},
               'training_baselines': [], 'cases': []}
    executable = cost_probe()
    with BatchSession('batch') as decoder:
        if private_archive:
            with zipfile.ZipFile(private_archive) as z:
                for key in ('chego', 'otvechaesh'):
                    prefix = f'07_PRIVATE_SPEECH_EXAMPLES/ACTIVE_Q0_AB/{key}/'
                    wav_bytes = z.read(prefix + 'original_pcm16.wav')
                    ref, rate = sf.read(io.BytesIO(wav_bytes), dtype='int16')
                    blob = z.read(prefix + 'optimized_l4hy.l4hy')
                    pcm = decoder.decode_one_s16(blob, len(ref))
                    if pcm is None or rate != 8000:
                        raise ValueError('Historical baseline decode failed')
                    item = {'id': key, 'bytes': len(blob), 'samples': len(ref),
                            'stream_sha256': hashlib.sha256(blob).hexdigest(),
                            'wav_sha256': hashlib.sha256(wav_bytes).hexdigest(),
                            'quality': quality(ref, pcm), 'decode_cost': probe(blob, executable)}
                    newer, out_pcm, joint = joint_opt(blob, ref, decoder, rounds=2,
                        lsf_trials=300, beam_trials=trials, header_trials=80, probe_executable=executable)
                    item['joint'] = joint
                    results['training_baselines'].append(item)
                    # Private data are kept only in the caller's external/ignored output directory.
                    folder = output / key;folder.mkdir(exist_ok=True)
                    (folder / 'baseline.l4hy').write_bytes(blob);(folder / 'optimized.l4hy').write_bytes(newer)
                    sf.write(folder / 'reference.wav', ref, 8000, subtype='PCM_16')
                    print(key, item['quality']['ser_db'], '->', joint['after']['ser_db'], flush=True)
        for key, ref, kind, provenance in cases:
            folder = output / key;folder.mkdir(exist_ok=True)
            sf.write(folder / 'reference.wav', ref, 8000, subtype='PCM_16')
            started = time.perf_counter()
            old = next((c for c in previous['cases'] if c['id'] == key), None) if previous else None
            limit = min(65535, len(ref) * 3 // 8, old['bytes'] if old else 65535)
            blob, pcm, generation = encode_segment(ref, decoder, max_bytes=limit,
                                                    kind=kind, lambdas=LAMBDAS)
            (folder / 'baseline.l4hy').write_bytes(blob)
            item = {'id': key, 'kind': kind, 'provenance': provenance, 'samples': len(ref),
                    'reference_pcm_sha256': hashlib.sha256(ref.astype('<i2').tobytes()).hexdigest(),
                    'bytes': len(blob), 'baseline_quality': quality(ref, pcm, kind),
                    'generation': generation, 'baseline_cost': probe(blob, executable), 'beam': []}
            if old:
                item['previous_encoder'] = {'stage': 'df2b28a standalone encoder before stable restarts',
                    'bytes': old['bytes'], 'quality': old['baseline_quality'],
                    'new_size_does_not_grow': len(blob) <= old['bytes']}
            best_blob, best_pcm = blob, pcm
            for width, window in ((1, 20), (4, 20), (8, 20), (16, 20), (4, 40)):
                newer, pp, r = beam_opt(blob, ref, decoder, beam_width=width, window=window,
                                       max_trials=trials, kind=kind)
                cost = probe(newer, executable)
                if cost != item['baseline_cost']:
                    raise AssertionError('Native decode-cost proxy changed')
                r['cost_proxy_unchanged'] = True
                item['beam'].append(r)
                if np.sum((ref.astype(np.float64) - pp) ** 2) < np.sum((ref.astype(np.float64) - best_pcm) ** 2):
                    best_blob, best_pcm = newer, pp
                print(key, 'beam', width, window, r['before']['ser_db'], '->', r['after']['ser_db'], flush=True)
            (folder / 'optimized.l4hy').write_bytes(best_blob)
            sf.write(folder / 'optimized.wav', best_pcm, 8000, subtype='PCM_16')
            item['best_quality'] = quality(ref, best_pcm, kind)
            item['elapsed_seconds'] = time.perf_counter() - started
            results['cases'].append(item)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(results, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return results


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--corpus', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--report', type=Path, required=True)
    ap.add_argument('--private-archive', type=Path)
    ap.add_argument('--trials', type=int, default=1000)
    ap.add_argument('--baseline-report', type=Path)
    a = ap.parse_args()
    run(a.corpus, a.output, a.report, a.private_archive, a.trials, a.baseline_report)
