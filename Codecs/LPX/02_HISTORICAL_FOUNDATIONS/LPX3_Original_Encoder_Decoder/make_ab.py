"""Generate direct-playable A/B WAV comparisons for Android players."""
from pathlib import Path
import numpy as np,soundfile as sf
R=Path(__file__).resolve().parent
for clip in ['vinni','xtuj-ntt','ne-otv']:
 p=R/'samples'/clip; fs=8000
 pieces=[]
 for name in ['original','lpc2_voice_v2','voice_v3_3bit','voice_v3_4bit']:
  arr,sr=sf.read(p/(name+'.wav')); assert sr==fs
  rms=np.sqrt(np.mean(arr*arr))+1e-12
  gain=min(.16/rms, .90/(np.max(np.abs(arr))+1e-12))
  pieces.append(np.asarray(arr*gain,'float32'))
  pieces.append(np.zeros(int(.25*sr),dtype='float32'))
 wav=np.concatenate(pieces)
 dest=p/'AB_original_v2_v3.wav'
 sf.write(dest,wav,fs,subtype='PCM_16')
 print(clip,dest.name,len(wav)/sr,dest.stat().st_size)
