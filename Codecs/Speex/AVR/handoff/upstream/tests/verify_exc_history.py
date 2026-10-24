#!/usr/bin/env python3
"""Verify excitation-history address equivalence for NB pitch 17..144.
This is an index/history invariant test, NOT a full standard Speex decode.
"""
import random
R=random.Random(0x5531)
REF_HISTORY=334
OPT_HISTORY=206
BUF1=[0]*500
BUF2=[0]*372
SAMPLE_COUNT=0
for frame in range(10000):
  BUF1[:340]=BUF1[160:500]
  BUF2[:212]=BUF2[160:372]
  for sub in range(4):
    lag=R.randrange(17,145)
    for n in range(40):
      offset=sub*40+n
      back=lag+R.randrange(-1,2)
      if back<=0:back=1
      v1=BUF1[REF_HISTORY+offset-back]
      v2=BUF2[OPT_HISTORY+offset-back]
      assert v1==v2, (frame,sub,n,back,v1,v2)
      # Both receive the same new excitation, created using history.
      sample=(v1*3+R.randrange(-2000,2001))//4
      BUF1[REF_HISTORY+offset]=sample
      BUF2[OPT_HISTORY+offset]=sample
      SAMPLE_COUNT+=1
print('PASS:',frame+1,'frames,',SAMPLE_COUNT,'excitation writes and lagged accesses identical')
