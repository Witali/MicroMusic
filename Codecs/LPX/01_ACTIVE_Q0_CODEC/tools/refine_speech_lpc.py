"""Bounded joint LSF and excitation search inside the existing speech v5 format.

Screen legal scalar LSF neighbours with exact local coefficient interpolation,
then re-fit nearby excitation before full-reference acceptance. Actual spectral
Rice costs and complete-file caps are counted. The input remains eligible, and
a best-encountered PCM-SSE alternative is returned for explicit tradeoff review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from numbers import Integral
from pathlib import Path
import time

import numpy as np
from numba import njit
import speech_compact as compact
from enhance_speech_compact import advance, sse
from q0_model import _coefficient_trace_vectors, coefficient_trace, table
from refine_speech_compact import quality, no_regression
from speech_rate_allocation import spectrum_bits, fit_capacity
from standard_metrics import pwm_duties
from wav_lpc import pack_frames


SEARCH_PRESETS = {
    'default': dict(frame_limit=32, spectral_candidates=2, lookahead=640,
                    excitation_horizon=80, passes=1),
    'expanded': dict(frame_limit=64, spectral_candidates=4, lookahead=1280,
                     excitation_horizon=160, passes=2),
}


def coefficient_patch(spectra, profile, frame, samples, cosine=None):
    """Exact changed compact frame plus the next160-sample interpolation tail.

    Compact spectra are repeated over two160-sample core frames. Changing one
    compact vector affects those320 samples and the next core frame's previous
    anchor. Include a preceding vector as context, never reset interpolation at
    the changed frame. The returned patch is trimmed to actual output samples.
    """
    start=frame*320;count=min(480,samples-start)
    if count<=0:raise ValueError('Frame does not affect requested samples')
    indices=([frame-1] if frame else [])+[frame,frame]
    if frame+1<len(spectra):indices.append(frame+1)
    shift=5 if profile==4 else 4
    vectors=np.asarray([[(int(v)<<shift)+(1<<(shift-1)) for v in spectra[i]]
                        for i in indices],np.int64)
    offset=160 if frame else 0
    vectors=vectors[:(offset+count+159)//160]
    result=_coefficient_trace_vectors(vectors,offset+count,
        table('cos_table.inc') if cosine is None else cosine)
    return result[offset:offset+count]


@njit(cache=True)
def adapt_excitation(reference,co,params,pulses,extras,steps,pre,bright,profile,
                     start,end,horizon,hist,dd,cc,ring,capacity):
    """Small coordinate neighbourhood; all scores use the existing integer DSP."""
    pp=params.copy();ii=pulses.copy();ee=extras.copy()
    h=hist.copy();qr=ring.copy();active=np.count_nonzero(ee[:,1]);evaluations=0
    for at in range(start,end,40):
        stop=min(len(reference),at+horizon);target=reference[at:stop]
        if at%160==0:
            index=at//160;original=pp[index].copy();best=original.copy()
            out,_,_,_,_=advance(co,pp,ii,ee,steps,pre,bright,at,stop,h,dd,cc,qr)
            loss=sse(target,out);evaluations+=1
            for field in range(3):
                for direction in (-1,1):
                    proposal=original.copy()
                    if field==0:proposal[0]=max(0,min(31,original[0]+direction))
                    elif field==1:proposal[1]=max(18,min(145,original[1]+direction))
                    else:proposal[2]=max(0,min(14,original[2]+direction*2))
                    pp[index]=proposal
                    out,_,_,_,_=advance(co,pp,ii,ee,steps,pre,bright,at,stop,h,dd,cc,qr)
                    trial=sse(target,out);evaluations+=1
                    if trial<loss:loss=trial;best=proposal.copy()
            pp[index]=best
        # Refit existing or new optional pulses at a small set of positions.
        index=at//40;original=ee[index].copy();best=original.copy()
        out,_,_,_,_=advance(co,pp,ii,ee,steps,pre,bright,at,stop,h,dd,cc,qr)
        loss=sse(target,out);evaluations+=1;valid=min(40,len(reference)-at)
        positions=np.zeros(40,np.uint8);peak=0;peak_error=-1
        for j in range(valid):
            error=abs(np.int64(target[j])-np.int64(out[j]))
            if error>peak_error:peak_error=error;peak=j
        positions[peak]=1
        if original[1]:
            for delta in (-1,0,1):
                pos=original[0]+delta
                if 0<=pos<valid:positions[pos]=1
        for pos in range(valid):
            if not positions[pos]:continue
            for amp in range(-8,8):
                if not (amp in (-4,-2,0,2,4) or abs(amp-original[1])<=1):continue
                if amp and not original[1] and active>=capacity:continue
                ee[index,0]=pos if amp else -1;ee[index,1]=amp
                trialout,_,_,_,_=advance(co,pp,ii,ee,steps,pre,bright,at,stop,h,dd,cc,qr)
                trial=sse(target,trialout);evaluations+=1
                if trial<loss:loss=trial;best=ee[index].copy()
        ee[index]=best;active+=int(best[1]!=0)-int(original[1]!=0)
        for half in range(2):
            begin=at+half*20
            if begin>=end:break
            stop=min(len(reference),begin+horizon);target=reference[begin:stop]
            index=begin//20;original=ii[index].copy();best=original.copy()
            out,_,_,_,_=advance(co,pp,ii,ee,steps,pre,bright,begin,stop,h,dd,cc,qr)
            loss=sse(target,out);evaluations+=1
            for pos in range(max(0,original[0]-2),min(20,len(reference)-begin,original[0]+3)):
                if profile==4 and pos%5==2:continue
                for amp in range(-8,9):
                    if profile==4:
                        if amp not in (-8,8):continue
                    elif amp>7 or abs(amp-original[1])>2:continue
                    ii[index,0]=pos;ii[index,1]=amp
                    trialout,_,_,_,_=advance(co,pp,ii,ee,steps,pre,bright,begin,stop,h,dd,cc,qr)
                    trial=sse(target,trialout);evaluations+=1
                    if trial<loss:loss=trial;best=ii[index].copy()
            ii[index]=best
            _,h,dd,cc,qr=advance(co,pp,ii,ee,steps,pre,bright,begin,min(end,begin+20),h,dd,cc,qr)
    return pp,ii,ee,evaluations


def frame_order(reference, pcm, limit):
    frames=(len(reference)+319)//320
    if frames<=limit:return list(range(frames))
    losses=[int(sse(reference[i*320:min(len(reference),(i+1)*320)],
                    pcm[i*320:min(len(pcm),(i+1)*320)])) for i in range(frames)]
    ranked=sorted(range(frames),key=lambda i:(-losses[i],i))
    selected=set(ranked[:(limit+1)//2])
    for i in np.linspace(0,frames-1,limit//2,dtype=int):selected.add(int(i))
    for i in ranked:
        if len(selected)>=limit:break
        selected.add(i)
    return sorted(selected)


def refine(reference,blob,decoder,max_bytes,*,frame_limit=32,spectral_candidates=2,
           lookahead=640,excitation_horizon=80,passes=1,refit=True):
    """Return selected v5 bytes/PCM/report plus a raw best-encountered stream."""
    values=(max_bytes,frame_limit,spectral_candidates,lookahead,excitation_horizon,passes)
    if any(isinstance(v,bool) or not isinstance(v,Integral) for v in values):
        raise ValueError('Expected integer byte cap and bounded search settings')
    if not len(blob)<=max_bytes<=65535 or not 1<=frame_limit<=200 or not 1<=spectral_candidates<=4:
        raise ValueError('Invalid complete-file cap or search bound')
    if lookahead not in (320,640,1280) or excitation_horizon not in (80,160) or passes not in (1,2) or not isinstance(refit,bool):
        raise ValueError('Unsupported bounded search settings')
    ref=np.asarray(reference)
    if ref.ndim!=1 or ref.dtype.kind not in 'iu' or np.any(ref<-32768) or np.any(ref>32767):
        raise ValueError('Expected mono PCM16 reference')
    n,profile,spectra,params,pulses,pre,bright,extras=compact.unpack(blob)
    if len(ref)!=n:raise ValueError('Reference/stream sample count mismatch')
    started=time.perf_counter();reference64=ref.astype(np.int64)
    sp=np.asarray(spectra,np.int64);pp=np.asarray(params,np.int64);ii=np.asarray(pulses,np.int64);ee=np.asarray(extras,np.int64)
    shift=5 if profile==4 else 4
    vectors=[[(int(v)<<shift)+(1<<(shift-1)) for v in row] for row in sp for _ in range(2)]
    co=coefficient_trace(pack_frames(vectors[:(n+159)//160]),n);steps=table('scale_table.inc');cosine=table('cos_table.inc')
    zero_h=np.zeros(10,np.int64);zero_ring=np.zeros(256,np.int64)
    pcm=advance(co,pp,ii,ee,steps,pre,bright,0,n,zero_h,0,0,zero_ring)[0]
    native=decoder.decode_one_s16(blob,n)
    if native is None or not np.array_equal(pcm,native) or not np.array_equal(pcm,compact.decode_model(blob)):
        raise AssertionError('Joint LPC baseline native/model mismatch')
    before=quality(ref,pcm);after=before;result=bytes(blob);raw=bytes(blob);raw_loss=before['pcm16']['error_energy']
    costs=[spectrum_bits(row,None if f==0 else sp[f-1],profile) for f,row in enumerate(sp)]
    spectral_trials=excitation_trials=full_evaluations=accepted=cap_rejections=0;checkpoints=[]
    for pass_index in range(passes if before['pcm16']['error_energy'] else 0):
        pass_changes=0
        for frame in frame_order(reference64,pcm,frame_limit):
            start=frame*320;stop=min(n,start+lookahead);patch_end=min(n,start+480)
            old_patch=co[start:patch_end].copy()
            _,hist,dd,cc,ring=advance(co,pp,ii,ee,steps,pre,bright,0,start,zero_h,0,0,zero_ring)
            proposals=[]
            for field in range(10):
                for delta in (-1,1):
                    vec=sp[frame].copy();vec[field]+=delta
                    if not 0<=vec[field]<(32 if profile==4 else 64):continue
                    if field and vec[field]<=vec[field-1] or field<9 and vec[field]>=vec[field+1]:continue
                    trial_sp=sp.copy();trial_sp[frame]=vec
                    co[start:patch_end]=coefficient_patch(trial_sp,profile,frame,n,cosine)
                    trial=advance(co,pp,ii,ee,steps,pre,bright,start,stop,hist,dd,cc,ring)[0]
                    loss=int(sse(reference64[start:stop],trial));spectral_trials+=1
                    proposals.append((loss,field,delta,trial_sp))
            co[start:patch_end]=old_patch
            proposals.sort(key=lambda p:(p[0],p[1],p[2]))
            for _,field,delta,trial_sp in proposals[:spectral_candidates]:
                co[start:patch_end]=coefficient_patch(trial_sp,profile,frame,n,cosine)
                trial_costs=costs.copy()
                for f in range(frame,min(frame+2,len(sp))):
                    trial_costs[f]=spectrum_bits(trial_sp[f],None if f==0 else trial_sp[f-1],profile)
                trial_ee,capacity,size,removed=fit_capacity(sum(trial_costs),len(sp),profile,ee,int(max_bytes),start,n)
                if size>max_bytes:cap_rejections+=1;co[start:patch_end]=old_patch;continue
                trial_pp=pp;trial_ii=ii
                if refit:
                    trial_pp,trial_ii,trial_ee,count=adapt_excitation(reference64,co,pp,ii,trial_ee,steps,pre,bright,
                        profile,start,min(n,start+480),excitation_horizon,hist,dd,cc,ring,capacity)
                    excitation_trials+=int(count)
                suffix=advance(co,trial_pp,trial_ii,trial_ee,steps,pre,bright,start,n,hist,dd,cc,ring)[0]
                trial=np.concatenate((pcm[:start],suffix));loss=int(sse(reference64,trial))
                if loss>=after['pcm16']['error_energy']:co[start:patch_end]=old_patch;continue
                candidate,metadata=compact.pack(n,profile,trial_sp.tolist(),trial_pp.tolist(),trial_ii.tolist(),pre,bright,extras=trial_ee.tolist())
                if len(candidate)>max_bytes:raise AssertionError('Joint LPC serialized cap failed')
                measured=quality(ref,trial);full_evaluations+=1;allowed=no_regression(measured,before)
                checkpoints.append({'pass':pass_index,'frame':frame,'lsf_index':field,'lsf_delta':delta,
                    'file_bytes':len(candidate),'cap_extra_pulses_removed':removed,'metrics':measured,
                    'conservative_floors_passed':bool(allowed)})
                if loss<raw_loss:raw=candidate;raw_loss=loss
                if allowed:
                    sp=trial_sp;pp=trial_pp;ii=trial_ii;ee=trial_ee;costs=trial_costs
                    pcm=trial;after=measured;result=candidate;accepted+=1;pass_changes+=1
                    old_patch=co[start:patch_end].copy()
                    # The shortlisted neighbours were based on the old vector.
                    # Accept at most one change per frame, then refresh next sweep.
                    break
                co[start:patch_end]=old_patch
            co[start:patch_end]=old_patch
        if not pass_changes:break
    for candidate in set((bytes(blob),result,raw)):
        received=decoder.decode_one_s16(candidate,n)
        if received is None or not np.array_equal(received,compact.decode_model(candidate)):
            raise AssertionError('Joint LPC result native/model mismatch')
        if not np.array_equal(decoder.decode_one(candidate,n),pwm_duties(received)):
            raise AssertionError('Joint LPC result native PWM mismatch')
    if not np.array_equal(decoder.decode_one_s16(result,n),pcm):raise AssertionError('Joint LPC snapshot mismatch')
    if result[12:16]!=blob[12:16]:raise AssertionError('Joint LPC changed frozen header filters')
    report={'proposal':'compact_joint_lpc_excitation','samples':n,'profile':profile,
        'baseline_bytes':len(blob),'file_bytes':len(result),'max_file_bytes':int(max_bytes),
        'baseline':before,'selected':after,'raw_best_sse':quality(ref,decoder.decode_one_s16(raw,n)),
        'raw_file_bytes':len(raw),'raw_stream_sha256':hashlib.sha256(raw).hexdigest(),
        'changed_spectral_indices':int(np.count_nonzero(sp!=np.asarray(spectra,np.int64))),
        'changed_excitation_fields':int(np.count_nonzero(pp!=np.asarray(params,np.int64))+np.count_nonzero(ii!=np.asarray(pulses,np.int64))+np.count_nonzero(ee!=np.asarray(extras,np.int64))),
        'spectral_trials':spectral_trials,'excitation_trials':excitation_trials,
        'full_metric_evaluations':full_evaluations,'accepted_frames':accepted,'cap_rejections':cap_rejections,
        'frame_limit':int(frame_limit),'spectral_candidates':int(spectral_candidates),'lookahead':int(lookahead),
        'excitation_horizon':int(excitation_horizon),'passes':int(passes),'refit':refit,
        'header_filters_exact':True,'native_model_pwm_exact':True,'checkpoints':checkpoints,
        'seconds':time.perf_counter()-started}
    return result,pcm,report,raw


def main():
    import soundfile as sf
    from batch_decoder import BatchSession
    from output_paths import protect_outputs
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference',type=Path);parser.add_argument('input',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--max-bytes',type=int,required=True)
    parser.add_argument('--preset',choices=tuple(SEARCH_PRESETS),default='default',
                        help='Named host search settings; explicit options override the preset')
    parser.add_argument('--frames',type=int,help='Override preset anchor count')
    parser.add_argument('--spectral-candidates',type=int,help='Override preset spectral finalists')
    parser.add_argument('--lookahead',type=int,choices=(320,640,1280),help='Override preset screening samples')
    parser.add_argument('--excitation-horizon',type=int,choices=(80,160),help='Override preset refit samples')
    parser.add_argument('--passes',type=int,choices=(1,2),help='Override preset pass count')
    args=parser.parse_args();paths=[args.output/'audio.l4hy',args.output/'decoded.wav',args.output/'raw.l4hy',args.output/'report.json']
    settings=SEARCH_PRESETS[args.preset].copy()
    for argument,option in (('frames','frame_limit'),('spectral_candidates','spectral_candidates'),
                            ('lookahead','lookahead'),('excitation_horizon','excitation_horizon'),('passes','passes')):
        value=getattr(args,argument)
        if value is not None:settings[option]=value
    protect_outputs([args.reference,args.input],paths);ref,rate=sf.read(args.reference,dtype='int16')
    if rate!=8000:raise ValueError('Reference must be8kHz')
    with BatchSession('batch',speech=True,speech_compact=True,compact_only=True) as decoder:
        result,pcm,report,raw=refine(ref,args.input.read_bytes(),decoder,args.max_bytes,**settings)
    report['search_preset']=args.preset
    args.output.mkdir(parents=True,exist_ok=True);paths[0].write_bytes(result);paths[2].write_bytes(raw)
    sf.write(paths[1],pcm,8000,subtype='PCM_16');paths[3].write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('profile','file_bytes','accepted_frames','spectral_trials','seconds')}))


if __name__=='__main__':main()
