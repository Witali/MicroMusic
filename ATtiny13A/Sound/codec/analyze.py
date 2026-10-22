from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly,butter,sosfiltfilt
P=Path(__file__).parent
FS=7500; H=256; ORDER=7
fs,foo=None,None
x,sr=sf.read(P/'source_original_7500.wav')
# remove initial and terminal dead air while keeping the original pauses (00:00.160 - 00:03.117)
start=round(.16*FS);stop=round(3.12*FS)
x=x[start:stop].copy()
# Gentle removal of low-frequency rumble; keep the theater recording's natural dynamics.
x=sosfiltfilt(butter(2,75,fs=FS,btype='highpass',output='sos'),x)
x=x/max(abs(x).max(),1e-8)*.9
sf.write(P/'speech_trimmed_7500.wav',x,FS,subtype='PCM_16')
print('trim', len(x)/FS,'samples',len(x),'frames',int(np.ceil(len(x)/H)),'size',int(np.ceil(len(x)/H))*5, 'peak',abs(x).max())

def levinson(seg,order=ORDER,preemph=0.,a=1.006):
 n=len(seg)
 # optional PRECOMP implemented in prepass, not local
 z=(seg-seg.mean())*np.hamming(n)
 r=np.array([z[k:]@z[:n-k] for k in range(order+1)])
 r[0]*=a
 k=np.zeros(order)
 coeff=[1.];error=r[0]
 if error<1e-9:return k,0
 for m in range(1,order+1):
  km=np.clip(-(r[m]+sum(coeff[j]*r[m-j] for j in range(1,m)))/max(error,1e-10),-.97,.97)
  new=coeff+[0]
  for j in range(1,m):new[j]=coeff[j]+km*coeff[m-j]
  new[m]=km;coeff=new;k[m-1]=km;error*=max(.01,1-km*km)
 return k,np.sqrt(max(error/n,0))


def get_pitch(st,x=x,FS=FS,H=H):
 seg=x[max(0,st-128):min(len(x),st+H+160)]
 if len(seg)<H*.8:return 0.,0
 seg=seg-seg.mean();peak=np.max(abs(seg))
 if peak<.008:return 0.,0
 seg=np.sign(seg)*np.maximum(0,abs(seg)-peak*.24)
 vals=[]
 for lag in range(round(FS/440),round(FS/55)):
  a=seg[lag:];b=seg[:-lag]
  vals.append((float(a@b/np.sqrt(a@a*b@b+1e-10)),lag))
 return max(vals)

if __name__=='__main__':
 from scipy.signal import stft
 print('time  rms  rawpitch  corr    K0 K1 K2 K3 K4 K5 K6')
 for t in range(0,len(x),H):
  sl=x[t:min(len(x),t+H)];k,err=levinson(sl);rms=np.sqrt(np.mean(sl*sl));co,per=get_pitch(t)
  print(f'{t/FS:5.2f} {rms:5.3f} {FS/per if per else 0:6.1f} {co:5.3f} '+' '.join(f'{z:4.1f}' for z in k))
