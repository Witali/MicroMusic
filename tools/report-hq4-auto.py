#!/usr/bin/env python3
"""Compare a feedback-encoder candidate with HQ4 and HQ4-T on one external WAV."""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import sosfilt, stft

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ATtiny13A/Sound/codec'))
from auto_encoder import SpectralObjective
from hq4_core import unpack_stream
from hq4_timbre import decode
from model import decode as old_decode
from pystoi import stoi


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--plot', action='store_true', help='Requires matplotlib')
    a = p.parse_args()
    reference, sr = sf.read(a.reference)
    objective = SpectralObjective(reference, sr)
    streams = {
        'HQ4': ROOT / 'ATtiny13A/Sound/codec/release/chego/speech.hq',
        'HQ4-T': ROOT / 'ATtiny13A/Sound/codec/timbre/chego/speech.hq',
        'Auto': a.candidate,
    }
    clips = {'Reference': reference}
    report = dict(reference_sha256=digest(a.reference.read_bytes()), samples=len(reference),
                  sample_rate=sr, streams={}, metrics={})
    for label, path in streams.items():
        f, d = unpack_stream(path.read_bytes())
        if int(np.sum(d)) != len(reference):
            raise ValueError('Candidate and reference duration differ')
        pcm = old_decode(f, d) if label == 'HQ4' else decode(f, d)
        x = (pcm.astype(float) - 128) / 128
        clips[label] = x
        report['streams'][label] = digest(path.read_bytes())
        report['metrics'][label] = dict(**objective.spectrum(x), stoi=float(stoi(reference, x, sr)),
                                       flash_bytes=(406 if label == 'HQ4' else 422) + len(path.read_bytes()) + 1)
    prev, new = report['metrics']['HQ4-T'], report['metrics']['Auto']
    report['log_error_reduction_vs_hq4t_percent'] = 100 * (1 - new['log_spectral_error'] / prev['log_spectral_error'])
    report['objective_reduction_vs_hq4t_percent'] = 100 * (1 - new['loss'] / prev['loss'])
    a.output.mkdir(parents=True, exist_ok=True)
    (a.output / 'quality.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    balanced = {}
    for label, x in clips.items():
        y = sosfilt(objective.hp, x)
        balanced[label] = y * objective.rms / (np.sqrt(np.mean(y * y)) + 1e-10)
    scale = .85 / max(float(np.max(abs(x))) for x in balanced.values())
    parts = []
    for label in ('Reference', 'HQ4-T', 'Reference', 'Auto'):
        parts += [balanced[label] * scale, np.zeros(round(sr * .3))]
    sf.write(a.output / 'reference-hq4t-reference-auto.wav', np.concatenate(parts), sr, subtype='PCM_16')
    if a.plot:
        os.environ.setdefault('MPLCONFIGDIR', str(ROOT / 'build/matplotlib-config'))
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(3, 1, figsize=(11, 8.3), sharex=True, sharey=True, layout='constrained')
        titles = {
            'Reference': 'Оригинал',
            'HQ4-T': f"HQ4-T до автоподбора · ошибка {prev['log_spectral_error']:.4f} · STOI {prev['stoi']:.4f}",
            'Auto': f"После автоподбора · ошибка {new['log_spectral_error']:.4f} · STOI {new['stoi']:.4f}",
        }
        reference_peak = max(abs(stft(balanced['Reference'], fs=sr, nperseg=256, noverlap=192)[2]).ravel())
        for ax, label in zip(axes, ('Reference', 'HQ4-T', 'Auto')):
            frequencies, times, spectrum = stft(balanced[label], fs=sr, nperseg=256, noverlap=192)
            db = 20 * np.log10(np.maximum(abs(spectrum) / max(reference_peak, 1e-10), 1e-4))
            artist = ax.pcolormesh(times, frequencies, db, shading='auto', cmap='magma', vmin=-65, vmax=0)
            ax.set_title(titles[label], loc='left', fontsize=11)
            ax.set_ylabel('Частота, Гц'); ax.set_ylim(0, sr / 2)
            ax.set_xlim(0, len(reference) / sr)
        axes[-1].set_xlabel('Время, с')
        fig.colorbar(artist, ax=axes, label='дБ относительно общего эталонного максимума', shrink=.85)
        fig.suptitle('Автоподбор HQ4-T: одинаковые фильтр 70 Гц, RMS и цветовая шкала\n'
                     'Окно 256 отсчётов, шаг 64; без подгонки времени или частот', fontsize=12)
        fig.savefig(a.output / 'spectrograms.png', dpi=150)
        plt.close(fig)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
