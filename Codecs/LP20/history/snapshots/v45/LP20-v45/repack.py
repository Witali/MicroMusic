#!/usr/bin/env python3
"""LP4R: lossless syntax experiment for LP42, software only.
Fixed Rice k=5 for count, delta4 for scale. No per-coefficient continuation bit.
Requires the original book. No change to any DCT coefficient or predictor.
"""
from trellis42 import read_frames
from v42 import *

def repack(src, book, dst):
    hdr, frames = read_frames(src, book)
    n, frame, grid, K, L, b = hdr
    w = Writer(); pm=0; pp=(); st=steps(grid); prev_scale=None
    for m,par,p,s,k,q,oldbits in frames:
        for v,width in fields(m,par,pm,pp,grid,K,frame,st): w.put(v,width)
        scale_fields=((s,7),) if prev_scale is None else delta(s,prev_scale,7,4)
        for v,width in scale_fields: w.put(v,width)
        w.put(k,2)
        nz=np.flatnonzero(q); count=len(nz)
        w.unary(count>>5);w.put(count&31,5)
        prev=-1
        for j in nz:
            gap=int(j)-prev-1;prev=int(j);v=int(q[j]);w.unary(gap>>k);w.put(gap&((1<<k)-1),k);w.eg(abs(v)-1);w.put(int(v<0),1)
        pm,pp,prev_scale=m,par,s
    Path(dst).write_bytes(struct.pack(HEADER42,b'LP4R',*hdr)+w.bytes())
    return len(w.bits)

def decode_r(path,bookdata):
    raw=Path(path).read_bytes();magic,n,frame,grid,K,L,b=struct.unpack_from(HEADER42,raw)
    assert magic==b'LP4R'
    wt=wave_table(unpack_book(bookdata,K,L,b));st=steps(grid);r=Reader(raw[struct.calcsize(HEADER42):]);pm=0;pp=();prev_scale=None;out=[];modes=[]
    kb=int(math.log2(K));nb=int(math.log2(grid))
    for pos in range(0,n,frame):
        m=r.get(2);nn=min(frame,n-pos);p=np.zeros(nn);par=()
        if m:
            if pm:
                pi=read_delta(r,pp[0],nb,4);i=read_repeat(r,pp[-3],kb);ph=read_delta(r,((pp[-2]*256+int(st[pp[0]])*frame+128)//256)%256,8,4,True);g=read_delta(r,pp[-1],8,4)
            else:pi=r.get(nb);i=r.get(kb);ph=r.get(8);g=r.get(8)
            par=(pi,i,ph,g);p=wave(wt[i],st[pi],ph,g,nn)
            if m>=2:
                j=read_repeat(r,i,kb);ph2=read_delta(r,ph,8,4,True) if m==2 else ph;g2=read_delta(r,g,8,4);par+=(j,ph2,g2);a=np.linspace(0,1,nn);p=p*(1-a)+wave(wt[j],st[pi],ph2,g2,nn)*a
        s=r.get(7) if prev_scale is None else read_delta(r,prev_scale,7,4)
        k=r.get(2);cnt=(r.unary()<<5)+r.get(5);assert cnt<=nn
        q=np.zeros(nn);j=-1
        for _ in range(cnt):
            j+=(r.unary()<<k)+r.get(k)+1;assert j<nn;z=r.eg()+1;q[j]=z*(-1 if r.get(1) else 1)
        out.append(p+idct(q*SCALES[s],norm='ortho'));modes.append(m);pm,pp,prev_scale=m,par,s
    assert not r.bits[r.pos:].any() and len(r.bits)-r.pos<8
    return np.concatenate(out),np.array(modes),r.pos

def test(src,book,dst):
    nb=repack(src,book,dst);x,m,_=decode(src,book);y,mm,n2=decode_r(dst,book)
    assert nb==n2 and np.array_equal(x,y) and np.array_equal(m,mm)
    a=Path(src).stat().st_size;b=Path(dst).stat().st_size
    return dict(old_bytes=a,new_bytes=b,saved_bytes=a-b,saved_pct=100*(a-b)/a,stream_kbps=b*8*FS/len(x)/1000,pcm_equal=True,max_pcm_difference=float(np.max(abs(x-y))))
if __name__=='__main__':
    import sys
    print(json.dumps(test(sys.argv[1],Path(sys.argv[2]).read_bytes(),sys.argv[3]),indent=2))
