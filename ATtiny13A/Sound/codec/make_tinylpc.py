"""TinyLPC v2 (7 reflection coefficients + four-tap glottal excitation).

Raw LPC (no preemphasis: tiny decoder has no deemphasis), H=256 at 7500 Hz.
Encoding: 5 bytes per 256-sample frame including 7 4-bit reflection coefficients,
pitch, 4-bit gain. Last high nibble was unused in v1; v2 encodes k6 there.
"""
from pathlib import Path
from fractions import Fraction
import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly
P=Path(__file__).resolve().parent
FS=7500
H=256
ORDER=7
s,pcm=wavfile.read(P/'tts_source.wav')
if pcm.ndim>1:pcm=pcm.mean(axis=1)
x=resample_poly(pcm.astype(np.float64)/np.iinfo(pcm.dtype).max,50,147)
x=x*.9/max(np.max(abs(x)),1e-10)

def levinson(seg):
 N=len(seg);z=(seg-seg.mean())*np.hamming(N)
 r=np.array([z[k:]@z[:N-k] for k in range(ORDER+1)])
 r[0]*=1.004
 k=np.zeros(ORDER);a=[1.];error=r[0]
 if error<1e-9:return k
 for m in range(1,ORDER+1):
  km=np.clip(-(r[m]+sum(a[j]*r[m-j] for j in range(1,m)))/max(error,1e-10),-.96,.96)
  new=a+[0]
  for j in range(1,m):new[j]=a[j]+km*a[m-j]
  new[m]=km;a=new;k[m-1]=km;error*=max(0.01,1-km*km)
 return np.clip(np.rint(k*8),-7,7).astype(int)

def get_pitch(st):
 # Autocorrelation of peak-clipped centered window
 seg=x[max(0,st-128):min(len(x),st+H+160)]
 if len(seg)<250:return 0.,0
 seg=seg-seg.mean();peak=np.max(np.abs(seg))
 if peak<.005:return 0.,0
 seg=np.sign(seg)*np.maximum(0,np.abs(seg)-peak*.26)
 vals=[]
 for lag in range(round(FS/260),round(FS/65)):
  a=seg[lag:];b=seg[:-lag]
  vals.append((float(a@b/np.sqrt(a@a*b@b+1e-10)),lag))
 return max(vals)

frames=[]
for t in range(0,len(x),H):
 seg=np.zeros(H);s0=x[t:t+H];seg[:len(s0)]=s0
 k=levinson(seg)
 rms=np.sqrt(np.mean(s0*s0))
 corr,period=get_pitch(t)
 pitch=period if corr>.65 and rms>.006 else 0
 # Proportional gain separately tuned for unvoiced vs voiced excitation;
 # 4-tap 5,3,0,-2 glottal chirp is much stronger than v1's 2-gain impulse.
 energy=int(np.clip(np.rint(rms*(100 if pitch else 80)),0,15))
 if rms<.003:energy=0;pitch=0
 frames.append((pitch,energy,*k,corr))

out=bytearray()
for pitch,amp,k0,k1,k2,k3,k4,k5,k6,corr in frames:
 k0,k1,k2,k3,k4,k5,k6=map(int,(k0,k1,k2,k3,k4,k5,k6))
 out.extend([pitch,(amp&15)|((k0+8)<<4),((k2+8)<<4)|(k1+8),((k4+8)<<4)|(k3+8),((k6+8)<<4)|(k5+8)])
(P/'voice_tinylpc.bin').write_bytes(out)
print(f'frames={len(frames)}, speech_bytes={len(out)}, duration={len(frames)*H/FS:.3f}s, voiced_frames={sum(e[0]>0 for e in frames)}')
