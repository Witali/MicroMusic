"""Bounded host-only parameter proposals for existing speech v5 streams.

The scalar energy estimate only proposes a narrow scale interval. At low
levels, especially with the mandatory +/-8 pulse of profile4, useful smaller
nonzero scales may lie outside that interval. Probe three additional lower
levels. A second proposal uses the existing pre-emphasis header at0.75
instead of0.85 and reruns the ordinary encoder. Retain proposals only after
complete original-level PCM and actual PWM checks. The input is an exact
rollback. The lower-scale kernel is adapted from speech_v4.search and imports
its unchanged integer synthesis helper; no decoder code is copied or changed.
"""
from __future__ import annotations

import time
import numpy as np
from numba import njit
from speech_v4 import search_block, pack as pack_v4, encode
from speech_compact import unpack, decode_model
from refine_speech_v4 import refine
from enhance_speech_compact import enhance
from q0_model import coefficient_trace, table
from wav_lpc import pack_frames
from standard_metrics import error_metrics, pwm_pcm16, pwm_duties
from level_policy import preserves_activity


@njit(cache=True)
def lower_scale_search(reference, co, steps, pre, profile):
    """Same integer synthesis and pitch proposals; up to three extra scales."""
    n=len(reference);params=np.zeros((n//160,3),np.int64)
    pulses=np.zeros((n//20,2),np.int64);output=np.empty(n,np.int16)
    h=np.zeros(10,np.int64);ring=np.zeros(256,np.int64);dd=cc=0
    emphasized=np.zeros(n,np.float64);residual=np.zeros(n,np.float64)
    for j in range(n):
        emphasized[j]=reference[j]/2-(pre*(reference[j-1]/2) if j else 0)/16384
        residual[j]=emphasized[j]
        for k in range(10):
            if j>k:residual[j]+=co[j,k]*emphasized[j-k-1]/4096
    evaluations=0
    for bi in range(n//160):
        start=bi*160;end=start+160;power=np.mean(residual[start:end]**2)
        desired=max(1.,np.sqrt(power*20)/8)
        center=max(1,min(31,int(np.rint((128+16*np.log2(desired/16.384))/8))))
        lag=18;pitchscore=-1.;pitchgain=0
        for cand in range(18,146):
            dot=energy=0.
            for j in range(start,end):
                v=residual[j-cand] if j>=cand else 0.
                dot+=v*residual[j];energy+=v*v
            score=max(0.,dot)**2/(energy+1.)
            if score>pitchscore:
                pitchscore=score;lag=cand
                pitchgain=min(14,max(0,int(np.rint(8*dot/(energy+1)))*2))
        low=max(0,center-2);high=min(31,center+2)
        scales=np.empty(8,np.int64);count=0
        # Retain the old proposal order before the extra probes. Ties do not
        # gratuitously change the reference choice.
        for scale in range(low,high+1):scales[count]=scale;count+=1
        for probe in (max(0,center-4),max(0,center-6),0):
            duplicate=False
            for i in range(count):
                if scales[i]==probe:duplicate=True
            if not duplicate:scales[count]=probe;count+=1
        best=np.inf;bestscale=0;bestgain=0
        for i in range(count):
            scale=scales[i]
            for choice in range(3):
                gain=0 if choice==0 else pitchgain if choice==1 else 14
                if choice and not gain:continue
                err,_,_,_,_,_,_=search_block(reference[start:end],co[start:end],h,dd,cc,ring,start,
                    pre,steps[scale*8],lag,gain,profile)
                evaluations+=1
                if err<best:best=err;bestscale=scale;bestgain=gain
        _,h,dd,cc,ring,pp,pcm=search_block(reference[start:end],co[start:end],h,dd,cc,ring,start,
            pre,steps[bestscale*8],lag,bestgain,profile)
        params[bi]=np.asarray([bestscale,lag,bestgain]);pulses[bi*8:bi*8+8]=pp
        output[start:end]=pcm
    return params,pulses,output,evaluations


def quality(reference,pcm):
    return {'pcm16':error_metrics(reference,pcm,True),
            'pwm8':error_metrics(reference,pwm_pcm16(pcm),True),
            'activity_preserved':preserves_activity(reference,pcm)}


def preserves_quality(baseline,candidate):
    """Unavailable baseline STOI imposes no invented intelligibility floor."""
    for domain in ('pcm16','pwm8'):
        old,new=baseline[domain],candidate[domain]
        if new['error_energy']>old['error_energy']:return False
        if any(value is not None and not np.isfinite(value) for value in (old['stoi'],new['stoi'])):
            return False
        if old['stoi'] is not None and (new['stoi'] is None or new['stoi']<old['stoi']-1e-12):
            return False
    return candidate['pcm16']['error_energy']<baseline['pcm16']['error_energy']


def optimize(reference,baseline_blob,decoder,max_bytes,*,enabled=True,
             proposals=('pre75','lower_scales'),refinement_passes=2,
             refinement_horizon=320):
    """Return (stream, PCM16, report), retaining the exact input on rejection.

    At most two rebuilds, each with the selected local refinement and one bounded
    extra innovation stage, are tried. The lower-scale proposal retains the
    spectrum; pre75 deliberately re-analyzes it. The format is unchanged.
    Nonzero-brightness inputs keep their exact rollback because the proposal
    kernel deliberately models the encoder's original zero-brightness path.
    """
    started=time.perf_counter();ref=np.asarray(reference)
    if ref.ndim!=1 or ref.dtype.kind not in 'iu' or not 1<=len(ref)<=64000 or np.any(ref<-32768) or np.any(ref>32767):
        raise ValueError('Expected 1..64000 mono PCM16 samples')
    if isinstance(max_bytes,bool) or int(max_bytes)!=max_bytes or not 22<=max_bytes<=65535:
        raise ValueError('Expected complete-file cap in 22..65535')
    if not isinstance(proposals,(tuple,list)) or len(proposals)>2 or any(p not in ('pre75','lower_scales') for p in proposals) or len(set(proposals))!=len(proposals):
        raise ValueError('Expected at most two distinct supported proposal names')
    if refinement_passes not in (1,2,3,4) or refinement_horizon not in (40,80,160,320,640):
        raise ValueError('Expected supported bounded refinement settings')
    n,profile,spectra,params,pulses,pre,bright,extras=unpack(baseline_blob)
    if len(ref)!=n or len(baseline_blob)>max_bytes:
        raise ValueError('Baseline sample count/cap mismatch')
    pcm=decoder.decode_one_s16(baseline_blob,n)
    if pcm is None or not np.array_equal(pcm,decode_model(baseline_blob)):
        raise AssertionError('Baseline native/model mismatch')
    if not np.array_equal(decoder.decode_one(baseline_blob,n),pwm_duties(pcm)):
        raise AssertionError('Baseline native/PWM mismatch')
    initial=quality(ref,pcm);selected=initial;result=baseline_blob
    report={'proposal':'bounded_speech_v5','trials':0,'accepted':False,'checkpoints':[],
            'spectra_exact':True,'decoder_modified':False,'native_model_exact':True,
            'max_bytes':int(max_bytes),'baseline':initial,'selected':initial,
            'refinement_passes':refinement_passes,'refinement_horizon':refinement_horizon}
    if not enabled:report['skip_reason']='explicitly_disabled'
    elif bright:report['skip_reason']='nonzero_brightness_not_modeled_by_proposals'
    elif not initial['pcm16']['error_energy']:report['skip_reason']='perfect_baseline'
    elif not proposals:report['skip_reason']='no_proposals_requested'
    if enabled and not bright and initial['pcm16']['error_energy']:
        for proposal in proposals:
            if not selected['pcm16']['error_energy']:break
            count=None
            if proposal=='lower_scales':
                shift=5 if profile==4 else 4
                vectors=[[(v<<shift)+(1<<(shift-1)) for v in row] for row in spectra for _ in range(2)]
                padded=np.pad(ref.astype(np.int64),(0,(-n)%320))
                co=coefficient_trace(pack_frames(vectors),len(padded))
                parameters,innovations,expected,count=lower_scale_search(padded,co,table('scale_table.inc'),pre,profile)
                candidate=pack_v4(n,profile,spectra,parameters,innovations,pre,bright)
                raw=decoder.decode_one_s16(candidate,n)
                if raw is None or not np.array_equal(raw,expected[:n]):
                    raise AssertionError('Lower-scale snapshot/native mismatch')
            else:
                candidate,_,_=encode(ref,profile,decoder,pre=12288,bandwidth=.97)
            candidate,_,_=refine(ref,candidate,decoder,passes=refinement_passes,horizon=refinement_horizon)
            report['trials']+=1
            try:
                candidate,actual,details=enhance(ref,candidate,decoder,int(max_bytes))
            except ValueError as error:
                if str(error)!='Exact compact baseline does not fit file cap':raise
                report['checkpoints'].append({'proposal':proposal,'accepted':False,
                    'rejection':'candidate_no_fit','quality':None,'file_bytes':None,
                    'block_evaluations':None if count is None else int(count),
                    'extra_full_evaluations':0})
                continue
            if not np.array_equal(actual,decode_model(candidate)) or not np.array_equal(decoder.decode_one(candidate,n),pwm_duties(actual)):
                raise AssertionError('Candidate native/model/PWM mismatch')
            measured=quality(ref,actual)
            accepted=(len(candidate)<=max_bytes and measured['activity_preserved']
                      and preserves_quality(initial,measured)
                      and measured['pcm16']['error_energy']<selected['pcm16']['error_energy'])
            report['checkpoints'].append({'proposal':proposal,'accepted':bool(accepted),
                'quality':measured,'file_bytes':len(candidate),'block_evaluations':None if count is None else int(count),
                'extra_full_evaluations':details['full_evaluations']})
            if accepted:
                result,pcm,selected=candidate,actual,measured;report['accepted']=True
                report['selected_proposal']=proposal
                report['spectra_exact']=proposal=='lower_scales'
    report.update(selected=selected,file_bytes=len(result),
        retained_baseline=result==baseline_blob,
        selected_admissible=bool(selected['activity_preserved'] and selected['pcm16']['error_energy']<=selected['pcm16']['reference_energy']),
        seconds=time.perf_counter()-started)
    report['status']='no_fit' if not report['selected_admissible'] else 'accepted' if report['accepted'] else 'retained_baseline'
    return result,pcm,report
