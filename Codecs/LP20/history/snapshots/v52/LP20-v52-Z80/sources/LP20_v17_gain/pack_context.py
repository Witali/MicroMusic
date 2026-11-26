#!/usr/bin/env python3
"""LP10G v1 PC transport, CRC32, optional zlib or LZMA. Expanded on PC, never Z80.
Header: magic, version, codec (0 zlib/1 xz), raw length, crc32.
Payload: sample count, token count, threshold, period, grid size, alpha,
Q24 LPC coefficients, banks, lengths, nominal PWM levels, grids, base vectors,
active context entries (slot, bank, vector), tokens. All fields little endian.
"""
import struct,zlib,lzma,sys,json
from pathlib import Path
import numpy as np
from reuse_context import decode_reuse,f
HDR=struct.Struct('<4sBBII');SUB=struct.Struct('<IIHHBd')
def raw_payload(d,meta):
 a=np.rint(d['a']*2**24).astype('<i4');assert np.array_equal(a.astype(float)/2**24,d['a']);bk,bm,lens,idx=[d[k] for k in ('bk','bm','lens','idx')];alt,ab,active=[d[k] for k in ('alt','ab','active')];ww=d['ww10'];grid=meta['grid'];assert len(bk)==255 and len(ww)<=255 and max(lens)<=255 and len(grid)<=255
 raw=SUB.pack(int(sum(lens[idx])),len(idx),int(d['threshold']),meta['period'],len(grid),meta['pattern_alpha'])+a.tobytes()+bm.astype('u1').tobytes()+lens.astype('u1').tobytes()+bytes([len(ww)])+ww.astype('<u2').tobytes()+np.asarray(grid,dtype='<u2').tobytes()+b''.join(v[:n].astype('<i2').tobytes() for v,n in zip(bk,lens))+bytes([int(active.sum())])+b''.join(bytes([int(k),int(ab[k])])+alt[k,:lens[k]].astype('<i2').tobytes() for k in np.flatnonzero(active))+idx.astype('u1').tobytes()
 return raw

def pack(d,meta,path):
 raw=raw_payload(d,meta);zs=[]
 for strategy in (zlib.Z_DEFAULT_STRATEGY,zlib.Z_FILTERED,zlib.Z_RLE,zlib.Z_HUFFMAN_ONLY):
  for level in (6,9):
   c=zlib.compressobj(level,zlib.DEFLATED,15,9,strategy);zs.append((0,c.compress(raw)+c.flush()))
 zs.append((1,lzma.compress(raw,preset=9)));co,z=min(zs,key=lambda a:len(a[1]));data=HDR.pack(b'L10G',1,co,len(raw),zlib.crc32(raw))+z;Path(path).write_bytes(data);print('LP10G',len(data),'zlib min',min(len(z) for c,z in zs if c==0)+HDR.size,'XZ',len(zs[-1][1])+HDR.size,'codec',co);return len(data)

def unpack(path):
 data=Path(path).read_bytes();magic,ver,co,nraw,crc=HDR.unpack_from(data);assert magic==b'L10G' and ver==1 and co in (0,1);raw=(zlib.decompress if co==0 else lzma.decompress)(data[HDR.size:]);assert len(raw)==nraw and zlib.crc32(raw)==crc;n,nt,th,period,ng,alpha=SUB.unpack_from(raw);off=SUB.size
 def take(dt,count):
  nonlocal off
  a=np.frombuffer(raw,dtype=dt,count=count,offset=off).copy();off+=a.nbytes;return a
 a=take('<i4',48).reshape(8,6).astype(float)/2**24;bm=take('u1',255);lens=take('u1',255).astype(np.int32);nw=take('u1',1)[0];ww=take('<u2',int(nw)).astype(np.int16);grid=take('<u2',ng).astype(int).tolist();bk=np.zeros((255,int(max(lens))),np.int16)
 for k,l in enumerate(lens):bk[k,:l]=take('<i2',int(l))
 alt=np.zeros_like(bk);ab=bm.copy();active=np.zeros(255,bool);nact=int(take('u1',1)[0]);
 for _ in range(nact):
  k,b=take('u1',2);assert not active[k] and b<8;active[k]=True;ab[k]=b;alt[k,:lens[k]]=take('<i2',int(lens[k]))
 idx=take('u1',nt).astype(np.int16);assert off==len(raw) and sum(lens[idx])==n;tb=f.compact_tables(a);y,ov=decode_reuse(tb,bk,bm,lens,idx,alt,ab,active,th);assert not ov
 return dict(a=a,bk=bk,bm=bm,lens=lens,idx=idx,alt=alt,ab=ab,active=active,threshold=th,y=y,tb=tb,target=np.zeros(n),ww10=ww,bits=10),dict(period=period,grid=grid,pattern_alpha=alpha)
if __name__=='__main__':
 if sys.argv[1]=='pack':pack(dict(np.load(sys.argv[2])),json.loads(Path(sys.argv[3]).read_text()),sys.argv[4])
 else:
  d,m=unpack(sys.argv[2]);np.savez(sys.argv[3],**d);print(m)
