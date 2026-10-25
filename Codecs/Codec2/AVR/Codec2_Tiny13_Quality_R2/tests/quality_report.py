#!/usr/bin/env python3
"""Report objective proxy metrics and make physically realistic AC-coupled previews.
Requires numpy, scipy, soundfile, pystoi. All input WAVs are 8kHz mono.
STOI is indicative, particularly for the synthetic tests; it is not listening/MOS.
"""
from pathlib import Path
import csv, numpy as np, soundfile as sf
from scipy.signal import butter,sosfilt,stft
from pystoi import stoi
ROOT=Path(__file__).resolve().parents[1]
W=ROOT/'audio'
D=[('English','english_input_source.wav','english_codec2_reference.wav','english_R1_pwm_sim.wav','speech.c2zx.resonator_full.wav'),
   ('Russian','russian_input_source.wav','russian_codec2_reference.wav','russian_R1_pwm_sim.wav','codec2_3200_8byte_frames.bin.resonator_full.wav')]
rows=[]
for lang,src,orig,r1,r2 in D:
 clean,fs=sf.read(W/src);assert fs==8000
 original,_=sf.read(W/orig);prev,_=sf.read(W/r1);x,_=sf.read(W/r2)
 # RC-coupled analog approximation; normalization only for listening comparison.
 sos=butter(1,35,btype='highpass',fs=8000,output='sos')
 xhp=sosfilt(sos,x)
 norm=min(2.0,float(np.sqrt(np.mean(original**2)))/max(1e-8,float(np.sqrt(np.mean(xhp**2)))))
 out=np.clip(xhp*norm,-0.9999,0.9999)
 outfile=lang.lower()+'_R2_listening_AC_coupled.wav'
 sf.write(W/outfile,out,8000,subtype='PCM_16')
 for label,xx in [('Input',clean),('Reference Codec2',original),('Tiny13 R1',prev),('Tiny13 R2',x),('R2 AC-coupled listen',out)]:
  m=min(len(clean),len(xx));xo=xx[:m];cl=clean[:m]
  _,_,spec1=stft(cl,8000,nperseg=256,noverlap=128)
  _,_,spec2=stft(xo,8000,nperseg=256,noverlap=128)
  # Only diagnostic; phase and gain differences make this a weak MOS proxy.
  aa=abs(spec1);bb=abs(spec2)
  logmag=float(np.mean(np.abs(20*np.log10(aa+0.0002)-20*np.log10(bb+0.0002))))
  rows.append(dict(language=lang,algorithm=label,stoi_vs_clean=round(float(stoi(cl,xo,8000)),6),
   mean_amplitude=round(float(np.mean(xo)),6),rms=round(float(np.sqrt(np.mean(xo**2))),6),
   logmag_delta_db=round(logmag,3),source_wav=src))
 print(lang,[(r['algorithm'],r['stoi_vs_clean']) for r in rows if r['language']==lang])
with (ROOT/'reports'/'quality_metrics.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
