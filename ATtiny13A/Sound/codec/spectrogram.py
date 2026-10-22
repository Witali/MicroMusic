import numpy as np,soundfile as sf,matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.signal import stft,resample_poly
from pathlib import Path
P=Path(__file__).resolve().parent
src,sr=sf.read(P/'speech_trimmed_7500.wav')
a=(np.fromfile(P/'emu_pwm_u8.raw',dtype='uint8').astype(float)-128)/128
b=resample_poly(np.fromfile(P/'phrase_lpc2.s16le',dtype='<i2')/32768,15,16)
seq=[src,a,b];names=['Оригинал · WAV','TinyLPC v3 · AVR HEX','LPC2 · декодер JavaScript']
fig,axs=plt.subplots(3,1,figsize=(12,7.5),sharex=True,sharey=True,layout='constrained')
for ax,signal,title in zip(axs,seq,names):
 f,t,Z=stft(signal,7500,nperseg=256,noverlap=208)
 sp=20*np.log10(np.maximum(abs(Z),1e-7));sp=sp-np.max(sp)
 ax.pcolormesh(t,f,sp,cmap='magma',shading='auto',vmin=-65,vmax=0)
 ax.set_ylim(0,3500);ax.set_ylabel('Гц');ax.set_title(title,loc='left',fontsize=12)
 ax.grid(axis='x',alpha=.15)
axs[-1].set_xlabel('Время, секунды');axs[-1].set_xlim(0,3.0)
fig.suptitle('MicroMusic • спектр оригинальной речи и LPC-версий',fontweight='bold')
fig.savefig(P/'spectrogram_compare_v3.png',dpi=135)
