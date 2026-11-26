#!/usr/bin/env python3
"""LP4V: variable blocks / joint predictor and residual selection; PC only."""
from rd44 import *
from collections import Counter
import pickle
ROOT=Path(__file__).resolve().parent
BASE=Path(os.environ.get('LP20_V44',ROOT.parent/'LP20-v44'))
G=2;M=12;TYP=3

def length_fields(n):return (0,1) if n==256 else (2 if n==128 else 3,2)

def write_v(path,h,frames,lens,variable):
    n,_,grid,K,L,b=h;table=Writer();w=Writer();st=steps(grid);enc=[codes(l) for l in lens];pm=0;pp=();ps=None;prev_n=0;pos=0
    for ln in lens:
        for v in ln:table.put(v,4)
    for nominal,m,par,p,s,q in frames:
        nn=len(q);assert nn==min(n-pos,nominal)
        if variable:w.put(*length_fields(nominal))
        else:assert nominal==256
        for v,k in fields(m,par,pm,pp,grid,K,prev_n,st):w.put(v,k)
        for v,k in (((s,7),) if ps is None else delta(s,ps,7,4)):w.put(v,k)
        nz=np.flatnonzero(q);cnt=len(nz);w.unary(cnt>>5);w.put(cnt&31,5);prev=-1
        for j in nz:
            j=int(j);gap=j-prev-1;v=int(q[j]);mag=abs(v)
            w.put(*enc[ctx(prev,cnt,s,TYP)][min(gap,G)*M+min(mag,M)-1])
            if gap>=G:w.eg(gap-G)
            if mag>=M:w.eg(mag-M)
            w.put(int(v<0),1);prev=j
        pm,pp,ps,prev_n=m,par,s,nn;pos+=nn
    assert pos==n
    path.write_bytes(struct.pack(HEADER42,b'LP4V' if variable else b'LP4S',n,256,grid,K,L,b)+bytes([G,M,TYP])+table.bytes()+w.bytes());return len(w.bits)

