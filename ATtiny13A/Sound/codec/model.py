import numpy as np
from numba import njit

@njit
def u8(v):return v & 255
@njit
def s8(v):return ((v+128)&255)-128
@njit
def mul_q4(x,k):
  a=s8(x)
  if k<0:a=s8(-a)
  # AVR multiply by repeated add then arithmetic shift right 4
  return (a*abs(k)>>4)&255

@njit
def decode(speech,mode_offset=0,overrides=None):
  frames=len(speech)//6;n=frames*256
  out=np.empty(n,np.uint8)
  state=np.zeros(8,np.int32);k=np.zeros(8,np.int32)
  seed=0xa7;period=0;gain=0;phase=1;mode=0
  for sample in range(n):
    frame=0 if sample<255 or sample==n-1 else (sample+1)//256
    if sample==0 or (sample&255)==255:
      period=int(speech[6*frame]);gain=int(speech[6*frame+1])&15
      if overrides is not None:mode=int(overrides[frame]);
      else:mode=(int(speech[6*frame+1])>>4)&3
      phase=period
      for j in range(4):
        data=int(speech[6*frame+2+j])
        k[j*2]=(data&15)-8
        k[j*2+1]=(data>>4)-8
    ex=0
    if period:
      phase=(phase-1)&255
      if phase==0:
        phase=period
        ex=(2*gain)&255
      else:
        lag=period-phase
        if lag==1:
          ex=(gain*(3 - (mode&1)))&255
        elif lag==2:
          ex=(gain*(2 - (mode>>1)))&255
        elif lag==3:
          ex=(-gain)&255
    else:
      low=seed&1
      seed=seed>>1
      if low:seed=seed ^ 0xb8
      ex=((-gain if (seed&1) else gain))&255
    for j in range(7,-1,-1):
      old=state[j];coef=k[j]
      ex=u8(ex-mul_q4(old,coef))
      if j<7:state[j+1]=u8(old+mul_q4(ex,coef))
    state[0]=ex
    out[sample]=u8(ex+128)
  return out
if __name__=='__main__':
 from pathlib import Path
 for voice in ['chego','otvechaesh','vinni']:
  d=Path('/mnt/data/MicroMusic_MiniLPC_Verified_328_350/examples')/voice/'full'
  speech=np.frombuffer((d/'speech.bin').read_bytes(),np.uint8)
  ref=np.frombuffer((d/'avr_pcm.raw').read_bytes(),np.uint8)
  got=decode(speech)
  print(voice,len(ref),'diff',int(np.sum(got!=ref)),'first',[(i,ref[i],got[i]) for i in np.nonzero(got!=ref)[0][:4]])
