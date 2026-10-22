from pathlib import Path
import numpy as np,soundfile as sf,json
from spectral_objective import evaluate,x
from model_exact import synth_exact
# scorer is implemented without running optimizer
from scipy.signal import butter,sosfilt
def pitch_error(P):
    from scipy.signal import correlate,find_peaks
    from spectral_objective import N,H,FS,x
    target=np.zeros(N,dtype=int);weight=np.zeros(N,float)
    for fi in range(N):
       center=fi*H+H//2
       s=x[max(0,center-285):min(len(x),center+285)]
       if len(s)<300:s=np.pad(s,(0,300-len(s)))
       s=s-s.mean();s=s[1:]-0.88*s[:-1]
       ac=correlate(s,s,'full',method='fft')[len(s)-1:]
       e=np.array([np.sqrt(np.sum(s[p:]**2)*np.sum(s[:-p]**2))+1e-9 for p in range(1,95)])
       ac=ac[1:95]/e;ac[:15]=0
       peaks,_=find_peaks(ac[15:90]);peaks=peaks+15
       ranked=sorted([(float(ac[p]),int(p)) for p in peaks],reverse=True)
       best=ranked[0][0] if ranked else 0
       rms=np.sqrt(np.mean(x[fi*H:min(len(x),(fi+1)*H)]**2))
       if best>.53 and rms>.065:
          c=[p for _,p in ranked if ac[p]>.77*best and ac[p]>.5]
          if c:
             target[fi]=min(c);weight[fi]=(best-.48)*rms
    weight/=weight.sum()
    r=np.zeros(N,float);v=target>0
    r[v]=np.minimum(2.,np.abs(np.log2(np.maximum(1,P[v])/target[v])))
    return float((r*weight).sum())
P=Path(__file__).resolve().parent
old=P
sv3=(np.fromfile(old/'emu_pwm_v3.raw',dtype='u1').astype(float)-128)/128
sv4=(np.fromfile(P/'emu_pwm_u8.raw',dtype='u1').astype(float)-128)/128
zp=np.load(P/'best_parameters.npz');zold=np.load(P/'v3_formant_best.npz')
metrics={}
for label,y,pp,ff in [('v3',sv3,zold['pitch'],(old/'tinylpc_v3.bin').stat().st_size),('v4',sv4,zp['P'],(P/'tinylpc.bin').stat().st_size)]:
   scores=evaluate(y[:len(x)],True)
   metrics[label]={'stoi':float(scores['stoi']),'mel':float(scores['spectral_mel_distance']),'envelope':float(scores['loudness_envelope_error']),'pitch_error':pitch_error(pp),'flash':ff,'speech':435,'samples':len(y)}
   print(label,metrics[label])
   # Avoid extra smoothing in comparator: raw PCM represents mean PWM duty 37.5kHz carrier after RC
   y=y*0.9/max(abs(y).max(),.001)  # same peak only for audio file, player normalizes RMS
   sf.write(P/f'TinyLPC_{label}_AVR_reference.wav',y,7500,subtype='PCM_16')
   # Loudness matched for subjective A/B, dynamic curve unchanged.
print('model',evaluate(synth_exact(zp['K'],zp['P'],zp['E'],len(x))/128.,True))
(P/'metrics.json').write_text(json.dumps(metrics,indent=2,ensure_ascii=False))
