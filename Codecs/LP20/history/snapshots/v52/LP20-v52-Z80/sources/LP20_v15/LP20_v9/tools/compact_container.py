"""LP2C transport format: losslessly store an LP2P dictionary as exact Q24
coefficients and variable-length residuals. Expand on PC before programming ROM.
Z80 never runs zlib, and does not require RAM. Compatible with build_packed.py.
"""
from pathlib import Path
import sys,struct,zlib,hashlib
import numpy as np
Q=1<<24
V=np.r_[np.arange(128),np.arange(-128,0)].astype(np.int64)
HEADER=struct.Struct('<4sBBBBHBIII') # magic, version, LPC order, banks, levels, period, pulses, sample count, raw len, CRC32

def exact_coeff(t):
 nz=V!=0;v=V[nz];a=t[nz].astype(float);lo=np.max(np.minimum((a-.5)/v,(a+.5)/v));hi=np.min(np.maximum((a-.5)/v,(a+.5)/v));q=int(round((lo+hi)*Q/2))
 for k in (0,-1,1,-2,2,-4,4,-8,8):
  if np.array_equal(np.rint(V*(q+k)/Q).astype(np.int16),t):return q+k
 raise ValueError('table cannot be represented exactly at Q24')

def pack(npz,out):
 d=np.load(npz);tb,bk,bm,lens,idx=[d[k] for k in ('tb','bk','bm','lens','idx')];assert len(lens)==255 and tb.ndim==3 and max(lens)<=255
 nb,order,_=tb.shape;q=np.array([[exact_coeff(t) for t in b] for b in tb],dtype='<i4');assert np.array_equal(np.rint(q[:,:,None]*V[None,None,:]/Q).astype(np.int16),tb)
 raw=q.tobytes()+bm.astype(np.uint8).tobytes()+lens.astype(np.uint8).tobytes()+b''.join(v[:n].astype(np.int8).tobytes() for v,n in zip(bk,lens))+idx.astype(np.uint8).tobytes()
 data=HEADER.pack(b'LP2C',1,order,nb,77,128,20,int(np.sum(lens[idx])),len(raw),zlib.crc32(raw))+zlib.compress(raw,9);Path(out).write_bytes(data);print('LP2C',len(data),'bytes; effective',len(data)*8/(np.sum(lens[idx])/7812.5)/1000,'kbps',flush=True)


def unpack(path,out):
 data=Path(path).read_bytes();magic,ver,order,nb,levels,period,pulses,n,sz,crc=HEADER.unpack_from(data);assert magic==b'LP2C' and ver==1 and order in (4,6,8) and nb<=32 and levels==77 and period==128 and pulses==20
 raw=zlib.decompress(data[HEADER.size:]);assert len(raw)==sz and zlib.crc32(raw)==crc
 off=nb*order*4;q=np.frombuffer(raw[:off],'<i4').reshape(nb,order);tb=np.rint(q[:,:,None]*V[None,None,:]/Q).astype(np.int16);bm=np.frombuffer(raw[off:off+255],np.uint8).copy();lens=np.frombuffer(raw[off+255:off+510],np.uint8).astype(np.int32);off+=510;assert max(bm)<nb and min(lens)>0
 bk=np.zeros((255,max(lens)),np.int16)
 for k,ln in enumerate(lens):bk[k,:ln]=np.frombuffer(raw[off:off+ln],np.int8);off+=ln
 idx=np.frombuffer(raw[off:],np.uint8).astype(np.int16);assert max(idx)<255 and sum(lens[idx])==n
 y=np.empty(n,np.int16);h=[0]*order;p=0;u=tb.astype(np.uint8)
 for k in idx:
  for j in range(lens[k]):
   v=(int(bk[k,j])+sum(int(u[bm[k],i,h[i]]) for i in range(order)))&255;y[p]=v if v<128 else v-256;p+=1;h=[v]+h[:-1]
 np.savez(out,tb=tb,bk=bk,bm=bm,lens=lens,idx=idx,y=y);return y
if __name__=='__main__':
 if sys.argv[1]=='pack':pack(sys.argv[2],sys.argv[3])
 elif sys.argv[1]=='unpack':unpack(sys.argv[2],sys.argv[3])
 else:raise SystemExit('pack input.npz output.lp2c | unpack input.lp2c output.npz')
