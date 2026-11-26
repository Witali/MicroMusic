#!/usr/bin/env python3
"""Lossless recalculation of transmitted prefix lengths; not a new voice dictionary."""
from joint_pwm import *
from adaptive45 import BASE,decode_v,write_v,build,HEADER42,G,M,TYP,FS,struct

def stats(frames):
 out=[]
 for _,m,par,p,s,q in frames:
  nz=np.flatnonzero(q);prev=-1
  for j in nz:
   out.append((prev,int(j)-prev-1,abs(int(q[j])),int(q[j])<0,len(nz),s));prev=int(j)
 return np.array(out,dtype=int)

def main():
 rows=[]
 for c in ('first','second'):
  out=ROOT/c;base,d,meta,ref,lv,x=data(c);book=(base/'book.bin').read_bytes()
  for src in sorted(out.glob('*-6k.lp4v'))+sorted(out.glob('*-5.9k.lp4v')):
   if src.stem.endswith('-pack'):continue
   hdr=struct.unpack_from(HEADER42,src.read_bytes())[1:];z,fr,_=decode_v(src,book);ln=build(stats(fr),G,M,TYP)
   if max(map(max,ln))>15:continue
   dst=src.with_name(src.stem+'-pack.lp4v');n=write_v(dst,hdr,fr,ln,True);zz,_,nn=decode_v(dst,book);assert n==nn and np.array_equal(zz,z);a=src.stat().st_size;b=dst.stat().st_size
   assert np.array_equal(render(zz,d,meta),wavfile.read(src.with_suffix('.wav'))[1]);row=dict(clip=c,profile=src.stem,old_bytes=a,bytes=b,saved_bytes=a-b,kbps=b*8*FS/hdr[0]/1000,pcm_equal=True);rows.append(row);print(row,flush=True)
 (ROOT/'repack.json').write_text(json.dumps(rows,indent=2))
if __name__=='__main__':main()
