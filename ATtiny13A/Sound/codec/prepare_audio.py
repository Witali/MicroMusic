"""Generate optional level-matched A/B comparison WAV from emulator PCM and two references."""
from pathlib import Path
import numpy as np,soundfile as sf
from scipy.signal import resample_poly
P=Path(__file__).parent;FS=7500
s,_=sf.read(P/'original_reference.wav');lpc2=resample_poly(np.fromfile(P/'lpc2_improved_reference.s16le',dtype='<i2')/32768.,15,16)
ref=(np.fromfile(P/'v5_reference_u8.raw',dtype='u1').astype(float)-128)/128
f0,_=sf.read(P/'pitch_glide_AVR.wav');mixed,_=sf.read(P/'mixed_excitation_AVR.wav')

def limit(a):
 a=np.asarray(a,float)
 rms=np.sqrt(np.mean(a*a));pk=np.max(abs(a))
 scale=min(0.12/max(rms,1e-7),.95/max(pk,1e-7))
 return a*scale
silence=np.zeros(int(FS*.3));samples=[]
for name,a in [('original',s),('lpc2',lpc2),('v5',ref),('pitchglide',f0),('mixed',mixed)]:
 a=limit(a);print(name,'peak',round(float(max(abs(a))),3),'rms',round(float(np.std(a)),3))
 samples.extend([a,silence])
sf.write(P/'MicroMusic_AB_LPC2_Lite.wav',np.concatenate(samples),FS,subtype='PCM_16')
