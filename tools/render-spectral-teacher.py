#!/usr/bin/env python3
"""Plot matched-level original, T1 baseline and complete PC period teacher."""
import argparse
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import soundfile as sf
from scipy.signal import stft

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
from auto_encoder import SpectralObjective


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--teacher',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    clips = [sf.read(path,dtype='float64') for path in (a.reference,a.baseline,a.teacher)]
    reference,sr = clips[0]
    if sr != 7500 or any(rate != sr or audio.shape != reference.shape for audio,rate in clips):
        p.error('All clips must preserve the mono 7500 Hz reference shape')
    objective = SpectralObjective(reference,sr)
    from scipy.signal import sosfilt
    matched = [sosfilt(objective.hp,audio) for audio,rate in clips]
    matched = [audio*objective.rms/(np.sqrt(np.mean(audio**2))+1e-20) for audio in matched]
    spectra = [stft(audio,fs=sr,nperseg=512,noverlap=448) for audio in matched]
    maximum = max(float(abs(z).max()) for f,t,z in spectra)
    fig,axes = plt.subplots(3,1,figsize=(13,9),sharex=True,sharey=True,layout='constrained')
    for ax,(f,t,z),title in zip(axes,spectra,('Original','Previous T1 firmware','Complete period/noise teacher (PC; decoder bytes excluded)')):
        decibels = 20*np.log10(np.maximum(abs(z),maximum*1e-4)/maximum)
        shown = ax.pcolormesh(t,f,decibels,cmap='magma',shading='auto',vmin=-70,vmax=0)
        ax.set(title=title,ylabel='Frequency (Hz)',ylim=(0,3750))
    axes[-1].set_xlabel('Time (seconds)')
    fig.colorbar(shown,ax=axes,label='Magnitude (dB; shared level and scale)',shrink=.85)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(a.output,dpi=150)
    plt.close(fig)


if __name__ == '__main__':
    main()
