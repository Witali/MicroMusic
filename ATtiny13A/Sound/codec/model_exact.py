"""Byte-exact emulation of TinyLPC DSP operations with the AVR frame timing.
Verification uses independent JavaScript instruction-level AVR emulator, not this model.
"""
import numpy as np
from numba import njit
@njit(cache=True)
def synth_exact(K,P,E,length,shift=4):
    n=len(P);out=np.zeros(length,dtype=np.int64)
    st=np.zeros(7,dtype=np.int64)
    phase=1;seed=0xa7
    lastfi=-1
    for i in range(length):
       fi=((i+1)//256)%n  # AVR increments frame clock *before* rendering and loops after last frame
       if fi!=lastfi:
          if E[fi]==0: st[:]=0
          lastfi=fi
       p=P[fi];g=E[fi]
       if p:
          phase=(phase-1)&255
          if phase==0:
             phase=int(p)
             excite=5*g
          else:
             dt=(p-phase)&255
             excite=3*g if dt==1 else -2*g if dt==3 else 0
       else:
          seed=(seed>>1)^(0xb8 if seed&1 else 0)
          excite=-g if seed&1 else g
       forward=excite
       for stage in range(6,-1,-1):
          v=(int(K[fi,stage])*st[stage])>>shift
          forward=((forward-v+128)&255)-128
          if stage<6:
             v2=(int(K[fi,stage])*forward)>>shift
             st[stage+1]=((st[stage]+v2+128)&255)-128
       st[0]=forward
       out[i]=forward
    return out

if __name__=='__main__':
 z=np.load('best_parameters.npz');aa=synth_exact(z['K'],z['P'],z['E'],22272)
 bb=np.fromfile('emu_pwm_u8.raw',dtype='u1').astype(int)-128
 print('exact',np.mean(aa==bb),'r',np.corrcoef(aa,bb)[0,1],'l1',np.abs(aa-bb).mean())
 print('first disagreement',np.flatnonzero(aa!=bb)[:30]);
 for pos in [253,254,255,256,257,258,511,512,767,768,1000,2048]:print(pos,aa[pos],bb[pos])
