#!/usr/bin/env python3
"""Alternating joint predictor fit and residual search; control uses same candidate pool."""
from adaptive45 import *

def fit_alternating(t,nom,m,par,p,s,q,wt,fft,st,lv):
    r=idct(q*SCALES[s],norm='ortho');z=p+r;tar=t-r-.75*(quant(z,lv)-z);a=np.linspace(0,1,len(t));one=np.ones(len(t));c=[];pi=par[0]
    for k in range(max(0,pi-1),min(len(st),pi+2)):
        if m==1:
            pa,ya=fit(tar,one,st[k],wt,fft);c.append((1,(k,*pa),ya))
        else:
            _,i,ph,g,j,ph2,g2=par;ya=wave(wt[i],st[k],ph,g,len(t));yb=wave(wt[j],st[k],ph2,g2,len(t));pa=(i,ph,g);pb=(j,ph2,g2)
            for _ in range(2):
                pa,ya=fit(tar-a*yb,1-a,st[k],wt,fft);pb,yb=fit(tar-(1-a)*ya,a,st[k],wt,fft)
            c.append((2,(k,*pa,*pb),(1-a)*ya+a*yb))
    def err(v):
        e=quant(v[2]+r,lv)-t
        e=sosfiltfilt(FILT,e) if len(e)>24 else e
        return e@e
    c.sort(key=err);return c[:2]

def main(clip):
    out=ROOT/clip;base=BASE/'input'/clip;h,ln,blocks=pickle.load(open(out/'candidates.pkl','rb'));book=(base/'book.bin').read_bytes();d=dict(np.load(base/'model.npz'));meta=json.loads((base/'decoder.json').read_text());x=d['target'];ref=wavfile.read(base/'reference.wav')[1];lv=np.unique(levels(d,meta)[1]);n,_,grid,K,L,b=h;wt=wave_table(unpack_book(book,K,L,b));fft=[np.fft.rfft(w,axis=1) for w in (wt,wt*wt,wt*np.roll(wt,-1,axis=1))];st=steps(grid);th=.065*np.max(abs(x));rows=[];visited=set();added=0;start=time.time()
    # Refit only selected nonzero predictor frames, not individual recording books.
    for tag in ('joint256','adaptive'):
        path=out/(tag+('.lp4s' if tag=='joint256' else '.lp4v'));_,frames,_=decode_v(path,book);pos=0
        for nominal,m,par,p,s,q in frames:
            nn=len(q);t=x[pos:pos+nn];key=(pos,nominal,m,par,s,q.tobytes());i=pos//128;pos+=nn
            if not m or key in visited:continue
            visited.add(key)
            for mm,pp,prediction in fit_alternating(t,nominal,m,par,p,s,q,wt,fft,st,lv):
                if (mm,pp)==(m,par):continue
                for c in candidate_search(t,prediction,ln,lv,th,s,(s,q)):
                    blocks[i].append((nominal,mm,pp,prediction,*c));added+=1
            if len(visited)%100==0:print('REFIT',clip,len(visited),added,round(time.time()-start,1),flush=True)
    for tag,variable,hf,pk in [('joint256-refit',False,0.,0.),('adaptive-refit',True,0.,0.),('adaptive-refit-peak',True,.13,3.)]:
        prepared=prepare(h,blocks,variable);frames,used,budget=alloc(h,prepared,ln,6,variable,hf,pk);path=out/(tag+('.lp4v' if variable else '.lp4s'));bits=write_v(path,h,frames,ln.tolist(),variable);assert bits==used;assert path.stat().st_size<=int(n*6000/(8*FS));y,dec,b2=decode_v(path,book);assert bits==b2 and np.array_equal(y,np.concatenate([p+idct(q*SCALES[s],norm='ortho') for _,_,_,p,s,q in frames]));wav=render(y,d,meta);wavfile.write(out/(tag+'.wav'),48000,wav);row=dict(clip=clip,profile=tag,bytes=path.stat().st_size,kbps=path.stat().st_size*8*FS/n/1000,lengths=dict(Counter(f[0] for f in frames)),modes=dict(Counter(f[1] for f in frames)),refitted=len(visited),added=added,**metrics(ref,wav));rows.append(row);(out/'refit.json').write_text(json.dumps(rows,indent=2));print('RESULT',row,flush=True)
if __name__=='__main__':main(sys.argv[1])
