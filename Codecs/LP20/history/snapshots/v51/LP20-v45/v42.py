#!/usr/bin/env python3
"""LP20 v42: PC-only sample prediction, predictive parameters, packed waveform tables.
Four modes: transform, single, independent morph, phase-shared morph.
Exact predictive parameter coding uses previous end phase; does not enforce continuity.
All bitstream bytes counted; separate static table budget. No Z80 implementation.
"""
from hybrid import *
from packed import optimize, DEAD
from collections import Counter
import argparse
HEADER42='<4sIHHBBB'

def pack_book(book,b):
    lim=(1<<(b-1))-1
    q=np.clip(np.rint(book.astype(float)*lim/127),-lim,lim).astype(int)
    w=Writer()
    for v in q.flat:w.put(int(v)+lim,b)
    return w.bytes()
def unpack_book(data,K,L,b):
    r=Reader(data);lim=(1<<(b-1))-1
    q=np.array([r.get(b)-lim for _ in range(K*L)])
    assert np.all(abs(q)<=lim) and len(r.bits)-r.pos<8 and not r.bits[r.pos:].any()
    return np.rint(q*127/lim).astype(np.int8).reshape(K,L)

def fixed_fit(x,weight,step,wt,phase):
    n=len(x);v=(np.arange(n,dtype=np.int64)*int(step)+phase*256)&65535;j=v>>8;fr=(v&255)/256.
    w=wt[:,j]*(1-fr)+wt[:,(j+1)%P]*fr
    ww=w*weight;dot=ww@x;en=np.maximum(np.sum(ww*ww,axis=1),1e-12);g=dot/en
    gc=np.clip(np.rint(np.log2(np.maximum(abs(g),GAINS[0])/GAINS[0])*12),0,127).astype(int)
    gain=GAINS[gc]*np.sign(g);i=np.argmax(2*gain*dot-gain*gain*en);code=int(gc[i])+128*int(g[i]<0)
    return (int(i),int(phase),code),wave(wt[i],step,phase,code,n)

def preds(x,f,wt,fft,grid):
    p=[(0,(),np.zeros(len(x)))]
    if not f:return p
    v=pred(x,f,wt,fft,grid);p+=v
    _,par,y=v[0];pi,i,ph,g=par;st=steps(grid)[pi];a=1-np.linspace(0,1,len(x));b=1-a;best=None
    for shift in (0,-2,2,-5,5):
        pp=(ph+shift)%256;yb=wave(wt[i],st,pp,g,len(x));ya=yb.copy()
        for _ in range(2):pa,ya=fixed_fit(x-b*yb,a,st,wt,pp);pb,yb=fixed_fit(x-a*ya,b,st,wt,pp)
        z=a*ya+b*yb;e=np.dot(x-z,x-z)
        if best is None or e<best[0]:best=(e,(3,(pi,*pa,*pb),z))
    p.append(best[1]);return p

def delta(v,base,bits,width,circular=False):
    d=v-base
    if circular:d=(d+128)%256-128
    maxd=(1<<(width-1))-1
    if abs(d)<=maxd:return (d+maxd,width),
    return ((1<<width)-1,width),(v,bits)
