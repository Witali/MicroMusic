"""LP10C compact PC-side transport. Expand into NPZ, then build_h10.py.
No compressed table expansion on Z80; CRC32 detects damaged raw payload.
"""
import sys,struct,zlib
from pathlib import Path
import numpy as np
from build_h10 import compact_tables
from precision_study import reconstruct
HDR=struct.Struct('<4sBBBBHBIIII') # magic,ver,order,banks,bits,period,pulses,n,bytes,raw bytes,crc

def pack(src,dst):
 d=np.load(src);a,bk,bm,lens,idx,ww=[d[k] for k in ('a','bk','bm','lens','idx','ww')];q=np.rint(a*2**24).astype('<i4');assert np.array_equal(q.astype(float)/2**24,a);assert len(bk)==255 and len(ww)<=255
 raw=q.tobytes()+bm.astype(np.uint8).tobytes()+lens.astype(np.uint8).tobytes()+bytes([len(ww)])+ww.astype('<u2').tobytes()+b''.join(v[:n].astype('<i2').tobytes() for v,n in zip(bk,lens))+idx.astype(np.uint8).tobytes();n=int(sum(lens[idx]));data=HDR.pack(b'L10C',1,a.shape[1],a.shape[0],10,256,10,n,len(idx),len(raw),zlib.crc32(raw))+zlib.compress(raw,9);Path(dst).write_bytes(data);print('LP10C',len(data),'bytes',len(data)*8/(n/7812.5)/1000,'kbps',flush=True)

def unpack(src,dst):
 data=Path(src).read_bytes();magic,ver,order,banks,bits,period,pulses,n,sz,rawlen,crc=HDR.unpack_from(data);assert (magic,ver,order,bits,period,pulses)==(b'L10C',1,6,10,256,10);raw=zlib.decompress(data[HDR.size:]);assert len(raw)==rawlen and zlib.crc32(raw)==crc
 off=banks*order*4;a=np.frombuffer(raw[:off],'<i4').reshape(banks,order).astype(float)/2**24;bm=np.frombuffer(raw[off:off+255],np.uint8).copy();off+=255;lens=np.frombuffer(raw[off:off+255],np.uint8).astype(np.int32);off+=255;cnt=raw[off];off+=1;ww=np.frombuffer(raw[off:off+cnt*2],'<u2').copy();off+=cnt*2;bk=np.zeros((255,max(lens)),np.int16)
 for k,l in enumerate(lens):bk[k,:l]=np.frombuffer(raw[off:off+l*2],'<i2');off+=l*2
 idx=np.frombuffer(raw[off:],np.uint8).astype(np.int16);assert len(idx)==sz and max(idx)<255 and sum(lens[idx])==n;tb=compact_tables(a);t=np.zeros(n);y,_,over=reconstruct(t,tb,bk,bm,lens,idx,10);assert not over
 np.savez(dst,target=t,a=a,tb=tb,bk=bk,bm=bm,lens=lens,idx=idx,y=y,bits=10,ww=ww);return y
if __name__=='__main__':
 if sys.argv[1]=='pack':pack(*sys.argv[2:])
 else:unpack(*sys.argv[2:])
