#!/usr/bin/env python3
"""Repeat A3 on the retained previous experiment's external media and hashes.

The previous report supplies reference/baseline PCM hashes. Input media are
read-only. Only numeric reports should be committed; encoded/WAV outputs
belong in an ignored build directory. No network access is performed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import soundfile as sf
from batch_decoder import BatchSession
from global_rate_pcm16 import optimize
from optimize_q0 import cost_probe
from tune_pcm16 import read_wav16


def run(previous_report, media, output, report_path, max_states=1024, max_candidates=64, rounds=2):
    previous_report, media, output, report_path = map(Path, (previous_report, media, output, report_path))
    previous = json.loads(previous_report.read_text(encoding='utf-8'))
    cases = [(c['id'], c['kind'], c['best_quality']['pcm16_sha256'], c['reference_pcm_sha256'])
             for c in previous['cases']]
    for item in previous.get('training_baselines', []):
        if (media / item['id'] / 'optimized.l4hy').exists():
            cases.append((item['id'], 'speech', item['joint']['after']['pcm16_sha256'], None))
    result = {'previous_report_sha256': hashlib.sha256(previous_report.read_bytes()).hexdigest(),
              'limits': {'states': max_states, 'candidates': max_candidates, 'rounds': rounds,
                         'max_cost_growth': 0., 'size_growth': 0., 'stoi_drop': 0.}, 'cases': []}
    executable = cost_probe()
    with BatchSession('batch') as decoder:
        for key, kind, baseline_hash, reference_hash in cases:
            folder = media / key
            ref = read_wav16(folder / 'reference.wav')
            if reference_hash and hashlib.sha256(ref.astype('<i2').tobytes()).hexdigest() != reference_hash:
                raise ValueError('Reference PCM hash mismatch: ' + key)
            blob = (folder / 'optimized.l4hy').read_bytes()
            first = decoder.decode_one_s16(blob, len(ref))
            if first is None or hashlib.sha256(first.astype('<i2').tobytes()).hexdigest() != baseline_hash:
                raise ValueError('Baseline PCM hash mismatch: ' + key)
            new, pcm, report = optimize(blob, ref, decoder, rounds=rounds, max_states=max_states,
                max_candidates=max_candidates, kind=kind, probe_executable=executable)
            report.update(id=key, kind=kind, samples=len(ref),
                          reference_pcm_sha256=hashlib.sha256(ref.astype('<i2').tobytes()).hexdigest())
            result['cases'].append(report)
            target = output / key;target.mkdir(parents=True, exist_ok=True)
            (target / 'global.l4hy').write_bytes(new)
            sf.write(target / 'global.wav', pcm, 8000, subtype='PCM_16')
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(key, len(blob), '->', len(new), 'SER', report['before']['ser_db'], '->', report['after']['ser_db'],
                  'STOI', report['before']['stoi'], '->', report['after']['stoi'],
                  'seconds', round(report['elapsed_seconds'], 2), flush=True)
    return result


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('previous_report', type=Path);ap.add_argument('media_directory', type=Path)
    ap.add_argument('output_directory', type=Path);ap.add_argument('report', type=Path)
    ap.add_argument('--max-states', type=int, default=1024)
    ap.add_argument('--max-candidates', type=int, default=64)
    ap.add_argument('--rounds', type=int, default=2)
    a = ap.parse_args()
    run(a.previous_report, a.media_directory, a.output_directory, a.report,
        a.max_states, a.max_candidates, a.rounds)