def decode_v(path,book):
    raw=path.read_bytes();magic,n,frame,grid,K,L,b=struct.unpack_from(HEADER42,raw);assert magic in (b'LP4V',b'LP4S');variable=magic==b'LP4V';o=struct.calcsize(HEADER42);gg,mm,typ=raw[o:o+3];assert (gg,mm,typ)==(G,M,TYP);o+=3;tb=(nc(typ)*(G+1)*M+1)//2;tr=Reader(raw[o:o+tb]);lens=[[tr.get(4) for _ in range((G+1)*M)] for _ in range(nc(typ))];dec=[{v:k for k,v in codes(l).items()} for l in lens];r=Reader(raw[o+tb:]);wt=wave_table(unpack_book(book,K,L,b));st=steps(grid);pm=0;pp=();ps=None;prev_n=0;pos=0;records=[];out=[];nb=int(math.log2(grid));kb=int(math.log2(K))
    while pos<n:
        nominal=(128 if r.get(1)==0 else 512) if variable and r.get(1) else 256;nn=min(n-pos,nominal);m=r.get(2);par=();p=np.zeros(nn)
        if m:
            if pm:
                pi=read_delta(r,pp[0],nb,4);i=read_repeat(r,pp[-3],kb);ph=read_delta(r,((pp[-2]*256+int(st[pp[0]])*prev_n+128)//256)%256,8,4,True);g=read_delta(r,pp[-1],8,4)
            else:pi=r.get(nb);i=r.get(kb);ph=r.get(8);g=r.get(8)
            par=(pi,i,ph,g);p=wave(wt[i],st[pi],ph,g,nn)
            if m>=2:
                j=read_repeat(r,i,kb);ph2=read_delta(r,ph,8,4,True) if m==2 else ph;g2=read_delta(r,g,8,4);par+=(j,ph2,g2);a=np.linspace(0,1,nn);p=p*(1-a)+wave(wt[j],st[pi],ph2,g2,nn)*a
        s=r.get(7) if ps is None else read_delta(r,ps,7,4);cnt=(r.unary()<<5)+r.get(5);assert cnt<=nn;q=np.zeros(nn,np.int32);prev=-1
        for _ in range(cnt):
            sym=read_symbol(r,dec[ctx(prev,cnt,s,TYP)]);gap,mag=divmod(sym,M);mag+=1
            if gap==G:gap+=r.eg()
            if mag==M:mag+=r.eg()
            j=prev+gap+1;assert j<nn;q[j]=-mag if r.get(1) else mag;prev=j
        out.append(p+idct(q*SCALES[s],norm='ortho'));records.append((nominal,m,par,p,s,q));pm,pp,ps,prev_n=m,par,s,nn;pos+=nn
    assert not r.bits[r.pos:].any() and len(r.bits)-r.pos<8
    return np.concatenate(out),records,r.pos

def candidate_search(x,p,ln,lv,threshold,base_s,seed=None):
    n=len(x);freq=np.arange(n)/n*FS/2;W=np.maximum(1/(1+(freq/3500)**10)**2,.05)*np.sinc(freq/FS)**2;c0=dct(x-p,norm='ortho');out={};seen=set()
    def add(q,s):
        key=(s,q.tobytes());
        if key in seen:return
        seen.add(key);z=p+idct(q*SCALES[s],norm='ortho');e=sosfiltfilt(FILT,quant(z,lv)-x) if n>24 else quant(z,lv)-x;cost=float(e@e);peak=float(np.max(abs(e)));pen=float(np.sum(np.maximum(abs(e)-threshold,0)**2));hf=float(np.dot(np.diff(e),np.diff(e)));bits=int(rbits(q,ln,G,M));row=(bits,cost,pen,hf,peak,s,q)
        for tag,v in [(0,cost),(1,cost+3*pen+.15*hf)]:
            k=(bits,s,tag)
            if k not in out or v<out[k][0]:out[k]=(v,row)
    if seed is not None:add(seed[1],seed[0])
    add(np.zeros(n,np.int32),int(base_s));ss=sorted(set(np.clip([base_s-6,base_s-3,base_s,base_s+3,base_s+6],0,127)));pre=[]
    for s in ss:
        sc=SCALES[s]
        for dz in (.55,1.,1.6):
            q=np.where(abs(c0)>=sc*dz,np.rint(c0/sc),0).astype(np.int32);bits=int(rbits(q,ln,G,M));err=float(np.sum(W*(c0-q*sc)**2));pre.append((bits,err,s));add(q,s)
    lams=np.array([.07,.25,.8,2.5])*SCALES[base_s]**2;scales=sorted(set(min(pre,key=lambda z:z[1]+la*z[0])[2] for la in lams)|{int(base_s)})
    for s in scales:
        for f in (.12,.5,1.8):add(choose(c0,SCALES[s],SCALES[s]**2*f,ln,G,M,int(n>=256),W),s)
    vals=[v[1] for v in out.values()]
    for la in lams[1:]:
        a=min(vals,key=lambda z:z[1]+la*z[0]);s=a[5];q=a[6];z=p+idct(q*SCALES[s],norm='ortho');cf=dct(x-p-.85*(quant(z,lv)-z),norm='ortho');add(choose(cf,SCALES[s],la,ln,G,M,int(np.count_nonzero(q)>=36),W),s)
    vals=[v[1] for v in out.values()];keep={}
    for la in np.r_[0,lams/3,lams,lams*3,1e5]:
        for w in (0,.12):
            a=min(vals,key=lambda z:z[1]+w*z[3]+3*w*z[2]+la*z[0]);keep[(a[5],a[6].tobytes())]=a
    if seed is not None:
        a=next((z for z in vals if z[5]==seed[0] and np.array_equal(z[6],seed[1])),None)
        if a is not None:keep[(a[5],a[6].tobytes())]=a
    return list(keep.values())

def gen(clip):
    base=BASE/'input'/clip;other=BASE/'input'/('second' if clip=='first' else 'first');book=(base/'book.bin').read_bytes();h,old=read_frames(base/'morph.lp42',book);_,tr=read_frames(other/'morph.lp42',(other/'book.bin').read_bytes());ln=np.asarray(build(pairs(tr),G,M,TYP),np.int32)
    _,_,_,refrec=decode_s(BASE/clip/'6k-SNR.lp4s',book);d=dict(np.load(base/'model.npz'));meta=json.loads((base/'decoder.json').read_text());x=d['target'];lv=np.unique(levels(d,meta)[1]);n,_,grid,K,L,b=h;wt=wave_table(unpack_book(book,K,L,b));fft=[np.fft.rfft(w,axis=1) for w in (wt,wt*wt,wt*np.roll(wt,-1,axis=1))];th=.065*np.max(abs(x));N=(n+127)//128
    centers=sorted(set(min(n-1,i*128+min(k,n-i*128)//2) for i in range(N) for k in (128,256,512) if k==128 or (i%(k//128)==0 and (n-i*128>=k or k==256))));pitch=dict(zip(centers,pitch_analysis(x,centers)));blocks=[];start=time.time()
    for i in range(N):
        pos=i*128;xs=[]
        for k in (128,256,512):
            if k!=128 and (i%(k//128) or (n-pos<k and k!=256)):continue
            nn=min(k,n-pos);t=x[pos:pos+nn];f=pitch[min(n-1,pos+nn//2)][0];pr=[(0,(),np.zeros(nn))];seed=None
            if k==256:
                m,par,s,q=refrec[i//2];p=old[i//2][2];assert (m,par)==old[i//2][:2];seed=(s,q)
                if m:pr.append((m,par,p))
            if f:
                for m,par,p in pred(t,f,wt,fft,grid):
                    if not any((m,par)==(z[0],z[1]) for z in pr):pr.append((m,par,p))
            bscale=int(refrec[min(i//2,len(refrec)-1)][2])
            for m,par,p in pr:
                sd=seed if k==256 and (m,par)==tuple(refrec[i//2][:2]) else None
                for a in candidate_search(t,p,ln,lv,th,bscale,sd):xs.append((k,m,par,p,*a))
        blocks.append(xs)
        if i%200==199:print('GEN',clip,i+1,N,round(time.time()-start,1),flush=True)
    return h,ln,blocks

def prepare(h,blocks,variable):
    n,_,grid,K,L,b=h;N=len(blocks);st=steps(grid);nodes=[[] for _ in range(N+1)];groups=[];rows=[];headers=[];ids={};hid=[]
    for i,ls in enumerate(blocks):
        cc=[]
        for a in ls:
            k,m,par,p=a[:4]
            if not variable and (k!=256 or i%2):continue
            ix=len(rows);rows.append(a);nodes[min(N,i+k//128)].append(ix);cc.append(ix);key=(m,par,len(p))
            if key not in ids:ids[key]=len(headers);headers.append(key)
            hid.append(ids[key])
        groups.append(cc)
    ts=[];hs=[];prevhs=[];gr=[]
    for i,cc in enumerate(groups):
        cur=list(dict.fromkeys(hid[ix] for ix in cc));prev=list(dict.fromkeys(hid[ix] for ix in nodes[i]))
        if i==0:prev=[-1]
        cm={v:j for j,v in enumerate(cur)};pm={v:j for j,v in enumerate(prev)};t=np.empty((len(prev),len(cur)),np.int16)
        for r,ph in enumerate(prev):
            om,op,on=(0,(),0) if ph<0 else headers[ph]
            for c,ch in enumerate(cur):
                m,par,_=headers[ch];t[r,c]=sum(w for _,w in fields(m,par,om,op,grid,K,on,st))
        ts.append(t);hs.append(np.array([cm[hid[ix]] for ix in cc],np.int32));prevhs.append(pm);gr.append(np.array(cc,np.int32))
    return rows,nodes,gr,np.array(hid),ts,hs,prevhs

def alloc(h,prepared,ln,rate,variable,hfweight=0.,peakweight=0.,beam=8,iterations=34):
    rows,nodes,gr,hid,ts,hs,prevhs=prepared;n=h[0];budget=int(n*rate*1000/(8*FS))*8-(struct.calcsize(HEADER42)+3+(ln.size+1)//2)*8;bs=np.array([a[4]+(length_fields(a[0])[1] if variable else 0) for a in rows]);es=np.array([a[5]+peakweight*a[6]+hfweight*a[7] for a in rows]);sc=np.array([a[9] for a in rows])
    def solve(lam):
        cost=np.full(len(rows),np.inf);nb=np.zeros(len(rows),np.int32);parent=np.full(len(rows),-1,np.int32)
        for i,cc in enumerate(gr):
            if not len(cc):continue
            if i==0:
                zz=ts[i][0,hs[i]]+7+bs[cc];cost[cc]=es[cc]+lam*zz;nb[cc]=zz;continue
            pr=np.asarray(nodes[i],np.int32);pr=pr[np.isfinite(cost[pr])]
            if not len(pr):continue
            order=pr[np.argsort(cost[pr])];keep=[];seen=set()
            for j in order:
                key=(hid[j],sc[j])
                if key not in seen:seen.add(key);keep.append(j)
                if len(keep)>=beam:break
            pr=np.asarray(keep,np.int32);pidx=np.array([prevhs[i][hid[j]] for j in pr]);delta_b=np.where(abs(sc[pr,None]-sc[cc][None,:])<=7,4,11);cb=ts[i][pidx[:,None],hs[i][None,:]]+delta_b+bs[cc][None,:];z=cost[pr,None]+lam*cb;ix=np.argmin(z,axis=0);cost[cc]=z[ix,np.arange(len(cc))]+es[cc];nb[cc]=nb[pr[ix]]+cb[ix,np.arange(len(cc))];parent[cc]=pr[ix]
        last=np.array(nodes[-1]);j=int(last[np.argmin(cost[last])]);bits=int(nb[j]);path=[]
        while j>=0:path.append(j);j=int(parent[j])
        return path[::-1],bits
    lo=0.;hi=max(1.,max(es));best=None
    for _ in range(iterations):
        la=(lo+hi)/2;p,b=solve(la)
        if b<=budget:hi=la;best=p;used=b
        else:lo=la
    assert best is not None
    return [(a[0],a[1],a[2],a[3],a[9],a[10]) for a in (rows[j] for j in best)],used,budget

def main(clip):
    out=ROOT/clip;out.mkdir(exist_ok=True);base=BASE/'input'/clip;book=(base/'book.bin').read_bytes();cache=out/'candidates.pkl'
    if cache.exists():h,ln,blocks=pickle.load(open(cache,'rb'))
    else:h,ln,blocks=gen(clip);pickle.dump((h,ln,blocks),open(cache,'wb'),protocol=5)
    print('READY',clip,len(blocks),sum(map(len,blocks)),flush=True);d=dict(np.load(base/'model.npz'));meta=json.loads((base/'decoder.json').read_text());ref=wavfile.read(base/'reference.wav')[1];res=[]
    for tag,variable,rate,hf,pk in [('joint256',False,6,0,0),('adaptive',True,6,0,0),('adaptive-peak',True,6,.13,3),('adaptive-58',True,5.8,0,0)]:
        pp=prepare(h,blocks,variable);frames,used,budget=alloc(h,pp,ln,rate,variable,hf,pk,iterations=22);path=out/(tag+('.lp4v' if variable else '.lp4s'));bits=write_v(path,h,frames,ln.tolist(),variable);assert used==bits,(used,bits);assert path.stat().st_size<=int(h[0]*rate*1000/(8*FS));y,dec,b2=decode_v(path,book);expected=np.concatenate([p+idct(q*SCALES[s],norm='ortho') for _,_,_,p,s,q in frames]);assert bits==b2 and np.array_equal(y,expected);assert all((a[:3]+(a[4],))==(b[:3]+(b[4],)) and np.array_equal(a[5],b[5]) for a,b in zip(frames,dec))
        if not variable:assert np.array_equal(decode_s(path,book)[0],y)
        wav=render(y,d,meta);wavfile.write(out/(tag+'.wav'),48000,wav);row=dict(clip=clip,profile=tag,bytes=path.stat().st_size,kbps=path.stat().st_size*8*FS/h[0]/1000,lengths=dict(Counter(f[0] for f in frames)),modes=dict(Counter(f[1] for f in frames)),**metrics(ref,wav));res.append(row);(out/'results.json').write_text(json.dumps(res,indent=2));print('RESULT',row,flush=True)
if __name__=='__main__':main(sys.argv[1])