def repeat(v,base,bits):return ((0,1),) if v==base else ((1,1),(v,bits))
def fields(m,p,pm,pp,grid,K,prev_n,st):
    nb=int(math.log2(grid));kb=int(math.log2(K));out=[(m,2)]
    if not m:return out
    if pm:
        end=(pp[-2]*256+int(st[pp[0]])*prev_n)&65535
        pphase=((end+128)//256)%256
        out+=delta(p[0],pp[0],nb,4)
        out+=repeat(p[1],pp[-3],kb)
        out+=delta(p[2],pphase,8,4,True)
        out+=delta(p[3],pp[-1],8,4)
    else:out += [(p[0],nb),(p[1],kb),(p[2],8),(p[3],8)]
    if m>=2:
        out+=repeat(p[4],p[1],kb)
        if m==2:out+=delta(p[5],p[2],8,4,True)
        else:assert p[5]==p[2]
        out+=delta(p[6],p[3],8,4)
    return out

def read_delta(r,base,bits,width,circular=False):
    v=r.get(width);md=(1<<(width-1))-1
    if v==(1<<width)-1:return r.get(bits)
    z=base+v-md
    if circular:z%=256
    assert 0<=z<1<<bits
    return z

def read_repeat(r,base,bits):return r.get(bits) if r.get(1) else base

def write_res(c,s,k,dead):
    w=Writer();w.put(max(s,0),7);w.put(k,2)
    q=np.zeros(len(c),int) if s==-2 else np.where(abs(c/SCALES[s])>=DEAD[dead],np.rint(c/SCALES[s]),0).astype(int)
    prev=-1
    for j in np.flatnonzero(q):
        v=q[j];gap=j-prev-1;prev=j;w.put(1,1);w.unary(gap>>k);w.put(gap&((1<<k)-1),k);w.eg(abs(v)-1);w.put(int(v<0),1)
    w.put(0,1);return np.asarray(w.bits,np.uint8)

def residuals(x,p,maxbits):
    c=dct(x-p,norm='ortho');bs,bk,bd,err=optimize(c,maxbits,SCALES,MAGBITS);out=[];last=None
    for b in range(10,maxbits+1):
        if bs[b]==-1:continue
        key=(int(bs[b]),int(bk[b]),int(bd[b]))
        if key==last:continue
        last=key;bits=write_res(c,*key);assert len(bits)<=b;out.append((len(bits),float(err[b]),bits))
    return out

def allocate(ca,budget,grid,K,frame,st,allowed):
    # Every frame has a fixed predictor for each mode; transition syntax cost depends
    # on the previous selected mode but not residual choices. Viterbi over modes.
    arr=[];hs=[];prev={0:()};oldm=[0]
    for a in ca:
        cur={m:p for m,p,_ in a if m in allowed};mode=list(cur)
        cost=np.array([[sum(n for _,n in fields(m,cur[m],pm,prev[pm],grid,K,frame,st)) for m in mode] for pm in oldm],np.int16)
        arr.append([(m,p,r,np.array([c[0] for c in r]),np.array([c[1] for c in r])) for m,p,r in a if m in allowed]);hs.append(cost);prev=cur;oldm=mode
    def search(lam):
        cost=np.array([0.]);sz=np.array([0]);back=[];ix=[]
        for a,h in zip(arr,hs):
            js=np.array([np.argmin(e+lam*b) for _,_,_,b,e in a]);rb=np.array([a[k][3][j] for k,j in enumerate(js)]);re=np.array([a[k][4][j] for k,j in enumerate(js)])
            z=cost[:,None]+lam*h;pr=np.argmin(z,axis=0);cost=z[pr,np.arange(len(a))]+re+lam*rb;sz=sz[pr]+h[pr,np.arange(len(a))]+rb;back.append(pr);ix.append(js)
        k=int(np.argmin(cost));n=int(sz[k]);sel=[]
        for pr,js in zip(back[::-1],ix[::-1]):sel.append((k,int(js[k])));k=int(pr[k])
        return n,sel[::-1]
    lo=0.;hi=max(1.,max(max(e.max() for _,_,_,_,e in a) for a in arr));best=None
    for _ in range(33):
        mid=(lo+hi)/2;n,sel=search(mid)
        if n<=budget:hi=mid;best=sel;size=n
        else:lo=mid
    assert best is not None
    # Remaining budget: improve residual at fixed chosen predictor, exact bytes.
    rem=budget-size;choices=[]
    for i,(k,j) in enumerate(best):
        a=arr[i][k];b,e=a[3:];db=b-b[j];dg=e[j]-e
        for q in np.flatnonzero((db>0)&(db<=rem)&(dg>0)):choices.append((dg[q]/db[q],dg[q],i,int(q),int(db[q]),j))
    for _,_,i,q,db,j in sorted(choices,reverse=True):
        if db<=rem and best[i][1]==j:best[i]=(best[i][0],q);rem-=db
    sel=[]
    for i,(k,j) in enumerate(best):
        m,p,r,*_=arr[i][k];sel.append((m,p,r[j]))
    return sel,budget-rem

def write(path,sel,n,frame,grid,K,L,b):
    w=Writer();pm=0;pp=();st=steps(grid);cc=Counter()
    for m,p,r in sel:
        fs=fields(m,p,pm,pp,grid,K,frame,st);header=sum(n for _,n in fs)
        cc['headers']+=header;cc['residual']+=r[0];cc['sample_headers']+=header-2 if m else 0
        if m and pm:
            cc['phase_short']+=int(abs((p[2]-((pp[-2]*256+int(st[pp[0]])*frame+128)//256)+128)%256-128)<=7)
            cc['sample_transitions']+=1
        for v,k in fs:w.put(v,k)
        w.bits.extend(r[2]);pm,pp=m,p
    Path(path).write_bytes(struct.pack(HEADER42,b'LP42',n,frame,grid,K,L,b)+w.bytes());return len(w.bits),dict(cc)

def decode(path,bookdata):
    raw=Path(path).read_bytes();magic,n,frame,grid,K,L,b=struct.unpack_from(HEADER42,raw);assert magic==b'LP42';book=unpack_book(bookdata,K,L,b);wt=wave_table(book);st=steps(grid);r=Reader(raw[struct.calcsize(HEADER42):]);pm=0;pp=();out=[];modes=[];kb=int(math.log2(K));nb=int(math.log2(grid))
    for pos in range(0,n,frame):
        m=r.get(2);nn=min(frame,n-pos);p=np.zeros(nn);par=()
        if m:
            if pm:
                pi=read_delta(r,pp[0],nb,4);i=read_repeat(r,pp[-3],kb);ph=read_delta(r,((pp[-2]*256+int(st[pp[0]])*frame+128)//256)%256,8,4,True);g=read_delta(r,pp[-1],8,4)
            else:pi=r.get(nb);i=r.get(kb);ph=r.get(8);g=r.get(8)
            par=(pi,i,ph,g);p=wave(wt[i],st[pi],ph,g,nn)
            if m>=2:
                j=read_repeat(r,i,kb);ph2=read_delta(r,ph,8,4,True) if m==2 else ph;g2=read_delta(r,g,8,4);par+= (j,ph2,g2);a=np.linspace(0,1,nn);p=p*(1-a)+wave(wt[j],st[pi],ph2,g2,nn)*a
        s=r.get(7);k=r.get(2);q=np.zeros(nn);j=-1
        while r.get(1):
            j+=(r.unary()<<k)+r.get(k)+1;assert j<nn;z=r.eg()+1;q[j]=z*(-1 if r.get(1) else 1)
        out.append(p+idct(q*SCALES[s],norm='ortho'));modes.append(m);pm,pp=m,par
    assert not r.bits[r.pos:].any() and len(r.bits)-r.pos<8
    return np.concatenate(out),np.array(modes),r.pos

def run(clip,test_path,book_path,out,b,grid,frame,bps=8000):
    out=Path(out);out.mkdir(exist_ok=True,parents=True);x=np.load(test_path)['target'];K=32;L=64;bookdata=pack_book(np.fromfile(book_path,np.int8).reshape(K,L),b);book=unpack_book(bookdata,K,L,b);(out/'book.bin').write_bytes(bookdata);wt=wave_table(book);fft=[np.fft.rfft(w,axis=1) for w in (wt,wt*wt,wt*np.roll(wt,-1,axis=1))];st=steps(grid);st.astype('<u2').tofile(out/'dds.bin');p0=np.arange(0,len(x),frame);f0=pitch_analysis(x,np.minimum(p0+frame//2,len(x)-1));a=[];start=time.time();mb=max(320,int(frame*2.5))
    for k,(p,(fr,score)) in enumerate(zip(p0,f0)):
        z=x[p:p+frame];a.append([(m,par,residuals(z,y,mb)) for m,par,y in preds(z,fr,wt,fft,grid)])
        if k%300==299:print(clip,b,frame,k+1,'s',round(time.time()-start,1),flush=True)
    budget=(int(len(x)*bps/(8*FS))-struct.calcsize(HEADER42))*8;rows=[]
    for tag,modes in [('sample',(0,1)),('morph',(0,1,2,3))]:
        sel,sz=allocate(a,budget,grid,K,frame,st,modes);path=out/(tag+'.lp42');n,cc=write(path,sel,len(x),frame,grid,K,L,b);assert n==sz;z,m,nb=decode(path,bookdata);assert n==nb and np.isclose(np.dot(x-z,x-z),sum(c[2][1] for c in sel),rtol=1e-6);np.save(out/(tag+'.npy'),z);met=dict(clip=clip,profile=tag,frame=frame,grid=grid,K=K,L=L,book_bits=b,bytes=path.stat().st_size,kbps=path.stat().st_size*8*FS/len(x)/1000,book_bytes=len(bookdata),dds_table_bytes=grid*2,mode_counts=np.bincount(m,minlength=4).tolist(),counts=cc,pcm_snr=float(10*np.log10(np.dot(x,x)/np.dot(x-z,x-z))));assert met['kbps']<=bps/1000;rows.append(met);print('RESULT',met,flush=True)
    (out/'results.json').write_text(json.dumps(rows,indent=2))
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('clip');ap.add_argument('test');ap.add_argument('book');ap.add_argument('out');ap.add_argument('bits',type=int);ap.add_argument('grid',type=int);ap.add_argument('frame',type=int);ap.add_argument('--bps',type=int,default=8000);a=ap.parse_args();run(a.clip,a.test,a.book,a.out,a.bits,a.grid,a.frame,a.bps)
