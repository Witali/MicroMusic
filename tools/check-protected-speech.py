"""Audit the three selected public speech controls and their retained PCM hashes.

This re-runs the numerical decoders, not the AVR emulators. The retained build
reports provide their previous three-engine qualification and full image sizes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from pystoi import stoi
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from fixed_period import decode_fixed
from hq4_core import unpack_stream
from hq4_speech_search import deterministic_estoi
from model import decode
from spectrogram_objective import SpectrogramObjective
from speech_regression import guard_recordings


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--baseline', type=Path, help='Also require per-metric and exact-PCM agreement with this frozen report')
    a = p.parse_args()
    catalog = json.loads((ROOT/'web-player/hq4-firmware.json').read_text(encoding='utf-8'))
    entries = {entry['audioReferenceId']: entry for entry in catalog['entries']}
    rows = {}
    for name in ('chego', 'otvechaesh', 'vinni'):
        entry = entries[name]
        path = ROOT/'web-player/audio/originals'/(name+'.wav')
        if sha(path) != entry['originalAudioSha256']:
            raise ValueError('Changed protected original: '+name)
        reference, sr = sf.read(path)
        if sr != 7500 or len(reference) != entry['phraseSamples']:
            raise ValueError('Changed protected sample rate/length: '+name)
        if entry['codec'] == 'tiny-period':
            source = ROOT/'ATtiny13A/Sound/research/tiny-speech'/name/'model.json'
            pcm = decode_fixed(json.loads(source.read_text(encoding='utf-8')))
        elif entry['codec'] == 'hq4':
            source = CODEC/'release'/name/'speech.hq'
            frames, durations = unpack_stream(source.read_bytes())
            pcm = decode(frames, durations, 0)
        else:
            raise ValueError('Unexpected protected decoder family')
        if len(pcm) != len(reference):
            raise ValueError('Decoded phrase length changed: '+name)
        complete = np.r_[pcm, np.full(2*len(pcm), 128, dtype=np.uint8)]
        build = json.loads((ROOT/'web-player'/entry['verification']).resolve().read_text(encoding='utf-8'))
        complete_sha = hashlib.sha256(complete.tobytes()).hexdigest()
        if complete_sha != build['expectedPcmSha256']:
            raise ValueError('Protected PCM differs from retained AVR build: '+name)
        audio = (pcm.astype(float)-128)/128
        metrics = dict(stoi=float(stoi(reference, audio, sr)),
            estoi=deterministic_estoi(reference, audio, sr), **SpectrogramObjective(reference).evaluate(audio))
        rows[name] = dict(reference_sha256=sha(path), source=source.relative_to(ROOT).as_posix(),
            source_sha256=sha(source), phrase_pcm_sha256=hashlib.sha256(pcm.tobytes()).hexdigest(),
            phrase_plus_silence_pcm_sha256=complete_sha, samples=len(pcm),
            codec=entry['codec'], metrics=metrics, flash_bytes=entry['flashBytes'],
            eeprom_bytes=entry['eepromBytes'], retained_avr_pcm_matches=True)
    report = dict(schema='protected-speech-audit-v1', recordings=rows, passed=True,
        qualification='Numerical re-decode equals retained three-engine phrase-plus-silence PCM hashes; no new AVR or physical run.',
        source_sha256_normalized_lf={path.relative_to(ROOT).as_posix():
            hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
            for path in (Path(__file__), CODEC/'fixed_period.py', CODEC/'model.py', CODEC/'hq4_core.py',
                         CODEC/'hq4_speech_search.py', CODEC/'dc_blocker.py',
                         CODEC/'spectrogram_objective.py', CODEC/'speech_regression.py')})
    if a.baseline:
        old = json.loads(a.baseline.read_text(encoding='utf-8'))['recordings']
        report['metrics_regression'] = guard_recordings(
            {name: row['metrics'] for name, row in old.items()},
            {name: row['metrics'] for name, row in rows.items()}, tuple(rows))
        report['unchanged_pcm'] = {name: rows[name]['phrase_pcm_sha256'] == old[name]['phrase_pcm_sha256']
                                  and rows[name]['reference_sha256'] == old[name]['reference_sha256'] for name in rows}
        report['passed'] = report['metrics_regression']['candidate_passed'] and all(report['unchanged_pcm'].values())
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps(dict(passed=report['passed'], controls={name: row['metrics'] for name, row in rows.items()})))
    raise SystemExit(not report['passed'])


if __name__ == '__main__':
    main()
