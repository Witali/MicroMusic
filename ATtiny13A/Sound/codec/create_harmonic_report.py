#!/usr/bin/env python3
"""Make objective comparisons, preview files and spectral-trajectory plot."""
from pathlib import Path
import json
import numpy as np, soundfile as sf
from scipy.signal import stft
from spectral_objective import evaluate,x
import matplotlib.pyplot as plt
P=Path(__file__).resolve().parent
base=P.parent/'MicroMusic-ATtiny13-LPC-v4'
fs=7500
v4=np.fromfile(base/'emu_pwm_u8.raw',dtype=np.uint8).astype(float)-128
v5=np.fromfile(P/'firmware_broadband/emu_pwm_u8.raw',dtype=np.uint8).astype(float)-128
h,sr=sf.read(P/'TinyLPC_harmonic_profiles.wav'); assert sr==fs
orig,sr=sf.read(P/'source_original_7500.wav'); assert sr==fs
orig=orig[:len(v4)]

def metrics(pcm, scale):
 yy=pcm[:len(x)]/scale
 z=evaluate(yy,True)
 jump=np.abs(np.diff(pcm*(128/scale)))
 return dict(stoi=z['stoi'],mel=z['spectral_mel_distance'],loudness=z['loudness_envelope_error'],max_step=int(np.max(jump)),steps_ge_60=int(np.sum(jump>=60)))
res={'v4_AVR':metrics(v4,128),'v5_AVR':metrics(v5,128),'four_profile_host_only':metrics(h,1)}
res['v4_AVR'].update(bytes_flash=1012, bytes_data=435)
res['v5_AVR'].update(bytes_flash=1012, bytes_data=435)
(P/'metrics_harmonic_v5.json').write_text(json.dumps(res,ensure_ascii=False,indent=2))
print(json.dumps(res,ensure_ascii=False,indent=2))
# matched-level preview useful for listening; do not use normalised signal for technical metrics
sf.write(P/'TinyLPC_v5_AVR.wav',np.clip(v5/128,-1,1),fs)
for name,data in [('v4',v4/128),('v5',v5/128),('harmonic_profile',h)]:
    power=np.sqrt(np.mean(data**2)+1e-12)
    target=np.sqrt(np.mean(orig**2)+1e-12)
    scale=min(2.8,target/power,0.96/(np.max(abs(data))+1e-9))
    sf.write(P/f'{name}_levelmatched.wav',data*scale,fs)
pad=np.zeros(int(.25*fs))
rows=[orig, sf.read(P/'v4_levelmatched.wav')[0],sf.read(P/'v5_levelmatched.wav')[0], sf.read(P/'harmonic_profile_levelmatched.wav')[0]]
# WAV slots: orig/v4/orig/v5/orig/synthetic multiharmonic, each with short silence
seq=[rows[i] for i in [0,1,0,2,0,3]]
sf.write(P/'TinyLPC_v5_AB_original_v4_v5_harmonics.wav',np.concatenate([x for pair in zip(seq,[pad]*len(seq)) for x in pair]),fs)
fig,axs=plt.subplots(4,1,figsize=(11,8.8),sharex=True,layout='constrained')
for ax,name,y in zip(axs,['Original excerpt','v4 AVR (four-tap chirp)','v5 AVR (broadband excitation)','4/8/12 harmonic profiles (host only)'],rows):
    f,t,s=stft(y,fs=fs,nperseg=256,noverlap=208)
    a=20*np.log10(abs(s)+1e-4)
    ax.pcolormesh(t,f,a,vmin=-70,vmax=-15,shading='auto',cmap='magma',rasterized=True)
    ax.set_ylim(0,3600)
    ax.set_ylabel('Hz');ax.set_title(name,fontsize=11)
axs[-1].set_xlabel('Seconds')
fig.savefig(P/'spectrogram_v5.png',dpi=140,bbox_inches='tight')
plt.close(fig)
