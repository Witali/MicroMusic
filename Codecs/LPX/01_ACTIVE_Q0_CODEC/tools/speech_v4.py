"""Opt-in LPX speech v4, fixed 40 ms packets at 4 or 6 kbit/s.

Original scalar LSF/pitch/sparse experiment, no trained codebooks. All search
is offline. Uses the existing Q0 integer synthesis; deliberately lossy.
"""
from __future__ import annotations
import argparse, struct, time
from pathlib import Path
import numpy as np
from numba import njit
from lpx4 import BitWriter, BitReader, HEADER
from wav_lpc import analyze, pack_frames, load_wav
from q0_model import coefficient_trace, synthesize, table, clamp

POSITIONS4=np.asarray([i+(i+2)//4 for i in range(16)],np.int64)


def quantize_spectrum(vectors, profile):
    bits=5 if profile==4 else 6; shift=10-bits; result=[]
    for i in range(0,len(vectors),2):
        average=np.mean(vectors[i:i+2],axis=0)
        codes=np.clip(np.rint((average-(1<<(shift-1)))/(1<<shift)),0,(1<<bits)-1).astype(int)
        for j in range(1,10):codes[j]=max(codes[j],codes[j-1]+1)
        if codes[-1]>=(1<<bits):
            codes[-1]=(1<<bits)-1
            for j in range(8,-1,-1):codes[j]=min(codes[j],codes[j+1]-1)
        result.append(codes.tolist())
    return result


def pack(samples,profile,spectra,params,pulses,pre=13926,bright=0):
    if profile not in (4,6) or not 1<=samples<=64000:raise ValueError('Invalid speech profile/count')
    packets=(samples+319)//320
    if len(spectra)!=packets or len(params)!=packets*2 or len(pulses)!=packets*16:
        raise ValueError('Incomplete final speech packet')
    w=BitWriter();bits=5 if profile==4 else 6
    for fi,vec in enumerate(spectra):
        if len(vec)!=10 or any(not 0<=v<(1<<bits) for v in vec) or any(a>=b for a,b in zip(vec,vec[1:])):
            raise ValueError('Unordered scalar spectrum')
        for v in vec:w.put(v,bits)
        if profile==6:w.put(0,6)
        for half in range(2):
            scale,lag,gain=map(int,params[fi*2+half])
            if not 0<=scale<32 or not 18<=lag<=145 or not 0<=gain<=14 or gain&1:
                raise ValueError('Invalid speech parameters')
            w.put(scale,5);w.put(lag-18,7);w.put(gain//2,3)
            for pos,amp in pulses[fi*16+half*8:fi*16+half*8+8]:
                pos,amp=int(pos),int(amp)
                if profile==4:
                    if pos not in POSITIONS4 or amp not in (-8,8):raise ValueError('Invalid 4k pulse')
                    w.put(int(np.flatnonzero(POSITIONS4==pos)[0]),4);w.put(int(amp>0),1)
                else:
                    if not 0<=pos<20 or not -8<=amp<=7:raise ValueError('Invalid 6k pulse')
                    w.put(pos,5);w.put(amp&15,4)
    w.aligned()
    return struct.pack(HEADER,b'L4HY',4,profile,8000,samples,pre,bright,320,160)+w.get()


def unpack(blob):
    if len(blob)<20:raise ValueError('Short speech header')
    magic,version,profile,rate,n,pre,bright,frame,block=struct.unpack(HEADER,blob[:20])
    if (magic,version,rate,frame,block)!=(b'L4HY',4,8000,320,160) or profile not in (4,6):
        raise ValueError('Unsupported speech header')
    if not 1<=n<=64000 or pre>16384 or bright>11469 or len(blob)!=20+((n+319)//320)*(20 if profile==4 else 30):
        raise ValueError('Invalid speech size/count/filter')
    r=BitReader(blob[20:]);bits=5 if profile==4 else 6;shift=10-bits
    spectra=[];params=[];pulses=[]
    for fi in range((n+319)//320):
        vec=[r.get(bits) for _ in range(10)]
        if any(a>=b for a,b in zip(vec,vec[1:])):raise ValueError('Unordered scalar spectrum')
        spectra.append(vec)
        if profile==6 and r.get(6):raise ValueError('Reserved speech bits')
        for half in range(2):
            params.append((r.get(5),r.get(7)+18,r.get(3)*2))
            for _ in range(8):
                pos=r.get(4 if profile==4 else 5)
                amp=(8 if r.get(1) else -8) if profile==4 else r.get(4)
                if profile==4:pos=int(POSITIONS4[pos])
                else:
                    if pos>=20:raise ValueError('Invalid speech pulse position')
                    if amp>=8:amp-=16
                pulses.append((pos,amp))
    vectors=[[(v<<shift)+(1<<(shift-1)) for v in vec] for vec in spectra for _ in range(2)]
    return n,pre,bright,vectors,params,pulses


def decode_model(blob):
    n,pre,bright,vectors,params,pulses=unpack(blob)
    q=[];scales=[]
    for half,(scale,lag,gain) in enumerate(params):
        scales.extend([scale*8]*2)
        for si in range(8):
            pos,amp=pulses[half*8+si]
            for j in range(20):
                old=q[-lag] if len(q)>=lag else 0
                predicted=min(31,max(-32,(gain*old+8)>>4))
                q.append(min(31,max(-32,predicted+(amp if j==pos else 0))))
    co=coefficient_trace(pack_frames(vectors[:(n+159)//160]),n)
    return synthesize(np.asarray(q[:n],np.int64),np.asarray(scales,np.int64),co,
                      table('scale_table.inc'),pre,bright)


@njit(cache=True)
def trial20(target,co,hist,dd,cc,qring,cursor,pre,step,lag,gain,pos,amp):
    h=hist.copy();ring=qring.copy();out=np.empty(20,np.int16);loss=0.
    for j in range(20):
        q=min(31,max(-32,(gain*ring[(cursor+j-lag)&255]+8)>>4))
        q=min(31,max(-32,q+(amp if j==pos else 0)));ring[(cursor+j)&255]=q
        acc=0
        for k in range(10):acc+=(co[j,k]*h[k])>>12
        pred=clamp(q*step-acc)
        for k in range(9,0,-1):h[k]=h[k-1]
        h[0]=pred;dd=clamp(pred+((pre*dd)>>14));cc=clamp(dd,-16384,16384)
        out[j]=clamp(cc*2,-32768,32767);loss+=float(out[j]-target[j])**2
    return loss,h,dd,cc,ring,out


@njit(cache=True)
def search_block(target,co,hist,dd,cc,qring,cursor,pre,step,lag,gain,profile):
    h=hist.copy();ring=qring.copy();pulses=np.zeros((8,2),np.int64)
    output=np.empty(160,np.int16);loss=0.
    for si in range(8):
        start=si*20;best=np.inf;bestpos=0;bestamp=0
        for pi in range(16 if profile==4 else 20):
            pos=pi+(pi+2)//4 if profile==4 else pi
            for ai in range(2 if profile==4 else 16):
                amp=(-8 if ai==0 else 8) if profile==4 else ai-8
                err,_,_,_,_,_=trial20(target[start:start+20],co[start:start+20],h,dd,cc,ring,
                                       cursor+start,pre,step,lag,gain,pos,amp)
                if err<best:best=err;bestpos=pos;bestamp=amp
        err,h,dd,cc,ring,out=trial20(target[start:start+20],co[start:start+20],h,dd,cc,ring,
                                    cursor+start,pre,step,lag,gain,bestpos,bestamp)
        pulses[si,0]=bestpos;pulses[si,1]=bestamp;output[start:start+20]=out;loss+=err
    return loss,h,dd,cc,ring,pulses,output


@njit(cache=True)
def search(reference,co,steps,pre,profile):
    n=len(reference);params=np.zeros((n//160,3),np.int64);pulses=np.zeros((n//20,2),np.int64)
    output=np.empty(n,np.int16);h=np.zeros(10,np.int64);ring=np.zeros(256,np.int64);dd=cc=0
    # Open-loop inverse filtering only proposes energy and pitch. All selected
    # parameters/pulses are scored through closed-loop integer synthesis.
    emphasized=np.zeros(n,np.float64);residual=np.zeros(n,np.float64)
    for j in range(n):
        emphasized[j]=reference[j]/2-(pre*(reference[j-1]/2) if j else 0)/16384
        residual[j]=emphasized[j]
        for k in range(10):
            if j>k:residual[j]+=co[j,k]*emphasized[j-k-1]/4096
    for bi in range(n//160):
        start=bi*160;end=start+160;power=np.mean(residual[start:end]**2)
        desired=max(1.,np.sqrt(power*20)/8)
        center=int(np.rint((128+16*np.log2(desired/16.384))/8))
        center=max(1,min(31,center));lag=18;pitchscore=-1.;pitchgain=0
        for cand in range(18,146):
            dot=energy=0.
            for j in range(start,end):
                v=residual[j-cand] if j>=cand else 0.
                dot+=v*residual[j];energy+=v*v
            score=max(0.,dot)**2/(energy+1.)
            if score>pitchscore:
                pitchscore=score;lag=cand;pitchgain=min(14,max(0,int(np.rint(8*dot/(energy+1)))*2))
        best=np.inf;bestscale=0;bestlag=18;bestgain=0
        for scale in range(max(0,center-2),min(31,center+2)+1):
            for choice in range(3):
                gain=0 if choice==0 else pitchgain if choice==1 else 14
                if choice and not gain:continue
                err,_,_,_,_,_,_=search_block(reference[start:end],co[start:end],h,dd,cc,ring,start,
                    pre,steps[scale*8],lag,gain,profile)
                if err<best:best=err;bestscale=scale;bestlag=lag;bestgain=gain
        _,h,dd,cc,ring,pp,pcm=search_block(reference[start:end],co[start:end],h,dd,cc,ring,start,
            pre,steps[bestscale*8],bestlag,bestgain,profile)
        params[bi]=np.asarray([bestscale,bestlag,bestgain]);pulses[bi*8:bi*8+8]=pp
        output[start:end]=pcm
    return params,pulses,output


def encode(reference,profile,decoder,pre=13926,bandwidth=.97):
    ref=np.asarray(reference)
    if profile not in (4,6) or ref.ndim!=1 or ref.dtype.kind not in 'iu' or not 1<=len(ref)<=64000 or np.any(ref<-32768) or np.any(ref>32767):
        raise ValueError('Expected 1..64000 PCM16 samples and profile 4/6')
    started=time.perf_counter();n=len(ref);padded=np.pad(ref.astype(np.int64),(0,(-n)%320))
    vectors,analysis=analyze(padded,pre=pre,bandwidth=bandwidth)
    spectra=quantize_spectrum(vectors,profile);shift=5 if profile==4 else 4
    quantized=[[(v<<shift)+(1<<(shift-1)) for v in vec] for vec in spectra for _ in range(2)]
    co=coefficient_trace(pack_frames(quantized),len(padded))
    params,pulses,expected=search(padded,co,table('scale_table.inc'),pre,profile)
    blob=pack(n,profile,spectra,params,pulses,pre)
    pcm=decoder.decode_one_s16(blob,n)
    if pcm is None or not np.array_equal(pcm,expected[:n]) or not np.array_equal(pcm,decode_model(blob)):
        raise AssertionError('Speech encoder/model/native mismatch')
    return blob,pcm,{'profile':profile,'samples':n,'file_bytes':len(blob),
        'payload_bps':(len(blob)-20)*64000/n,'file_bps':len(blob)*64000/n,
        'analysis':analysis,'bandwidth':bandwidth,'native_model_exact':True,
        'algorithmic_packet_ms':40,'synthesis_shift_samples':0,
        'seconds':time.perf_counter()-started}


def main():
    import json, soundfile as sf
    from batch_decoder import BatchSession
    from standard_metrics import compare
    from output_paths import protect_outputs
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('input',type=Path);ap.add_argument('output',type=Path)
    ap.add_argument('--profile',type=int,choices=(4,6),required=True)
    a=ap.parse_args();paths=[a.output/'audio.l4hy',a.output/'decoded.wav',a.output/'report.json']
    protect_outputs([a.input],paths);reference,_=load_wav(a.input)
    with BatchSession('batch',speech=True) as decoder:blob,pcm,report=encode(reference,a.profile,decoder)
    report['metrics']=compare(reference,pcm,True,known_delay=0)[0]
    a.output.mkdir(parents=True,exist_ok=True);paths[0].write_bytes(blob)
    sf.write(paths[1],pcm,8000,subtype='PCM_16');paths[2].write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
