"""TinyLPC v4: perceptual iterative analysis by synthesis.
Scores: STOI intelligibility + 24-band spectral envelope + temporal amplitude, pitch error.
Search only parameters that exist in the 5-byte/frame ATtiny13A bitstream.
"""
import time,os
import numpy as np
from scipy.signal import correlate,find_peaks
from scipy.ndimage import median_filter
from spectral_objective import evaluate,x,N,H,FS,metrics
from model_exact import synth_exact

rng=np.random.default_rng(13)
z=np.load('joint_epoch2.npz')
K=z['K'].astype(np.int64).copy()
P=z['P'].astype(np.int64).copy()
E=z['E'].astype(np.int64).copy()

# High-confidence fundamental-period reference from ORIGINAL SOURCE (pre-emphasized)
P_TARGET=np.zeros(N,dtype=int);P_WEIGHT=np.zeros(N,float)
P_CANDS=[]
for fi in range(N):
    center=fi*H+H//2
    s=x[max(0,center-285):min(len(x),center+285)]
    if len(s)<300:s=np.pad(s,(0,300-len(s)))
    s=s-np.mean(s); s=s[1:]-0.88*s[:-1]
    ac=correlate(s,s,'full',method='fft')[len(s)-1:]
    e=np.array([np.sqrt(np.sum(s[p:]**2)*np.sum(s[:-p]**2))+1e-9 for p in range(1,95)])
    ac=ac[1:95]/e;ac[:15]=0
    peaks,_=find_peaks(ac[15:90]);peaks=peaks+15
    ranked=sorted([(float(ac[p]),int(p)) for p in peaks],reverse=True)
    best=ranked[0][0] if ranked else 0
    # original pitch must be strongly periodic before enforcing f0 match
    rms=np.sqrt(np.mean(x[fi*H:min(len(x),(fi+1)*H)]**2))
    if best>.53 and rms>.065:
        c=[p for _,p in ranked if ac[p]>.77*best and ac[p]>.5]
        if c:
            P_TARGET[fi]=min(c)
            P_WEIGHT[fi]=(best-.48)*rms
    P_CANDS.append([p for _,p in ranked[:6]])
if P_WEIGHT.sum(): P_WEIGHT/=P_WEIGHT.sum()


def pitch_error(P):
    # log pitch-period error against observed fundamental; no penalty in noisy frames
    r=np.zeros(N,float)
    v=P_TARGET>0
    r[v]=np.minimum(2.,np.abs(np.log2(np.maximum(1,P[v])/P_TARGET[v])))
    return float((r*P_WEIGHT).sum())


def score(K,P,E,full=False):
    yy=synth_exact(K,P,E,len(x)).astype(float)/128.
    mel,env=evaluate(yy)
    s,_=metrics(yy)
    pitch=pitch_error(P)
    # Higher is better, weights ~ comparable to 0.03 STOI and 0.08 mel difference
    value=2.0*s - .85*mel - .18*env - .17*pitch
    if full:return value, s, mel,env,pitch,yy
    return value

start=time.monotonic()
best=score(K,P,E,True)
print('AVR v4 base',np.round(best[:5],5), 'pitch targets',[(i,int(p)) for i,p in enumerate(P_TARGET) if p],flush=True)
print('initial pitches',list(P),flush=True)
counts=0

def try_update(arr,i,cands,kind):
    global best, counts
    old=int(arr[i]); opt=old; ob=float(best[0]); current=best
    for v in dict.fromkeys(int(v) for v in cands):
        if v==old:continue
        arr[i]=v
        cur=score(K,P,E,True)
        counts+=1
        if cur[0] >ob+1e-5:
            opt=v;ob=cur[0];current=cur
    arr[i]=opt
    if opt!=old:
        best=current
        return True
    return False

log_file='exact_optimization.log'
with open(log_file,'w') as outf:
 def log(msg):
    print(msg,flush=True);print(msg,file=outf,flush=True)
 log('begin '+str(np.round(best[:5],4)))
 for epoch in range(3):
    improvements={'pitch':0,'energy':0,'K':0}
    # Alter pitch only for source frames with reliable voicedness,
    # and additionally test making weak/ambiguous frames unvoiced.
    for i in range(N):
        if E[i]<=0: continue
        old=int(P[i]);candidates=[0,old]
        if P_TARGET[i]:
            t=P_TARGET[i]
            candidates += [t,max(16,t-1),min(140,t+1),max(16,t-2),t+2]
        if old>32: candidates += [old//2,old//3]
        candidates+=P_CANDS[i][:3]
        candidates=[v for v in candidates if 0<=v<=180]
        if try_update(P,i,candidates,'pitch'):improvements['pitch']+=1
    log('epoch '+str(epoch)+' after pitch '+str(np.round(best[:5],4))+' changes '+str(improvements['pitch'])+' '+str(round(time.monotonic()-start,1))+'s')
    np.savez('exact_running.npz',K=K,P=P,E=E)
    # amplitude optimized for each frame; preserve actual silence
    for i in range(N):
        if E[i]==0:continue
        a=int(E[i]); candidates=np.unique(np.clip([a-4,a-2,a-1,a+1,a+2,a+4,round(a*.65),round(a*1.35)],0,15))
        if try_update(E,i,candidates,'gain'):improvements['energy']+=1
    log('epoch '+str(epoch)+' after amplitude '+str(np.round(best[:5],4))+' changes '+str(improvements['energy'])+' '+str(round(time.monotonic()-start,1))+'s')
    np.savez('exact_running.npz',K=K,P=P,E=E)
    for i in rng.permutation(N):
        if E[i]==0:continue
        for j in rng.permutation(7):
            v=int(K[i,j]);cands=np.unique(np.clip([v-3,v-2,v-1,v+1,v+2,v+3],-7,7))
            if try_update(K[i],j,cands,'K'):improvements['K']+=1
        if i%14==0:
            log('epoch '+str(epoch)+' K frame '+str(i)+' score '+str(np.round(best[:5],4))+' elapsed '+str(round(time.monotonic()-start,1))+'s')
    log('epoch '+str(epoch)+' final '+str(np.round(best[:5],4))+' changes '+str(improvements)+' total eval '+str(counts)+' '+str(round(time.monotonic()-start,1))+'s')
    np.savez(f'exact_epoch{epoch}.npz',K=K,P=P,E=E,quality=best[0],stoi=best[1],mel=best[2],envelope=best[3],pitchloss=best[4])
    if epoch==2:break
