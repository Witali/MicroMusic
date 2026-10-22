#!/usr/bin/env python3
"""Offline experiment: how many harmonics in the excitation help original-voice resemblance?
The input stream and exact 8-bit lattice are inherited from TinyLPC v4. The bank is
precomputed on the host, NOT embedded in ATtiny13A ROM; this is a feasibility study.
"""
from pathlib import Path
import numpy as np
import soundfile as sf
from numba import njit
from spectral_objective import evaluate, x, FS
from model_exact import synth_exact
ROOT=Path(__file__).parent
D=np.load(ROOT/'best_parameters.npz')
K=D['K'].astype(np.int64);P=D['P'].astype(np.int64);E=D['E'].astype(np.int64)
L=len(P)*256

@njit(cache=True)
def render(K,P,E,banks,length,sel,scale=1.0,blend=.0,smooth=0):
    out=np.zeros(length,dtype=np.int64)
    st=np.zeros(7,dtype=np.int64)
    phase=1;seed=0xa7;prev=0;oldfi=-1
    for t in range(length):
        fi=((t+1)//256)%len(P)
        if fi!=oldfi:
            if E[fi]==0: st[:]=0
            oldfi=fi
        p=int(P[fi]);g=int(E[fi]); e=0
        if p:
            phase=(phase-1)&255
            justreset=(phase==0)
            if justreset: phase=p;offset=0
            else:offset=(p-phase)&255
            # An unchanged pitch countdown can be larger than the NEW period at a frame transition.
            # Offset zero in that case must not spuriously trigger a new glottal pulse.
            valid=justreset or offset!=0
            chirp=5 if offset==0 and valid else 3 if offset==1 else -2 if offset==3 else 0
            v=banks[sel[fi],p,offset]*scale if valid and offset<banks.shape[2] else 0.
            e=int(np.rint(g*(blend*chirp+(1-blend)*v)))
        else:
            seed=(seed>>1)^(0xb8 if seed&1 else 0)
            e=-g if seed&1 else g
        v=e
        for j in range(6,-1,-1):
            delta=(int(K[fi,j])*st[j])>>4
            v=((v-delta+128)&255)-128
            if j<6:
                delta2=(int(K[fi,j])*v)>>4
                st[j+1]=((st[j]+delta2+128)&255)-128
        st[0]=v
        if smooth==1: out[t]=(v>>1)+(prev>>1)
        elif smooth==2:out[t]=((3*v+prev)>>2)
        elif smooth==3:out[t]=((v+3*prev)>>2)
        else:out[t]=v
        prev=v
    return out


def make_bank():
    """Band-limited harmonic families with energy comparable to four-tap excitation."""
    shapes=[];labels=[]
    for n in [2,3,4,6,8,12]:
      for slope in [.0,.6,1.,1.5,2.,3.]:
        bank=np.zeros((255,255),dtype=np.float64)
        for p in range(2,255):
            nmax=min(n, max(1,int(np.floor(p*.44))))
            ns=np.arange(1,nmax+1)
            a=ns**(-slope)
            # Match impulse RMS (=sqrt(5^2+3^2+2^2)/sqrt(p))
            norm=np.sqrt(2*(25+9+4)/p/(a*a).sum())
            offs=np.arange(p)
            b=(np.cos(2*np.pi*offs[:,None]*ns[None,:]/p)@a)*norm
            bank[p,:p]=b
        shapes.append(bank);labels.append(f'{n} partials, 1/n^{slope}')
    return np.array(shapes),labels


def record(y):
    m=evaluate(y[:len(x)]/128,True)
    dif=np.abs(np.diff(y))
    return m['stoi'], m['spectral_mel_distance'],float((dif>=60).sum()),float(np.abs(dif).max())

if __name__=='__main__':
    print('Source length',len(x),'files',len(P),'frames',flush=True)
    v4=synth_exact(K,P,E,L);base=record(v4)
    print('v4',base,flush=True)
    bank,labels=make_bank();print('bank',bank.shape,flush=True)
    sel=np.zeros(len(P),dtype=np.int64)
    results=[]
    for i,label in enumerate(labels):
      sel[:]=i
      for blend in [0.,.35,.7]:
       for scale in [.65,1.,1.4]:
        y=render(K,P,E,bank,L,sel,scale,blend,0)
        r=record(y)
        results.append((r[0],r[1],r[2],r[3],i,label,blend,scale))
    for z in sorted(results,key=lambda a: (a[1]+max(0,0.79-a[0])*3 +a[2]*0.003))[:25]:
        print('candidate',tuple(round(a,4) if isinstance(a,float) else a for a in z),flush=True)
    best=min(results,key=lambda a:(a[1]+max(0,0.79-a[0])*3 +a[2]*0.003))
    print('best',best,flush=True)
    # compare a priori 4, 8, 12 harmonic families (no frame-wise adapted templates)
    rows=[]
    for n in [4,8,12]:
      choices=[v for v in results if v[5].startswith(str(n)+' partials')]
      z=min(choices,key=lambda a:a[1]+max(0,.79-a[0])*3+a[2]*.003)
      sel[:]=z[4]; sig=render(K,P,E,bank,L,sel,z[7],z[6],0)
      rows.append((n,z,sig))
    # optional frame-level spectral pattern selection from small bank with same weights
    from scipy.signal import stft
    positions=np.arange(L)
    sf.write(ROOT/'TinyLPC_v4_baseline.wav',v4.astype(np.float64)/128,FS,subtype='PCM_16')
    for n,z,y in rows:
      sf.write(ROOT/f'harmonics_{n}_test.wav',y.astype(np.float64)/128,FS,subtype='PCM_16')
    # WAV A/B with repeated source for listening
    ref,_=sf.read(ROOT/'source_original_7500.wav')
    ref=ref[:len(v4)]
    signals=[ref,v4/128]+[y/128 for _,_,y in rows]
    pad=np.zeros(FS//4)
    audio=[]
    for s in signals:
      s=s[:len(ref)]
      # normalize to comparable RMS with cap to avoid excessive clipping
      rms=np.sqrt(np.mean(s*s)+1e-12); ref_rms=np.sqrt(np.mean(ref*ref)+1e-12)
      s=s*min(2.,ref_rms/rms)
      audio.extend([s,pad])
    sf.write(ROOT/'harmonic_A_B.wav',np.concatenate(audio),FS)
    lines=['Test: ORIGINAL, TinyLPC v4, harmonic 4, harmonic 8, harmonic 12.',f'Baseline: STOI {base[0]:.3f} spectral_error {base[1]:.3f} clicks>=60 {base[2]:.0f} maxstep {base[3]:.0f}']
    for n,z,y in rows:
      lines.append(f'{n} harmonics: STOI {z[0]:.3f} spectral_error {z[1]:.3f} clicks>=60 {z[2]:.0f} maxstep {z[3]:.0f} slope={z[5]} chirp_mix={z[6]} gain={z[7]}')
    (ROOT/'harmonic_comparison.txt').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines))
