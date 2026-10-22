from pathlib import Path
import numpy as np,soundfile as sf
from scipy.signal import resample_poly
import math
R=Path(__file__).resolve().parent
SR=7500

def read(fp):
 x,sr=sf.read(fp,dtype='float32',always_2d=True);x=x.mean(axis=1)
 if sr!=7500:g=math.gcd(sr,7500);x=resample_poly(x,7500//g,sr//g)
 rms=np.sqrt(np.mean(x*x));pk=max(1e-8,np.max(abs(x)))
 if rms>1e-8:x*=min(.2/rms,.85/pk)
 return x
pause=np.zeros(SR//4,dtype=np.float32)
for name in ('xtuj-ntt','ne-otv','vinni'):
 p=R/name
 arr=[read(p/'original.wav'),pause,read(p/'lpc2_voice_v2.wav'),pause,read(p/'original.wav'),pause,read(p/'attiny13.wav')]
 sf.write(p/'AB_compare.wav',np.concatenate(arr),SR,subtype='PCM_16')
 print(name,len(np.concatenate(arr))/SR)
