"""Compare retained FluidR3 PCM with isolated actual AVR percussion."""
from pathlib import Path
import hashlib
import json
import wave
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/'build/natural-hat'
EDGES=np.array([35,120,250,500,1000,2000,4000,6500,9000])


def features(x,sr):
    if x.ndim==1:x=x[:,None]
    n=round(.032*sr);psd=0
    for t in [.005,.020,.035,.050]:
        y=x[round(t*sr):round(t*sr)+n]
        y=(y-y.mean(axis=0))*np.hanning(n)[:,None]
        psd=psd+np.mean(abs(np.fft.rfft(y,axis=0))**2,axis=1)
    hz=np.fft.rfftfreq(n,1/sr)
    bands=np.array([sum(psd[(hz>=a)&(hz<b)]) for a,b in zip(EDGES[:-1],EDGES[1:])])
    return bands/bands.sum()


def main():
    capture=json.loads((ROOT/'build/fluid-grid/drums/capture.json').read_text(encoding='utf-8'))
    report=dict(capture=capture,bandEdgesHz=EDGES.tolist(),
                method='Actual AVR output, held envelope for PSD: four 32-ms Hann windows at 5,20,35,50 ms; normalized band power below 9 kHz. Actual decay in 10-ms RMS windows.',instruments={})
    times=np.arange(.005,.255,.01)
    for midi,kind in [(35,0),(42,1),(38,2)]:
        entry=next(n for n in capture['notes'] if n['midi']==midi)
        file=ROOT/'build/fluid-grid/drums'/entry['file']
        assert hashlib.sha256(file.read_bytes()).hexdigest()==entry['sha256']
        with wave.open(str(file)) as f:
            sr=f.getframerate();x=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2').reshape(-1,2)/32768.
        target=features(x,sr)
        row=dict(referenceBands=target.tolist())
        for name in ['foreground-pwm','natural-hat']:
            held=np.fromfile(RAW/f'{name}-{kind}-held.f32',dtype='<f4')
            decay=np.fromfile(RAW/f'{name}-{kind}-decay.f32',dtype='<f4')
            bands=features(held,37500)
            rms=np.array([np.sqrt(np.mean(decay[round((t-.005)*37500):round((t+.005)*37500)]**2)) for t in times])
            row[name]=dict(bandPower=bands.tolist(),spectralDistance=float(np.linalg.norm(np.sqrt(bands)-np.sqrt(target))),
                           rmsFirst80ms=float(np.sqrt(np.mean(held[:3000]**2))),
                           rmsTimes=times.round(4).tolist(),rms=(rms/max(rms)).round(6).tolist())
        report['instruments'][midi]=row
        print(midi,[(n,round(row[n]['spectralDistance'],4)) for n in ['foreground-pwm','natural-hat']])
    (ROOT/'ATtiny13A/Music/variants/natural-hat/percussion-measurements.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')


if __name__=='__main__':main()
