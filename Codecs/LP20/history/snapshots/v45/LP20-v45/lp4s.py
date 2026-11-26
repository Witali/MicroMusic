#!/usr/bin/env python3
"""Lossless joint gap/magnitude prefix coding for LP42; PC reference only.
Train Huffman lengths on a separate recording. Include all lengths in the file.
"""
from study import *
from collections import Counter
import argparse


def write_file(hdr, frames, lens,G,M,typ,dst):
    n,frame,grid,K,L,b=hdr
    table=Writer()
    for ln in lens:
        for v in ln:table.put(v,4)
    enc=[codes(ln) for ln in lens]
    w=Writer();pm=0;pp=();st=steps(grid);ps=None
    for m,par,p,s,k,q,_ in frames:
        for v,width in fields(m,par,pm,pp,grid,K,frame,st):w.put(v,width)
        for v,width in (((s,7),) if ps is None else delta(s,ps,7,4)):w.put(v,width)
        nz=np.flatnonzero(q);cnt=len(nz);w.unary(cnt>>5);w.put(cnt&31,5);prev=-1
        for j in nz:
            j=int(j);g=j-prev-1;v=int(q[j]);mag=abs(v)
            sym=min(g,G)*M+min(mag,M)-1
            w.put(*enc[ctx(prev,cnt,s,typ)][sym])
            if g>=G:w.eg(g-G)
            if mag>=M:w.eg(mag-M)
            w.put(int(v<0),1);prev=j
        pm,pp,ps=m,par,s
    Path(dst).write_bytes(struct.pack(HEADER42,b'LP4S',*hdr)+bytes([G,M,typ])+table.bytes()+w.bytes())
    return len(w.bits),len(table.bytes())


def read_symbol(r,dec):
    v=0
    for k in range(1,16):
        v=(v<<1)|r.get(1)
        if (v,k) in dec:return dec[v,k]
    raise ValueError('invalid prefix')


def decode_s(path,bookdata):
    raw=Path(path).read_bytes();magic,n,frame,grid,K,L,b=struct.unpack_from(HEADER42,raw)
    assert magic==b'LP4S';offset=struct.calcsize(HEADER42);G,M,typ=raw[offset:offset+3];offset+=3
    assert 1<=G<=16 and 2<=M<=24 and 0<=typ<=4
    nt=nc(typ)*(G+1)*M;size=(nt+1)//2;t=Reader(raw[offset:offset+size]);lens=[[t.get(4) for _ in range((G+1)*M)] for _ in range(nc(typ))]
    assert all(1<=v<=15 for ln in lens for v in ln) and not t.bits[t.pos:].any()
    dec=[{v:k for k,v in codes(ln).items()} for ln in lens];r=Reader(raw[offset+size:]);wt=wave_table(unpack_book(bookdata,K,L,b));st=steps(grid);pm=0;pp=();ps=None;out=[];modes=[];records=[];kb=int(math.log2(K));nb=int(math.log2(grid))
    for pos in range(0,n,frame):
        m=r.get(2);nn=min(frame,n-pos);p=np.zeros(nn);par=()
        if m:
            if pm:
                pi=read_delta(r,pp[0],nb,4);i=read_repeat(r,pp[-3],kb);ph=read_delta(r,((pp[-2]*256+int(st[pp[0]])*frame+128)//256)%256,8,4,True);g=read_delta(r,pp[-1],8,4)
            else:pi=r.get(nb);i=r.get(kb);ph=r.get(8);g=r.get(8)
            par=(pi,i,ph,g);p=wave(wt[i],st[pi],ph,g,nn)
            if m>=2:
                j=read_repeat(r,i,kb);ph2=read_delta(r,ph,8,4,True) if m==2 else ph;g2=read_delta(r,g,8,4);par+=(j,ph2,g2);a=np.linspace(0,1,nn);p=p*(1-a)+wave(wt[j],st[pi],ph2,g2,nn)*a
        s=r.get(7) if ps is None else read_delta(r,ps,7,4);cnt=(r.unary()<<5)+r.get(5);assert cnt<=nn;q=np.zeros(nn,np.int32);j=-1
        for _ in range(cnt):
            sym=read_symbol(r,dec[ctx(j,cnt,s,typ)]);gap,mag=divmod(sym,M);mag+=1
            if gap==G:gap+=r.eg()
            if mag==M:mag+=r.eg()
            j+=gap+1;assert j<nn;q[j]=-mag if r.get(1) else mag
        out.append(p+idct(q*SCALES[s],norm='ortho'));modes.append(m);records.append((m,par,s,q));pm,pp,ps=m,par,s
    assert not r.bits[r.pos:].any() and len(r.bits)-r.pos<8
    return np.concatenate(out),np.array(modes),r.pos,records


def test(src,train,dst,G=2,M=12,typ=3):
    src=Path(src);train=Path(train);dst=Path(dst);book=(src/'book.bin').read_bytes();hdr,f=read_frames(src/'morph.lp42',book);_,tf=read_frames(train/'morph.lp42',(train/'book.bin').read_bytes());ln=build(pairs(tf),G,M,typ)
    assert max(map(max,ln))<=15
    dst.parent.mkdir(parents=True,exist_ok=True);nb,tb=write_file(hdr,f,ln,G,M,typ,dst);x,m,_=decode(src/'morph.lp42',book);xr,mr,_=decode_r(src/'morph.lp4r',book);y,mm,n2,rr=decode_s(dst,book)
    assert nb==n2 and np.array_equal(x,y) and np.array_equal(xr,y) and np.array_equal(m,mm) and np.array_equal(mr,mm)
    assert all((a[0],a[1],a[3])==b[:3] and np.array_equal(a[5],b[3]) for a,b in zip(f,rr)) and len(f)==len(rr)
    sz=dst.stat().st_size;old=(src/'morph.lp4r').stat().st_size;n=hdr[0];a=(src/'morph.lp42').stat().st_size
    return dict(clip=src.name,G=G,M=M,context=typ,contexts=nc(typ),table_bytes=tb,original_bytes=a,lp4r_bytes=old,bytes=sz,stream_kbps=sz*8*FS/n/1000,with_book_and_dds_kbps=(sz+2048)*8*FS/n/1000,saved_vs_lp4r=old-sz,saved_pct=100*(old-sz)/old,pcm_equal=True,coefficient_equal=True,max_pcm_difference=float(np.max(abs(x-y))))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('src');p.add_argument('train');p.add_argument('out');p.add_argument('--gap',type=int,default=2);p.add_argument('--mag',type=int,default=12);p.add_argument('--context',type=int,default=3);a=p.parse_args();print(json.dumps(test(a.src,a.train,a.out,a.gap,a.mag,a.context),indent=2))
