#!/usr/bin/env python3
"""Exact Lagrangian trellis of sparse transform coefficient positions/magnitudes.
Preserve sample predictor parameters; optimize DCT residual across the full clip.
"""
from v42 import *
@njit(cache=True)
def trellis(c,scale,k,lam):
    n=len(c);M=1<<k;best=np.full(M,1e100);best_i=np.full(M,-2,np.int32);best[M-1]=lam;best_i[M-1]=-1
    dp=np.empty(n);parent=np.empty(n,np.int32);mag=np.empty(n,np.int32);end=-1;cost=0.
    for j in range(n):
        a=abs(c[j]);near=max(1,int(np.rint(a/scale)));q=near;v=(a-q*scale)**2-a*a+lam*MAGBITS[min(q,len(MAGBITS)-1)]
        # For each shorter Exp-Golomb category the best integer is its upper bound.
        # q=1 is the shortest nonzero category.
        p=1
        while p<=near:
            z=min(near,2*p-1);vv=(a-z*scale)**2-a*a+lam*MAGBITS[min(z,len(MAGBITS)-1)]
            if vv<v:v=vv;q=z
            p*=2
        mn=1e100;ii=-2
        for r in range(M):
            val=best[r]+lam*((j-1)//M-int(r>(j-1)%M))
            if val<mn:mn=val;ii=best_i[r]
        dp[j]=mn+v+lam*(2+k);parent[j]=ii;mag[j]=q if c[j]>=0 else -q
        adj=dp[j]-lam*(j//M)
        if adj<best[j%M]:best[j%M]=adj;best_i[j%M]=j
        if dp[j]<cost:cost=dp[j];end=j
    q=np.zeros(n,np.int32)
    while end>=0:q[end]=mag[end];end=parent[end]
    return q
@njit(cache=True)
def qcost(c,q,s,k):
    prev=-1;bits=10;err=0.
    for j in range(len(c)):
        z=q[j];err+=(c[j]-z*s)**2
        if z:
            gap=j-prev-1;prev=j;bits+=2+k+(gap>>k)+MAGBITS[min(abs(z),len(MAGBITS)-1)]
    return bits,err
@njit(cache=True)
def variants(c,s0,k0):
    # Keep best SSE for every measured residual length.
    B=max(640,len(c)*5);er=np.full(B+1,1e100);qs=np.zeros((B+1,len(c)),np.int16);ss=np.full(B+1,-1,np.int16);ks=np.zeros(B+1,np.int8)
    for s in range(max(0,s0-10),min(128,s0+11),2):
        for k in range(4):
            for f in (.10,.20,.40,.80,1.6):
                q=trellis(c,SCALES[s],k,f*SCALES[s0]**2);b,e=qcost(c,q,SCALES[s],k)
                if b<=B and e<er[b]:er[b]=e;qs[b]=q;ss[b]=s;ks[b]=k
    return er,qs,ss,ks

def read_frames(path,bookdata):
    raw=Path(path).read_bytes();magic,n,frame,grid,K,L,b=struct.unpack_from(HEADER42,raw);assert magic==b'LP42';book=unpack_book(bookdata,K,L,b);wt=wave_table(book);st=steps(grid);r=Reader(raw[struct.calcsize(HEADER42):]);pm=0;pp=();out=[];kb=int(math.log2(K));nb=int(math.log2(grid))
    for pos in range(0,n,frame):
        m=r.get(2);nn=min(frame,n-pos);p=np.zeros(nn);par=()
        if m:
            if pm:
                pi=read_delta(r,pp[0],nb,4);i=read_repeat(r,pp[-3],kb);ph=read_delta(r,((pp[-2]*256+int(st[pp[0]])*frame+128)//256)%256,8,4,True);g=read_delta(r,pp[-1],8,4)
            else:pi=r.get(nb);i=r.get(kb);ph=r.get(8);g=r.get(8)
            par=(pi,i,ph,g);p=wave(wt[i],st[pi],ph,g,nn)
            if m>=2:
                j=read_repeat(r,i,kb);ph2=read_delta(r,ph,8,4,True) if m==2 else ph;g2=read_delta(r,g,8,4);par+=(j,ph2,g2);a=np.linspace(0,1,nn);p=p*(1-a)+wave(wt[j],st[pi],ph2,g2,nn)*a
        start=r.pos;s=r.get(7);k=r.get(2);q=np.zeros(nn,np.int32);j=-1
        while r.get(1):
            j+=(r.unary()<<k)+r.get(k)+1;assert j<nn;z=r.eg()+1;q[j]=z*(-1 if r.get(1) else 1)
        out.append((m,par,p,s,k,q,r.bits[start:r.pos].copy()));pm,pp=m,par
    assert not r.bits[r.pos:].any() and len(r.bits)-r.pos<8
    return (n,frame,grid,K,L,b),out

def bits_res(q,s,k):
    w=Writer();w.put(s,7);w.put(k,2);prev=-1
    for j in np.flatnonzero(q):
        v=q[j];gap=j-prev-1;prev=j;w.put(1,1);w.unary(gap>>k);w.put(gap&((1<<k)-1),k);w.eg(abs(v)-1);w.put(int(v<0),1)
    w.put(0,1);return np.asarray(w.bits,np.uint8)

def run(test,indir,outdir):
    start=time.time();indir=Path(indir);out=Path(outdir);out.mkdir(exist_ok=True,parents=True);data=(indir/'book.bin').read_bytes();src=indir/'morph.lp42';x=np.load(test)['target'];hdr,frames=read_frames(src,data);n,frame,grid,K,L,b=hdr;assert n==len(x)
    (out/'book.bin').write_bytes(data);(out/'dds.bin').write_bytes((indir/'dds.bin').read_bytes());a=[];pm=0;pp=();headers=0;baseline=0
    for i,(m,par,p,s,k,q,oldbits) in enumerate(frames):
        c=dct(x[i*frame:i*frame+len(p)]-p,norm='ortho');e0=float(np.sum((c-q*SCALES[s])**2));baseline+=e0;headers+=sum(n for _,n in fields(m,par,pm,pp,grid,K,frame,steps(grid)));pm,pp=m,par
        er,qs,ss,ks=variants(c,s,k);best=e0;cc=[(len(oldbits),e0,oldbits)]
        # Pareto envelope, with exact original residual as a candidate.
        best=1e100
        for z in range(len(er)):
            if ss[z]>=0 and er[z]<best:
                best=er[z];bits=bits_res(qs[z],int(ss[z]),int(ks[z]));assert len(bits)==z;cc.append((z,float(er[z]),bits))
        a.append(cc)
        if i%300==299:print('TRELLIS',i+1,round(time.time()-start,1),flush=True)
    budget=(int(n*1000/FS)-struct.calcsize(HEADER42))*8-headers
    # Vectorized Lagrangian allocation; include baseline explicitly.
    bs=[np.array([v[0] for v in c]) for c in a];es=[np.array([v[1] for v in c]) for c in a]
    lo=0.;hi=max(1.,max(e.max() for e in es));ix=None
    for _ in range(40):
        l=(lo+hi)/2;jj=[int(np.argmin(e+l*b)) for b,e in zip(bs,es)];sz=sum(b[j] for b,j in zip(bs,jj))
        if sz<=budget:hi=l;ix=jj;used=sz
        else:lo=l
    assert ix is not None
    rem=budget-used;choices=[]
    for i,j in enumerate(ix):
        db=bs[i]-bs[i][j];dg=es[i][j]-es[i]
        for k in np.flatnonzero((db>0)&(db<=rem)&(dg>0)):choices.append((dg[k]/db[k],i,int(k),int(db[k]),j))
    for _,i,k,db,j in sorted(choices,reverse=True):
        if db<=rem and ix[i]==j:ix[i]=k;rem-=db
    sel=[(f[0],f[1],c[j]) for f,c,j in zip(frames,a,ix)];path=out/'morph.lp42';nb,cc=write(path,sel,*hdr);assert nb==budget-rem+headers;z,m,nb2=decode(path,data);assert nb==nb2;err=np.dot(x-z,x-z);assert np.isclose(err,sum(c[2][1] for c in sel),rtol=1e-6);np.save(out/'morph.npy',z);assert path.stat().st_size<=int(n*1000/FS)
    result=dict(profile='trellis',frame=frame,grid=grid,K=K,L=L,book_bits=b,bytes=path.stat().st_size,kbps=path.stat().st_size*8*FS/n/1000,book_bytes=len(data),dds_table_bytes=grid*2,mode_counts=np.bincount(m,minlength=4).tolist(),counts=cc,pcm_snr=float(10*np.log10(np.dot(x,x)/err)),baseline_pcm_snr=float(10*np.log10(np.dot(x,x)/baseline)),seconds=time.time()-start);(out/'results.json').write_text(json.dumps([result],indent=2));print('RESULT',result,flush=True)
if __name__=='__main__':run(*sys.argv[1:])
