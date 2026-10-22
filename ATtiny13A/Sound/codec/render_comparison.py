#!/usr/bin/env python3
"""Render fair A/B audio and spectrum images from original WAV and decoded AVR HEX."""
from pathlib import Path
import numpy as np,soundfile as sf,matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.signal import stft,resample_poly
from PIL import Image
P=Path(__file__).resolve().parent
old=P
sr=7500
src,_=sf.read(P/'speech_trimmed_7500.wav')
v3=(np.fromfile(old/'emu_pwm_v3.raw',dtype='u1').astype(float)-128)/128
v4=(np.fromfile(P/'emu_pwm_u8.raw',dtype='u1').astype(float)-128)/128
lpc2=np.fromfile(P/'phrase_lpc2.s16le',dtype='<i2')/32768.
lpc2=resample_poly(lpc2,15,16)
N=len(src)
# A/B listening levels: same broadband RMS target when headroom permits.
def levelmatch(a,tar=.12):
 a=np.asarray(a[:N],float)
 rms=np.sqrt(np.mean(a*a));peak=np.max(abs(a))
 gain=min(tar/max(1e-6,rms),.97/max(1e-6,peak))
 return a*gain, gain
m_src,g0=levelmatch(src);m_v3,g3=levelmatch(v3);m_v4,g4=levelmatch(v4)
print('RMS levels',[(name,round(np.sqrt(np.mean(a*a)),4),round(g,2)) for name,a,g in [('Original',m_src,g0),('v3',m_v3,g3),('v4',m_v4,g4)]])
sf.write(P/'MicroMusic_TinyLPC_v4_AVR.wav',m_v4,sr,subtype='PCM_16')
sf.write(P/'MicroMusic_TinyLPC_v3_levelmatched.wav',m_v3,sr,subtype='PCM_16')
silence=np.zeros(round(.45*sr))
# Single WAV for blind-ish consecutive comparison. Show order in README.
sequence=np.concatenate([m_src,silence,m_v3,silence,m_src,silence,m_v4,silence,m_v3,silence,m_v4])
sf.write(P/'MicroMusic_AB_original_v3_v4.wav',sequence,sr,subtype='PCM_16')

signals=[src,v3,v4,lpc2]
names=['Оригинальный голос · обработанный WAV','TinyLPC v3 · результат выполнения AVR','TinyLPC v4 · результат выполнения AVR','LPC2 Improved · большая память (для сравнения)']
fig,axes=plt.subplots(4,1,figsize=(12,9),sharex=True,sharey=True)
for ax,signal,name in zip(axes,signals,names):
 signal,_=levelmatch(signal)
 freqs,ts,sp=stft(signal,fs=sr,nperseg=256,noverlap=208)
 db=20*np.log10(np.maximum(abs(sp),1e-7))
 ax.pcolormesh(ts,freqs,db,shading='auto',cmap='magma',vmin=-70,vmax=-10)
 ax.set_ylim(0,3300);ax.set_ylabel('Гц',fontsize=10);ax.set_title(name,loc='left',fontsize=12,fontweight='bold',pad=7)
 ax.grid(axis='x',alpha=.15)
axes[-1].set_xlabel('Время, с');axes[-1].set_xlim(0,len(src)/sr)
fig.suptitle('MicroMusic — оригинал и декодированные фразы',fontsize=15,fontweight='bold',y=.995)
fig.tight_layout(rect=(0,0,1,.965),h_pad=1.2)
fig.savefig(P/'spectrogram_compare_v4.png',dpi=135)
plt.close(fig)
Image.open(P/'spectrogram_compare_v4.png').convert('RGB').save(P/'spectrogram_compare_v4.webp',quality=84,method=6)
print('Spectrogram and A/B WAV saved', flush=True)
