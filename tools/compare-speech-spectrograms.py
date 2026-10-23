"""Plot RMS-matched speech spectrograms on shared scales and report discrepancies."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from spectrogram_objective import SpectrogramObjective, VERSION


def read_candidate(path, samples, sample_rate):
    if path.suffix.lower() == '.raw':
        pcm = np.frombuffer(path.read_bytes(), np.uint8)
        if len(pcm) == 3*samples and np.all(pcm[samples:] == 128):
            pcm = pcm[:samples]
        if len(pcm) != samples:
            raise ValueError('Raw AVR input must be one phrase or one phrase followed by twice its length of midpoint silence')
        return (pcm.astype(float)-128)/128, sample_rate
    return sf.read(path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--candidate', action='append', required=True, help='Label=path.wav')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--listen', action='store_true', help='Export a level-matched original then each candidate, with shared peak scale')
    a = p.parse_args()
    reference, sr = sf.read(a.reference)
    objective = SpectrogramObjective(reference, sr)
    signals = [('Original', objective.filtered)]
    report = dict(version=VERSION, reference_sha256=hashlib.sha256(a.reference.read_bytes()).hexdigest(),
                  samples=len(reference), sample_rate=sr, processing='Identical 70 Hz highpass, global RMS match; no time/frequency warping', candidates={})
    for entry in a.candidate:
        label, filename = entry.split('=', 1)
        path = Path(filename)
        value, rate = read_candidate(path, len(reference), sr)
        if rate != sr:
            p.error('Every sample rate must equal the reference')
        report['candidates'][label] = dict(**objective.evaluate(value),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        signals.append((label, objective.matched(value)))
    a.output.mkdir(parents=True, exist_ok=True)
    if a.listen:
        scale = .85/max(float(np.max(abs(x))) for _, x in signals)
        report['listening_order'] = []
        parts = []
        for index, (label, value) in enumerate(signals):
            filename = f'track-{index}.wav'
            sf.write(a.output/filename, value*scale, sr, subtype='PCM_16')
            report['listening_order'].append(dict(label=label, file=filename))
            parts.extend((value*scale, np.zeros(round(.3*sr))))
        sf.write(a.output/'comparison.wav', np.concatenate(parts), sr, subtype='PCM_16')
    for size, hop in ((512, 64), (1024, 128)):
        fig, axes = plt.subplots(len(signals), 2, figsize=(14, 3*len(signals)),
            gridspec_kw={'width_ratios': [3.6, 1]}, squeeze=False)
        fig.subplots_adjust(left=.065, right=.91, top=.95, bottom=.07, hspace=.36, wspace=.3)
        f, t, target = objective.magnitude(signals[0][1], size, hop)
        maximum = max(float(target.max()), 1e-20)
        for index, (label, x) in enumerate(signals):
            mag = objective.magnitude(x, size, hop)[2]
            db = 20*np.log10(np.maximum(mag/maximum, 1e-6))
            im = axes[index, 0].pcolormesh(t, f, db, shading='auto', cmap='magma', vmin=-60, vmax=0)
            axes[index, 0].set(title=label, ylabel='Frequency, Hz', ylim=(0, 3750), xlim=(0, len(x)/sr))
            mean = np.mean(mag**2, axis=1)
            ref = np.mean(target**2, axis=1)
            axes[index, 1].plot(10*np.log10(np.maximum(ref/maximum**2, 1e-12)), f, color='#777', label='Original')
            axes[index, 1].plot(10*np.log10(np.maximum(mean/maximum**2, 1e-12)), f, label=label, alpha=.8)
            axes[index, 1].set(ylim=(0, 3750), xlim=(-70, 0), xlabel='Mean spectrum, dB')
            axes[index, 1].grid(alpha=.2)
        axes[-1, 0].set_xlabel('Time, seconds')
        colorbar = fig.add_axes((.935, .13, .012, .72))
        fig.colorbar(im, cax=colorbar, label='dB relative to original peak')
        fig.savefig(a.output/f'spectrograms-{size}.png', dpi=125)
        plt.close(fig)
    (a.output/'metrics.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
