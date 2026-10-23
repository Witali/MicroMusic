#!/usr/bin/env python3
"""Audit retained HQ4/HQ4-T against an external WAV; write local matched A/B audio."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
import scipy
import soundfile as sf
from scipy.signal import butter, sosfilt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ATtiny13A/Sound/codec'))
from hq4_core import unpack_stream
from model import decode as old_decode
from hq4_timbre import decode, metrics, normalized_spectral_error


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    refs = json.loads((ROOT / 'ATtiny13A/Sound/audio-references.json').read_text(encoding='utf-8'))['clips']
    ref_hash = hashlib.sha256(a.reference.read_bytes()).hexdigest()
    if ref_hash != refs[0]['sha256']:
        raise ValueError('Unexpected reference hash')
    reference, sr = sf.read(a.reference)
    baseline = unpack_stream((ROOT / 'ATtiny13A/Sound/codec/release/chego/speech.hq').read_bytes())
    candidate = unpack_stream((ROOT / 'ATtiny13A/Sound/codec/timbre/chego/speech.hq').read_bytes())
    old = old_decode(*baseline)
    new = decode(*candidate)
    hp = butter(2, 70, fs=sr, btype='highpass', output='sos')
    balanced_ref = sosfilt(hp, reference)
    report = {'referenceSha256': ref_hash, 'numpy': np.__version__, 'scipy': scipy.__version__,
              'sampleHz': sr, 'samples': len(reference), 'metrics': {}}
    listening = [sosfilt(hp, x) for x in [reference, (old.astype(float) - 128) / 128,
                                                   (new.astype(float) - 128) / 128]]
    for name, pcm in [('hq4', old), ('hq4-t', new)]:
        filtered = sosfilt(hp, (pcm.astype(float) - 128) / 128)
        # Reuse the documented spectral metric with floating PCM: conversion is
        # algebraic only, without requantization to unsigned bytes.
        report['metrics'][name] = {**metrics(reference, pcm, sr),
            'hp70_spectral_error': normalized_spectral_error(balanced_ref, filtered * 128 + 128, sr),
            'rms': float(np.sqrt(np.mean(((pcm.astype(float) - 128) / 128) ** 2)))}
    report['spectralErrorReductionPercent'] = 100 * (1 - report['metrics']['hq4-t']['spectral_error'] /
                                                        report['metrics']['hq4']['spectral_error'])
    report['hp70SpectralErrorReductionPercent'] = 100 * (1 - report['metrics']['hq4-t']['hp70_spectral_error'] /
                                                            report['metrics']['hq4']['hp70_spectral_error'])
    # Reference, HQ4, reference, HQ4-T. Identical 70 Hz highpass and RMS, with one
    # common peak-safe scale so that loudness alone does not decide the comparison.
    listening = [x / (np.sqrt(np.mean(x*x)) + 1e-10) for x in listening]
    scale = .85 / max(float(np.max(abs(x))) for x in listening)
    parts = []
    for i in (0, 1, 0, 2):
        parts += [listening[i] * scale, np.zeros(round(sr * .3))]
    a.output.mkdir(parents=True, exist_ok=True)
    sf.write(a.output / 'reference-hq4-reference-hq4t.wav', np.concatenate(parts), sr, subtype='PCM_16')
    (a.output / 'quality.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
