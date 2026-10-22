"""LPC2-lite variable-length speech events: 5-byte frames + one-byte silence RLE.
Each pitch byte 0..127 = plain voiced/unvoiced, 128..223 = breathy voiced,
225..254 = silence N=(byte-224) frames, 255 = loop marker.
"""
from pathlib import Path
import numpy as np
P=Path(__file__).resolve().parent
z=np.load(P/'best_parameters.npz');K=z['K'];pitch=z['P'];E=z['E']
mode=np.load(P/'mode_bits.npy') if (P/'mode_bits.npy').exists() else np.zeros_like(pitch)
assert K.shape==(87,7)
stream=bytearray();i=0;events=[]
while i<len(pitch):
 if E[i]==0 and pitch[i]==0:
  j=i
  while j<len(E) and E[j]==0 and pitch[j]==0 and j-i<30:j+=1
  stream.append(0xe0+j-i); events.append(('silence',i,j-i))
  i=j
 else:
  k=K[i].astype(int);pi=int(pitch[i]);gain=int(E[i]);m=int(mode[i])
  assert all(-7<=n<=7 for n in k)
  assert 0<=pi<=127 and 0<=gain<=15 and 0<=m<=1
  if pi>95 and m:raise ValueError('Mixed excitation period needs <96')
  head=pi| (m<<7)
  stream.extend([head, (gain&15)|((k[0]+8)<<4),((k[2]+8)<<4)|(k[1]+8),((k[4]+8)<<4)|(k[3]+8),((k[6]+8)<<4)|(k[5]+8)])
  events.append(('normal',i,int(head)))
  i+=1
(P/'voice_tinylpc.bin').write_bytes(stream)
assert sum(ev[2] if ev[0]=='silence' else 1 for ev in events)==87
print('Speech',len(stream),'bytes',len(events),'events; saved',435-len(stream),'bytes')
