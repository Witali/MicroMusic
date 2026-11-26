"""Prepare public 8 kHz PCM using the canonical16/15 Kaiser5 polyphase filter.

Stdlib reproduction of the mathematical filter used by SciPy resample_poly:
321-tap, cutoff1/16 of Nyquist, Kaiser beta5, DC normalization, zero padding.
Source: scipy.signal.resample_poly / firwin; no library code is copied.
https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.resample_poly.html
The scalar implementation is cross-checked against SciPy when --scipy is used.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import struct
import wave

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]

def i0(x):
    term=total=1.0
    for k in range(1,100):
        term*=x*x/(4*k*k)
        total+=term
        if term<total*1e-17:
            return total
    raise ArithmeticError('I0 convergence')

def resample16_15(pcm):
    taps=[]
    for m in range(-160,161):
        sinc=1/16 if not m else math.sin(math.pi*m/16)/(math.pi*m)
        taps.append(sinc*i0(5*math.sqrt(max(0,1-(m/160)**2)))/i0(5))
    norm=sum(taps)
    taps=[v/norm*16 for v in taps]
    result=[]
    for j in range((len(pcm)*16+14)//15):
        # SciPy prepends5 filter zeros and removes11 decimated outputs.
        at=(j+11)*15-5
        first=max(0,(at-320+15)//16)
        last=min(len(pcm)-1,at//16)
        value=sum(pcm[i]*taps[at-i*16] for i in range(first,last+1))
        result.append(max(-32768,min(32767,round(value))))
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scipy',action='store_true')
    args=parser.parse_args()
    output=REPO/'build/lbg1-common'
    output.mkdir(parents=True,exist_ok=True)
    rows=[]
    for clip in ('chego','otvechaesh','vinni','bread'):
        source=REPO/('web-player/audio/lpx-bread/original.wav' if clip=='bread' else f'web-player/audio/originals/{clip}.wav')
        with wave.open(str(source),'rb') as f:
            assert f.getnchannels()==1 and f.getsampwidth()==2
            rate=f.getframerate()
            data=f.readframes(f.getnframes())
        samples=list(struct.unpack('<'+'h'*(len(data)//2),data))
        if clip!='bread':
            assert rate==7500
            original=samples
            samples=resample16_15(samples)
            if args.scipy:
                import numpy as np
                from scipy.signal import resample_poly
                expected=np.clip(np.rint(resample_poly(np.asarray(original,dtype=float),16,15)),-32768,32767).astype(np.int16)
                assert samples==expected.tolist(),'Scalar/SciPy PCM mismatch'
        else:
            assert rate==8000
        blob=struct.pack('<'+'h'*len(samples),*samples)
        (output/(clip+'.source.pcm')).write_bytes(blob)
        with wave.open(str(output/(clip+'.source.wav')),'wb') as f:
            f.setparams((1,2,8000,len(samples),'NONE','not compressed'));f.writeframes(blob)
        rows.append(dict(clip=clip,source=source.relative_to(REPO).as_posix(),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                         source_rate=rate,rate=8000,samples=len(samples),pcm_sha256=hashlib.sha256(blob).hexdigest(),scipy_cross_checked=args.scipy))
    report=dict(method='same canonical16/15 Kaiser5 FIR, float64, round-to-even PCM16; no fitted gain/delay',sources=rows)
    (output/'sources.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    main()
