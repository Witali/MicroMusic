"""Read LPC2 Improved's excitation labels (LSB-first) for offline conversion.
The ATtiny13A does not decode LSF and does not claim bitstream compatibility.
"""
import struct, numpy as np
from pathlib import Path
P=Path(__file__).parent
p=(P/'lpc2_improved_reference.lp2').read_bytes() if (P/'lpc2_improved_reference.lp2').exists() else (P.parent/'MicroMusic-ATtiny13-LPC-v5/phrase_lpc2.lp2').read_bytes()
assert p[:4]==b'LPC2' and p[4]==1
sr,H,W=struct.unpack_from('<HHH',p,6);n,ns,nbits=struct.unpack_from('<III',p,12)
class Br:
 def __init__(self,b):self.b=b;self.pos=0
 def read(self,n):
  r=0
  for bit in range(n):r|=((self.b[self.pos>>3]>>(self.pos&7))&1)<<bit;self.pos+=1
  return r
br=Br(p[36:]);modes=[];energies=[]
for fi in range(n):
 eng=br.read(5)
 if not eng:
  modes.append(0);energies.append(0);continue
 mode=br.read(2);rep=br.read(1)
 voiced=mode==1 or mode==2
 if voiced:br.read(6)
 if not rep:
  for bits in ([5,5,4,4,4,4,4,3,3,3] if voiced else [5,5,4,4]):br.read(bits)
 modes.append(mode);energies.append(eng)
assert br.pos<=nbits
modes=np.asarray(modes);energies=np.asarray(energies)
z=np.load(P/'best_parameters.npz');pitch=z['P'];gain=z['E']
N=len(pitch)
# Single interval in TinyLPC may overlap one or more LPC2 frames.
ms=[]; en=[]
for i in range(N):
 lo=i*256/7500;hi=(i+1)*256/7500
 j0=int(lo*sr/H);j1=min(n-1,int(np.nextafter(hi*sr/H,-np.inf)))
 mm=modes[j0:j1+1]
 ms.append(mm.tolist());en.append(energies[j0:j1+1].tolist())
for method in range(4):
 a=np.zeros(N,np.uint8)
 for i,mm in enumerate(ms):
  if not pitch[i] or pitch[i]>95 or not gain[i]:continue
  if method==0:a[i]=0
  if method==1:a[i]=int(mm.count(1)>0)
  if method==2:a[i]=int(mm.count(1)+mm.count(3)>0)
  if method==3:a[i]=1
 np.save(P/f'mode_from_lpc2_{method}.npy',a)
 print(method,'mixed',int(a.sum()),'frames',np.where(a)[0].tolist())
print('LPC2 stream',len(p),'bytes',n,'frames',sr,'Hz',H,'hop','excitation modes',np.bincount(modes,minlength=4).tolist())
