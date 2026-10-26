"""Bounded offline extra innovations with frozen speech spectra and base fields.

Snapshot integer synthesis is adapted from refine_speech_v4.advance. An extra
and a primary pulse at the same location are summed before q saturation.
Selected groups must improve whole-reference SSE without lowering STOI.
"""
from __future__ import annotations
import argparse, hashlib, json, time
from pathlib import Path
import numpy as np
from numba import njit
import speech_compact as compact
from q0_model import coefficient_trace, table, clamp
from wav_lpc import pack_frames
from standard_metrics import error_metrics


@njit(cache=True)
def advance(co,params,pulses,extras,steps,pre,bright,start,end,hist,dd,cc,ring):
    h=hist.copy();qring=ring.copy();output=np.empty(end-start,np.int16)
    for j in range(start,end):
        scale,lag,gain=params[j//160];pos,amp=pulses[j//20];ep,ea=extras[j//40]
        predicted=min(31,max(-32,(gain*qring[(j-lag)&255]+8)>>4))
        q=min(31,max(-32,predicted+(amp if j%20==pos else 0)+(ea if j%40==ep else 0)))
        qring[j&255]=q;acc=0
        for k in range(10):acc+=(co[j,k]*h[k])>>12
        pred=clamp(q*steps[scale*8]-acc)
        for k in range(9,0,-1):h[k]=h[k-1]
        h[0]=pred;dd=clamp(pred+((pre*dd)>>14));clipped=clamp(dd,-16384,16384)
        out=clamp(clipped-((bright*cc)>>14),-16384,16384);cc=clipped
        output[j-start]=clamp(out*2,-32768,32767)
    return output,h,dd,cc,qring


@njit(cache=True)
def sse(target,actual):
    total=np.int64(0)
    for i in range(len(target)):
        d=np.int64(target[i])-np.int64(actual[i]);total+=d*d
    return total


@njit(cache=True)
def proposals(reference,co,params,pulses,steps,pre,bright,horizon,position_candidates):
    """One independently scored proposal per chunk, using baseline snapshots.

    Probe every position at +4/-4, rank by fitted linear benefit, then test
    every nonzero legal amplitude at a bounded number of top positions.
    This screening is heuristic; all accepted output is checked globally.
    """
    chunks=(len(reference)+39)//40;extras=np.zeros((len(pulses)//2,2),np.int64)
    extras[:,0]=-1;choices=extras.copy();benefits=np.zeros(chunks,np.int64)
    hist=np.zeros(10,np.int64);ring=np.zeros(256,np.int64);dd=cc=0;evaluations=0
    for index in range(chunks):
        at=index*40;stop=min(len(reference),at+horizon);target=reference[at:stop]
        baseline,_,_,_,_=advance(co,params,pulses,extras,steps,pre,bright,at,stop,hist,dd,cc,ring)
        original_loss=sse(target,baseline);best_loss=original_loss;bestpos=-1;bestamp=0
        scores=np.full(40,-np.inf);valid_positions=min(40,len(reference)-at)
        if original_loss:
            for pos in range(valid_positions):
                for amp in (-4,4):
                    extras[index,0]=pos;extras[index,1]=amp
                    out,_,_,_,_=advance(co,params,pulses,extras,steps,pre,bright,at,stop,hist,dd,cc,ring)
                    evaluations+=1;power=dot=0.
                    for j in range(len(out)):
                        delta=float(out[j])-float(baseline[j]);power+=delta*delta
                        dot+=(float(target[j])-float(baseline[j]))*delta
                    center=min(7,max(-8,int(np.rint(amp*dot/(power+1.)))))
                    ratio=center/amp
                    estimated=2*ratio*dot-ratio*ratio*power
                    if estimated>scores[pos]:scores[pos]=estimated
                    trial=sse(target,out)
                    if trial<best_loss:best_loss=trial;bestpos=pos;bestamp=amp
            count=min(position_candidates,valid_positions)
            for _ in range(count):
                pos=int(np.argmax(scores));scores[pos]=-np.inf
                for amp in range(-8,8):
                    if amp==0:continue
                    extras[index,0]=pos;extras[index,1]=amp
                    out,_,_,_,_=advance(co,params,pulses,extras,steps,pre,bright,at,stop,hist,dd,cc,ring)
                    evaluations+=1;trial=sse(target,out)
                    if trial<best_loss:best_loss=trial;bestpos=pos;bestamp=amp
        choices[index,0]=bestpos;choices[index,1]=bestamp;benefits[index]=original_loss-best_loss
        extras[index,0]=-1;extras[index,1]=0
        _,hist,dd,cc,ring=advance(co,params,pulses,extras,steps,pre,bright,
                                  at,min(at+40,len(reference)),hist,dd,cc,ring)
    return choices,benefits,evaluations


def enhance(reference,blob,decoder,max_bytes,horizon=160,position_candidates=6,
            batch_size=16,max_full_evaluations=128):
    if horizon not in (160,320) or not 1<=position_candidates<=12 or not 1<=batch_size<=64 or not 1<=max_full_evaluations<=512:
        raise ValueError('Unsupported bounded search settings')
    ref=np.asarray(reference)
    if ref.ndim!=1 or ref.dtype.kind not in 'iu' or np.any(ref<-32768) or np.any(ref>32767):
        raise ValueError('Expected mono PCM16 reference')
    if isinstance(max_bytes,bool) or int(max_bytes)!=max_bytes or not 22<=max_bytes<=65535:
        raise ValueError('Expected complete file cap in 22..65535')
    started=time.perf_counter();args=compact.components(blob)
    n,profile,spectra,params,pulses,pre,bright=args
    if len(ref)!=n:raise ValueError('Reference/stream sample count mismatch')
    base,base_meta=compact.pack(*args)
    if len(base)>max_bytes:raise ValueError('Exact compact baseline does not fit file cap')
    shift=5 if profile==4 else 4
    vectors=[[(v<<shift)+(1<<(shift-1)) for v in vec] for vec in spectra for _ in range(2)]
    co=coefficient_trace(pack_frames(vectors[:(n+159)//160]),n);steps=table('scale_table.inc')
    parameters=np.asarray(params,np.int64);innovations=np.asarray(pulses,np.int64)
    extras=np.zeros((len(spectra)*8,2),np.int64);extras[:,0]=-1
    zero_h=np.zeros(10,np.int64);zero_ring=np.zeros(256,np.int64)
    def render(x):return advance(co,parameters,innovations,x,steps,pre,bright,0,n,zero_h,0,0,zero_ring)[0]
    pcm=render(extras);native=decoder.decode_one_s16(base,n)
    if native is None or not np.array_equal(native,pcm):raise AssertionError('Extra snapshot baseline/native mismatch')
    initial=error_metrics(ref,pcm,True);current=initial
    _,marker_meta=compact.pack(*args,force_extras=True)
    capacity=max(0,min((n+39)//40,((int(max_bytes)-22)*8-marker_meta['payload_bits'])//10))
    evaluations=0;full_evaluations=0;accepted=0;checkpoints=[];rejected_sse=0;rejected_stoi=0
    if capacity and initial['error_energy']:
        choices,benefits,evaluations=proposals(ref.astype(np.int64),co,parameters,innovations,
            steps,pre,bright,horizon,position_candidates)
        order=sorted((i for i,b in enumerate(benefits) if b>0),key=lambda i:(-int(benefits[i]),i))
        for start in range(0,len(order),batch_size):
            if accepted>=capacity or full_evaluations>=max_full_evaluations:break
            todo=[order[start:start+min(batch_size,capacity-accepted)]]
            while todo and full_evaluations<max_full_evaluations and accepted<capacity:
                group=todo.pop(0)[:capacity-accepted]
                if not group:continue
                candidate=extras.copy()
                for i in group:candidate[i]=choices[i]
                trial=render(candidate);full_evaluations+=1
                good=int(sse(ref,trial))<current['error_energy'];reason='sse'
                quality=None
                if good:
                    quality=error_metrics(ref,trial,True)
                    good=current['stoi'] is None or quality['stoi'] is not None and quality['stoi']>=current['stoi']-1e-12
                    reason='stoi'
                if good:
                    extras=candidate;pcm=trial;current=quality;accepted+=len(group)
                    checkpoints.append({'added_chunks':group,'extra_pulses':accepted,
                        'error_energy':quality['error_energy'],'stoi':quality['stoi']})
                else:
                    if reason=='sse':rejected_sse+=1
                    else:rejected_stoi+=1
                    if len(group)>1:
                        mid=len(group)//2;todo[0:0]=[group[:mid],group[mid:]]
    result,meta=compact.pack(*args,extras=extras.tolist())
    if len(result)>max_bytes:raise AssertionError('Enhanced complete-file cap failed')
    actual=decoder.decode_one_s16(result,n)
    if actual is None or not np.array_equal(actual,pcm) or not np.array_equal(actual,compact.decode_model(result)):
        raise AssertionError('Enhanced native/snapshot/independent model mismatch')
    if compact.unpack(result)[:7]!=args:raise AssertionError('Extra search changed frozen base fields')
    if current['error_energy']>initial['error_energy'] or initial['stoi'] is not None and current['stoi']<initial['stoi']-1e-12:
        raise AssertionError('Enhanced whole-reference floor failed')
    report={'profile':profile,'samples':n,'max_file_bytes':int(max_bytes),'file_bytes':len(result),
        'payload_bits':meta['payload_bits'],'spectra_params_base_pulses_exact':True,'native_model_exact':True,
        'exact_compact_file_bytes':len(base),'extra_capacity':capacity,'extra_pulses':int(accepted),
        'baseline':initial,'selected':current,'horizon_samples':horizon,'position_candidates':position_candidates,
        'candidate_evaluations':int(evaluations),'full_evaluations':full_evaluations,
        'full_evaluation_limit':max_full_evaluations,'full_limit_reached':full_evaluations>=max_full_evaluations,
        'rejected_sse_groups':rejected_sse,'rejected_stoi_groups':rejected_stoi,'checkpoints':checkpoints,
        'seconds':time.perf_counter()-started}
    return result,actual,report


def main():
    import soundfile as sf
    from batch_decoder import BatchSession
    from output_paths import protect_outputs
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('reference',type=Path);ap.add_argument('input',type=Path);ap.add_argument('output',type=Path)
    ap.add_argument('--max-bytes',type=int,required=True);ap.add_argument('--horizon',type=int,choices=(160,320),default=160)
    ap.add_argument('--position-candidates',type=int,default=6);ap.add_argument('--full-evaluations',type=int,default=128)
    a=ap.parse_args();paths=[a.output/'audio.l4hy',a.output/'decoded.wav',a.output/'report.json']
    protect_outputs([a.reference,a.input],paths)
    ref,rate=sf.read(a.reference,dtype='int16')
    if rate!=8000:raise ValueError('Reference must be 8kHz')
    with BatchSession('batch',v3_features=24,speech=True,speech_compact=True) as decoder:
        result,pcm,report=enhance(ref,a.input.read_bytes(),decoder,a.max_bytes,a.horizon,
                                 a.position_candidates,max_full_evaluations=a.full_evaluations)
    report.update(reference_sha256=hashlib.sha256(ref.astype('<i2').tobytes()).hexdigest(),
        input_sha256=hashlib.sha256(a.input.read_bytes()).hexdigest(),
        stream_sha256=hashlib.sha256(result).hexdigest())
    a.output.mkdir(parents=True,exist_ok=True);paths[0].write_bytes(result)
    sf.write(paths[1],pcm,8000,subtype='PCM_16');paths[2].write_bytes((json.dumps(report,indent=2)+'\n').encode())
    print(json.dumps({k:report[k] for k in ('profile','file_bytes','extra_pulses','full_evaluations','seconds')}))


if __name__=='__main__':main()
