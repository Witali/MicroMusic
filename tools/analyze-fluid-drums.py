"""Compare FluidR3 percussion and actual AVR candidate output below 9 kHz."""
from pathlib import Path
import json
import hashlib
import wave
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'build/fluid-grid/drums'
AVR=ROOT/'build/fluid-grid/avr-drums'
OUT=ROOT/'ATtiny13A/Music/reference/fluidr3'
EDGES=np.array([35,120,250,500,1000,2000,4000,6500,9000])


def features(x,sr):
    if x.ndim==1:x=x[:,None]
    n=round(.032*sr);psd=0
    for age in [.005,.020,.035,.050]:
        y=x[round(age*sr):round(age*sr)+n]
        y=(y-y.mean(axis=0))*np.hanning(n)[:,None]
        psd=psd+np.mean(abs(np.fft.rfft(y,axis=0))**2,axis=1)
    hz=np.fft.rfftfreq(n,1/sr)
    bands=np.array([sum(psd[(hz>=a)&(hz<b)]) for a,b in zip(EDGES[:-1],EDGES[1:])])
    bands=bands/bands.sum()
    return bands,hz,psd


capture=json.loads((FOLDER/'capture.json').read_text(encoding='utf-8'))
notes={}
for entry in capture['notes']:
    raw=(FOLDER/entry['file']).read_bytes();assert hashlib.sha256(raw).hexdigest()==entry['sha256']
    with wave.open(str(FOLDER/entry['file'])) as f:
        sr=f.getframerate();x=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2').reshape(-1,2)/32768.
    bands,hz,psd=features(x,sr)
    times=np.arange(.005,.605,.01)
    rms=np.array([np.sqrt(np.mean(x[round(max(0,t-.005)*sr):round((t+.005)*sr)]**2)) for t in times])
    notes[entry['midi']]=dict(bandPower=bands.tolist(),rms=(rms/max(rms)).round(6).tolist(),times=times.round(4).tolist(),
        lowPeakHz=float(hz[(hz>=35)&(hz<=200)][np.argmax(psd[(hz>=35)&(hz<=200)])]))
report=dict(capture=capture,bandEdgesHz=EDGES.tolist(),method='Four 32-ms Hann PSDs at 5,20,35,50 ms; stereo power; normalized bands below 9 kHz. RMS 10-ms windows.',references=notes)
def distance(a,b):return float(np.linalg.norm(np.sqrt(a)-np.sqrt(b)))
candidates=[]
for p in sorted(AVR.glob('*-1.f32')):
    name=p.name[:-6]
    if name=='actual':continue
    if not (AVR/f'{name}-2.f32').exists():continue
    errors=[]
    for kind,midi in [(1,42),(2,38)]:
        a,_,_=features(np.fromfile(AVR/f'{name}-{kind}.f32',dtype='<f4'),37500)
        errors.append(distance(a,np.array(notes[midi]['bandPower'])))
    candidates.append(dict(name=name,hihatError=errors[0],snareError=errors[1],combinedError=float(np.mean(errors))))
candidates.sort(key=lambda r:r['combinedError'])
report['noiseCandidates']=candidates
kick=[]
for name in ['original','kick-1','kick-2','kick-3']:
    a,hz,psd=features(np.fromfile(AVR/f'{name}-0.f32',dtype='<f4'),37500)
    kick.append(dict(name=name,error=distance(a,np.array(notes[35]['bandPower'])),
        lowPeakHz=float(hz[(hz>=35)&(hz<=400)][np.argmax(psd[(hz>=35)&(hz<=400)])])))
report['kickCandidates']=sorted(kick,key=lambda r:r['error'])
(OUT/'percussion-measurements.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
print('Fluid kick low peak:',notes[35]['lowPeakHz'])
print('Kick candidates:',json.dumps(report['kickCandidates']))
print('Best noise:',json.dumps(candidates[:5]))
print('Original noise:',next(r for r in candidates if r['name']=='original'))
