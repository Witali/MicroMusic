#!/usr/bin/env python3
"""Make the 8 kHz PCM source used by LPC1/LPC2 browser reference encoder."""
from pathlib import Path
from fractions import Fraction
import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly, butter, sosfilt
P=Path(__file__).resolve().parent
fs,raw=wavfile.read(P/'tts_source.wav')
if raw.ndim>1: raw=np.mean(raw,axis=1)
if np.issubdtype(raw.dtype,np.integer):
    x=raw.astype(np.float64)/max(1,np.iinfo(raw.dtype).max)
else:
    x=raw.astype(np.float64)
f=Fraction(8000,fs)
x=resample_poly(x,f.numerator,f.denominator)
x=sosfilt(butter(1,90,fs=8000,btype='highpass',output='sos'),x)
x=x/max(1e-12,np.max(abs(x)))*.89
np.clip(np.round(x*32767),-32768,32767).astype('<i2').tofile(P/'input_8k.s16le')
print(f'{len(x)} samples at 8000 Hz written to input_8k.s16le')
