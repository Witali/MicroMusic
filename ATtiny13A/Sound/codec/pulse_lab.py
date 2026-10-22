"""Closed-loop search over bit-exact AVR-compatible excitation constants.
The 4 controls each change a single AVR opcode and DO NOT cost Flash bytes.
"""
from pathlib import Path
import numpy as np, soundfile as sf, itertools, argparse, json
from numba import njit
from quality import Compare
BASE=Path(__file__).parent
@njit
def s8(v): return ((v+128)&255)-128
@njit
def mul_q4(x,k):
    a=s8(x)
    if k<0:a=s8(-a)
    return ((a*abs(k))>>4)&255
@njit
def decode_pulse(frames,durations,first,second,third,fourth):
    n=int(np.sum(durations));out=np.empty(n,np.uint8)
    state=np.zeros(8,np.int32);k=np.zeros(8,np.int32)
    seed=0xa7;period=0;gain=0;phase=1;mode=0
    fi=0;next_t=int(durations[0])-1
    for t in range(n):
        if t==0 or t==next_t:
            if t!=0:
                fi+=1
                if fi>=len(frames):fi=0
                next_t+=int(durations[fi])
            period=int(frames[fi,0]);gain=int(frames[fi,1])&15
            mode=(int(frames[fi,1])>>4)&3
            phase=period
            for j in range(4):
                data=int(frames[fi,2+j]);k[j*2]=(data&15)-8;k[j*2+1]=(data>>4)-8
        ex=0
        if period:
            phase=(phase-1)&255
            if phase==0:
                phase=period;ex=(first*gain)&255
            else:
                lag=period-phase
                if lag==1:ex=(gain*(second-(mode&1)))&255
                elif lag==2:ex=(gain*(third-(mode>>1)))&255
                elif lag==3:ex=(fourth*gain)&255
        else:
            low=seed&1;seed=seed>>1
            if low:seed=seed^0xb8
            ex=((-gain if (seed&1) else gain))&255
        for j in range(7,-1,-1):
            old=state[j];coef=k[j];ex=(ex-mul_q4(old,coef))&255
            if j<7:state[j+1]=(old+mul_q4(ex,coef))&255
        state[0]=ex;out[t]=(ex+128)&255
    return out

def process(names,write=True):
   report={}
   for name in names:
    ref,sr=sf.read(BASE/'references'/name/'original.wav');cp=Compare(ref)
    x=np.load(BASE/'samples'/name/'trained.npz');f=x['frames'];d=x['durations']
    trials=[]
    for a,b,c,e in itertools.product([1,2],[2,3],[1,2],[-1,0]):
       pcm=decode_pulse(f,d,a,b,c,e)
       st,sp,click=cp.scores(pcm)
       trials.append({'pulse':[a,b,c,e],'stoi':st,'spectral':sp,'clicks':click})
    trials.sort(key=lambda r:(r['clicks']==0,r['stoi']-0.012*r['spectral']),reverse=True)
    default=next(v for v in trials if v['pulse']==[2,3,2,-1])
    report[name]={'old':default,'best_untrained':trials[0],'candidates':trials}
    print(name,'old',round(default['stoi'],5),'best',trials[0]['pulse'],round(trials[0]['stoi'],5), 'clicks',trials[0]['clicks'],flush=True)
   if write: (BASE/'pulse_report.json').write_text(json.dumps(report,indent=2))
   return report
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('names',nargs='*',default=['chego','otvechaesh','vinni']);arg=a.parse_args();process(arg.names)
