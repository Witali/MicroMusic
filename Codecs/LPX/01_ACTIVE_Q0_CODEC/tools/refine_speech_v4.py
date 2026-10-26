"""Bounded encoder-only excitation refinement with frozen speech v4 spectra.

Pulse/energy/pitch decisions use a longer exact integer-synthesis horizon
than the initial 20-sample greedy search. Every accepted group must improve
full-reference SSE while retaining its full-reference STOI floor. The stream
format, length, spectrum, header filters and decoder remain unchanged.
"""
from __future__ import annotations
import argparse, hashlib, json, time
from pathlib import Path
import numpy as np
from numba import njit
from speech_v4 import unpack, pack
from q0_model import coefficient_trace, table, clamp
from wav_lpc import pack_frames
from standard_metrics import error_metrics


@njit(cache=True)
def advance(co,params,pulses,steps,pre,bright,start,end,hist,dd,cc,ring):
    """Exact synthesis from a snapshot; all arrays/state are private copies."""
    h=hist.copy();qring=ring.copy();output=np.empty(end-start,np.int16)
    for j in range(start,end):
        scale,lag,gain=params[j//160]
        pos,amp=pulses[j//20]
        q=min(31,max(-32,(gain*qring[(j-lag)&255]+8)>>4))
        q=min(31,max(-32,q+(amp if j%20==pos else 0)))
        qring[j&255]=q
        acc=0
        for k in range(10):acc+=(co[j,k]*h[k])>>12
        pred=clamp(q*steps[scale*8]-acc)
        for k in range(9,0,-1):h[k]=h[k-1]
        h[0]=pred;dd=clamp(pred+((pre*dd)>>14))
        clipped=clamp(dd,-16384,16384)
        b=clamp(clipped-((bright*cc)>>14),-16384,16384);cc=clipped
        output[j-start]=clamp(b*2,-32768,32767)
    return output,h,dd,cc,qring


@njit(cache=True)
def loss(target,output):
    result=np.int64(0)
    for i in range(len(target)):
        d=np.int64(target[i])-np.int64(output[i]);result+=d*d
    return result


@njit(cache=True)
def optimize_group(reference,co,params,pulses,steps,pre,bright,profile,
                   start,end,horizon,hist,dd,cc,ring,tune_parameters):
    """Sequential local changes; later groups/full-waveform checks may reject."""
    parameters=params.copy();innovations=pulses.copy();h=hist.copy();qring=ring.copy()
    evaluations=0;changed=0
    for at in range(start,end,20):
        stop=min(len(reference),at+horizon)
        target=reference[at:stop]
        if tune_parameters and at%160==0:
            index=at//160;original=parameters[index].copy();best=original.copy()
            out,_,_,_,_=advance(co,parameters,innovations,steps,pre,bright,at,stop,h,dd,cc,qring)
            best_loss=loss(target,out);evaluations+=1
            # Separate bounded one-coordinate proposals. No new decoder bits.
            proposals=np.zeros((8,3),np.int64)
            for i in range(8):proposals[i]=original
            proposals[0,0]=max(0,original[0]-1);proposals[1,0]=min(31,original[0]+1)
            proposals[2,1]=max(18,original[1]-1);proposals[3,1]=min(145,original[1]+1)
            proposals[4,2]=max(0,original[2]-2);proposals[5,2]=min(14,original[2]+2)
            proposals[6,2]=0;proposals[7,2]=14
            for proposal in proposals:
                parameters[index]=proposal
                out,_,_,_,_=advance(co,parameters,innovations,steps,pre,bright,at,stop,h,dd,cc,qring)
                trial=loss(target,out);evaluations+=1
                if trial<best_loss:best_loss=trial;best=proposal.copy()
            parameters[index]=best
            if np.any(best!=original):changed+=1
        index=at//20;original=innovations[index].copy();best=original.copy()
        out,_,_,_,_=advance(co,parameters,innovations,steps,pre,bright,at,stop,h,dd,cc,qring)
        best_loss=loss(target,out);evaluations+=1
        amplitudes=np.asarray([-8,8],np.int64) if profile==4 else np.asarray(
            [original[1],max(-8,original[1]-1),min(7,original[1]+1),
             max(-8,original[1]-2),min(7,original[1]+2),0,min(7,max(-8,-original[1]))],np.int64)
        for pi in range(16 if profile==4 else 20):
            position=pi+(pi+2)//4 if profile==4 else pi
            if at+position>=len(reference):continue
            for ai in range(len(amplitudes)):
                amp=amplitudes[ai];duplicate=False
                for prev in range(ai):
                    if amplitudes[prev]==amp:duplicate=True
                if duplicate:continue
                innovations[index,0]=position;innovations[index,1]=amp
                out,_,_,_,_=advance(co,parameters,innovations,steps,pre,bright,at,stop,h,dd,cc,qring)
                trial=loss(target,out);evaluations+=1
                if trial<best_loss:best_loss=trial;best[0]=position;best[1]=amp
        innovations[index]=best
        if np.any(best!=original):changed+=1
        _,h,dd,cc,qring=advance(co,parameters,innovations,steps,pre,bright,
                              at,min(end,at+20),h,dd,cc,qring)
    return parameters,innovations,evaluations,changed


def refine(reference,blob,decoder,passes=1,horizon=160,group_samples=640,tune_parameters=True):
    if passes not in (1,2,3,4) or horizon not in (40,80,160,320,640) or not 160<=group_samples<=2560 or group_samples%160:
        raise ValueError('Expected 1..4 passes, supported horizon and 160-aligned group size')
    reference=np.asarray(reference)
    if reference.ndim!=1 or reference.dtype.kind not in 'iu' or np.any(reference<-32768) or np.any(reference>32767):
        raise ValueError('Expected mono PCM16 reference')
    n,pre,bright,vectors,params,pulses=unpack(blob)
    if len(reference)!=n:raise ValueError('Reference/stream sample count mismatch')
    started=time.perf_counter();profile=blob[5]
    shift=5 if profile==4 else 4
    spectra=[[(v-(1<<(shift-1)))>>shift for v in vec] for vec in vectors[::2]]
    co=coefficient_trace(pack_frames(vectors[:(n+159)//160]),n)
    steps=table('scale_table.inc');parameters=np.asarray(params,np.int64);innovations=np.asarray(pulses,np.int64)
    zero_h=np.zeros(10,np.int64);zero_ring=np.zeros(256,np.int64)
    pcm,_,_,_,_=advance(co,parameters,innovations,steps,pre,bright,0,n,zero_h,0,0,zero_ring)
    native=decoder.decode_one_s16(blob,n)
    if native is None or not np.array_equal(native,pcm):raise AssertionError('Snapshot model/native baseline mismatch')
    initial=error_metrics(reference,pcm,True);current=initial
    checkpoints=[];evaluations=0;accepted=0
    for pass_index in range(passes):
        pass_accepted=0
        for start in range(0,n,group_samples):
            end=min(n,start+group_samples)
            _,h,dd,cc,ring=advance(co,parameters,innovations,steps,pre,bright,0,start,zero_h,0,0,zero_ring)
            candidate_params,candidate_pulses,count,changed=optimize_group(reference,co,parameters,innovations,
                steps,pre,bright,profile,start,end,horizon,h,dd,cc,ring,bool(tune_parameters))
            evaluations+=int(count)
            if not changed:continue
            trial,_,_,_,_=advance(co,candidate_params,candidate_pulses,steps,pre,bright,0,n,zero_h,0,0,zero_ring)
            # Avoid calculating STOI for a waveform that already fails SSE.
            if int(loss(reference,trial))>=current['error_energy']:continue
            quality=error_metrics(reference,trial,True)
            stoi_ok=current['stoi'] is None or quality['stoi'] is not None and quality['stoi']>=current['stoi']-1e-12
            if not stoi_ok:continue
            parameters=candidate_params;innovations=candidate_pulses;pcm=trial;current=quality
            accepted+=1;pass_accepted+=1
            checkpoints.append({'pass':pass_index,'start_sample':start,'stop_sample':end,
                                'error_energy':quality['error_energy'],'stoi':quality['stoi']})
        if not pass_accepted:break
    result=pack(n,profile,spectra,parameters,innovations,pre,bright)
    if len(result)!=len(blob) or result[:20]!=blob[:20]:raise AssertionError('Refinement changed v4 geometry/header')
    if unpack(result)[3]!=vectors:raise AssertionError('Refinement changed spectral coefficients')
    actual=decoder.decode_one_s16(result,n)
    if actual is None or not np.array_equal(actual,pcm):raise AssertionError('Refined snapshot model/native mismatch')
    if current['error_energy']>initial['error_energy'] or initial['stoi'] is not None and current['stoi']<initial['stoi']-1e-12:
        raise AssertionError('Full-waveform quality floor failed')
    return result,actual,{'profile':profile,'samples':n,'file_bytes':len(result),'spectra_exact':True,
        'decoder_modified':False,'native_model_exact':True,'baseline':initial,'selected':current,
        'passes_requested':passes,'horizon_samples':horizon,'group_samples':group_samples,
        'tune_parameters':bool(tune_parameters),'candidate_evaluations':evaluations,
        'accepted_groups':accepted,'checkpoints':checkpoints,'seconds':time.perf_counter()-started}


def main():
    import soundfile as sf
    from batch_decoder import BatchSession
    from output_paths import protect_outputs
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('reference',type=Path);ap.add_argument('input',type=Path);ap.add_argument('output',type=Path)
    ap.add_argument('--passes',type=int,default=1);ap.add_argument('--horizon',type=int,default=160)
    ap.add_argument('--group-samples',type=int,default=640);ap.add_argument('--pulse-only',action='store_true')
    a=ap.parse_args();paths=[a.output/'audio.l4hy',a.output/'decoded.wav',a.output/'report.json']
    protect_outputs([a.reference,a.input],paths)
    reference,rate=sf.read(a.reference,dtype='int16')
    if rate!=8000:raise ValueError('Reference must be 8kHz')
    with BatchSession('batch',v3_features=24,speech=True) as decoder:
        result,pcm,report=refine(reference,a.input.read_bytes(),decoder,a.passes,a.horizon,
                                 a.group_samples,not a.pulse_only)
    report['stream_sha256']=hashlib.sha256(result).hexdigest()
    a.output.mkdir(parents=True,exist_ok=True);paths[0].write_bytes(result)
    sf.write(paths[1],pcm,8000,subtype='PCM_16');paths[2].write_bytes((json.dumps(report,indent=2)+'\n').encode())
    print(json.dumps({k:report[k] for k in ('profile','file_bytes','accepted_groups','seconds')}))


if __name__=='__main__':main()
