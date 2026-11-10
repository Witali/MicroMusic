"""Offline sparse80 beam decisions and fixed-size filter refinement.

The beam kernel adapts this project's research/low-bitrate-speech-2026-11-02/
beam_innovations.py, adding exact partial-tail accounting. Metadata/spectra and
the seven-bit innovation alphabet remain fixed. No receiver change is needed.
"""
from __future__ import annotations

import time
import struct
import numpy as np
from numba import njit
import speech_sparse80 as sparse
from speech_v9 import repack
from encode_low_bitrate_speech import trial_group
from q0_model import coefficient_trace,table,clamp
from wav_lpc import pack_frames
from refine_sparse80 import refine,voice_floor
from refine_speech_compact import quality,no_regression
from speech_noise_objective import NoiseObjective
from voice_character import track_pitch,compare_voice
from standard_metrics import pwm_duties,pwm_pcm16


@njit(cache=True)
def saturation_trial(target,co,hist,dd,cc,ring,start,step,lag,gain,position,amplitude,pre,valid_samples):
    """Exact synthesis with a proposal-only penalty for internal clipping.

    The penalty never changes arithmetic or reported decoded audio. It merely
    gives a separate beam a reason to avoid saturating LPC/deemphasis states.
    """
    history=hist.copy();qring=ring.copy();output=np.zeros(80,np.int16);loss=np.int64(0)
    played=max(0,min(80,valid_samples-start))
    for j in range(played):
        at=start+j;q=min(31,max(-32,(gain*qring[(at-lag)&255]+8)>>4))
        q=min(31,max(-32,q+(amplitude if j==position else 0)));qring[at&255]=q
        acc=np.int64(0)
        for k in range(10):acc+=(co[at,k]*history[k])>>12
        raw=q*step-acc;predicted=clamp(raw)
        if raw<-32767 or raw>32767:loss+=np.int64(1)<<42
        for k in range(9,0,-1):history[k]=history[k-1]
        history[0]=predicted;raw=predicted+((pre*dd)>>14);dd=clamp(raw)
        if raw<-32767 or raw>32767:loss+=np.int64(1)<<42
        cc=clamp(dd,-16384,16384);output[j]=clamp(cc*2,-32768,32767)
        delta=np.int64(output[j])-target[at];loss+=delta*delta
        if output[j]<=-32768 or output[j]>=32767:loss+=np.int64(1)<<42
    return loss,history,dd,cc,qring,output


@njit(cache=True)
def beam(reference,co,parameters,steps,pre,width,clip_guard,valid_samples):
    groups=len(reference)//80
    history=np.zeros((width,10),np.int64);ring=np.zeros((width,256),np.int64)
    dd=np.zeros(width,np.int64);cc=np.zeros(width,np.int64)
    costs=np.zeros(width,np.int64);paths=np.zeros((width,groups,2),np.int64)
    active=1;evaluations=0
    for group in range(groups):
        nh=np.zeros((width,10),np.int64);nr=np.zeros((width,256),np.int64)
        nd=np.zeros(width,np.int64);nc=np.zeros(width,np.int64)
        loss=np.full(width,np.int64(9223372036854775807),np.int64)
        choices=np.zeros((width,groups,2),np.int64);count=0
        at=group*80;scale,lag,gain=parameters[at//320]
        if at>=valid_samples:
            # Unplayed packets still need legal fields in the v8 bridge.
            paths[:,group,0]=0;paths[:,group,1]=-8
            continue
        for parent in range(active):
            for code in range(64):
                position=code+((code+2)>>2)
                for sign in range(2):
                    amplitude=7 if sign else -8
                    if clip_guard==2:
                        error,h,d,c,q,_=saturation_trial(reference,co,history[parent],dd[parent],cc[parent],
                            ring[parent],at,steps[scale*8],lag,gain,position,amplitude,pre,valid_samples)
                    else:
                        error,h,d,c,q,_=trial_group(reference,co,history[parent],dd[parent],cc[parent],
                            ring[parent],at,80,steps[scale*8],lag,gain,position,amplitude,pre,clip_guard,valid_samples)
                    evaluations+=1;total=costs[parent]+error;slot=width
                    for rank in range(width):
                        if total<loss[rank]:slot=rank;break
                    if slot==width:continue
                    for rank in range(width-1,slot,-1):
                        loss[rank]=loss[rank-1];nh[rank]=nh[rank-1];nr[rank]=nr[rank-1]
                        nd[rank]=nd[rank-1];nc[rank]=nc[rank-1];choices[rank]=choices[rank-1]
                    loss[slot]=total;nh[slot]=h;nr[slot]=q;nd[slot]=d;nc[slot]=c
                    choices[slot]=paths[parent];choices[slot,group,0]=position;choices[slot,group,1]=amplitude
                    count=min(width,count+1)
        history,ring,dd,cc,costs,paths,active=nh,nr,nd,nc,loss,choices,count
    return paths[0],evaluations


def enhance(reference,blob,decoder,*,speech=True):
    """Preserve the complete byte budget and numerical quality floors.

    The input is a protected rollback. Six finite beam proposals compete with
    header refinement; neither this search nor its proxies prove audibility.
    """
    start=time.perf_counter();original=bytes(blob);short=original[:2]==b'L9'
    header,pcm,header_report=refine(reference,original,decoder,speech=speech)
    legacy=repack(original,8)[0] if short else original
    n,spectra,parameters,pulses,pre,bright=sparse.unpack(legacy)
    target=np.asarray(reference);track=track_pitch(target);objective=NoiseObjective(target,track.period)
    initial=header_report['baseline'];base_voice=header_report['baseline_voice'];base_clip=header_report['baseline_clipped']
    best=header;best_pcm=pcm;best_score=header_report['selected_score'];rows=[]
    best_beam=None;best_beam_score=float('inf');raw_beam=None;raw_beam_error=float('inf')
    seen={original,header};original_pcm=sparse.decode_model(legacy)
    def consider(candidate,origin):
        nonlocal best,best_pcm,best_score,best_beam,best_beam_score,raw_beam,raw_beam_error
        encoded=repack(candidate)[0] if short else candidate
        if len(encoded)>len(original):
            rows.append(dict(origin=origin,admissible=False,reason='complete_byte_budget'));return
        if encoded in seen:
            rows.append(dict(origin=origin,admissible=False,reason='duplicate'));return
        seen.add(encoded)
        actual=sparse.decode_model(candidate);pwm=pwm_pcm16(actual)
        metrics=quality(target,actual,speech)
        voice=[compare_voice(target,x,reference_track=track) for x in (actual,pwm)]
        clipped=[int(np.count_nonzero((actual<=-32768)|(actual>=32767))),int(np.count_nonzero((pwm<=-32768)|(pwm>=32512)))]
        score=float(np.mean([objective.voice_objective(x)+objective(x) for x in (actual,pwm)]))
        allowed=(np.isfinite(score) and no_regression(metrics,initial) and
                 all(voice_floor(a,b) for a,b in zip(voice,base_voice)) and all(a<=b for a,b in zip(clipped,base_clip)))
        rows.append(dict(origin=origin,admissible=bool(allowed),score=score,file_bytes=len(encoded),metrics=metrics,voice=voice,clipped=clipped))
        if origin.get('beam_width') and metrics['pwm8']['error_energy']<raw_beam_error:
            raw_beam=candidate;raw_beam_error=metrics['pwm8']['error_energy']
        if allowed and score<best_beam_score:
            best_beam=candidate;best_beam_score=score
        if allowed and score<best_score-1e-12:
            expanded=sparse.expand(candidate)
            if not np.array_equal(decoder.decode_one_s16(expanded,n),actual) or not np.array_equal(decoder.decode_one(expanded,n),pwm_duties(actual)):
                raise AssertionError('Beam/model/native output differs')
            best=encoded;best_pcm=actual;best_score=score
    if not bright:
        padded=np.pad(target.astype(np.int64),(0,len(spectra)*320-n))
        vectors=[[(int(v)<<4)+8 for v in row] for row in spectra for _ in range(2)]
        co=coefficient_trace(pack_frames(vectors),len(padded))
        for guard in (0,1,2):
            for width in (2,4):
                innovation,trials=beam(padded,co,np.asarray(parameters,np.int64),table('scale_table.inc'),pre,width,guard,n)
                candidate=sparse.pack(n,spectra,parameters,innovation.tolist(),pre,bright)
                consider(candidate,dict(beam_width=width,clipping_guard=guard,position_sign_trials=int(trials)))
                # A beam/filter pair can pass floors even when either change
                # alone does not. Transfer the independently selected header
                # before spending another full filter-search budget.
                if header_report['accepted']:
                    pair=header_report['output_header']
                    filtered=candidate[:12]+struct.pack('<HH',pair['preQ14'],pair['brightQ14'])+candidate[16:]
                    consider(filtered,dict(beam_width=width,clipping_guard=guard,transferred_header=True))
        if raw_beam is not None:
            # The full beam may trade a good local change against a bad one.
            # Rank up to four 320-sample patches by its local PWM SSE gain;
            # reconstruct and admit each patch over the COMPLETE output.
            # Ranking is heuristic because pitch/LPC state crosses boundaries.
            _,_,_,raw_pulses,_,_=sparse.unpack(raw_beam)
            raw_pcm=sparse.decode_model(raw_beam)
            improvement=(target.astype(np.int64)-pwm_pcm16(original_pcm).astype(np.int64))**2-(target.astype(np.int64)-pwm_pcm16(raw_pcm).astype(np.int64))**2
            gains=[int(np.sum(improvement[a:a+320])) for a in range(0,n,320)]
            order=sorted((i for i,gain in enumerate(gains) if gain>0),key=lambda i:(-gains[i],i))[:4]
            for index in order:
                patched=list(pulses);patched[index*4:index*4+4]=raw_pulses[index*4:index*4+4]
                candidate=sparse.pack(n,spectra,parameters,patched,pre,bright)
                consider(candidate,dict(local_beam_patch=index,groups=4))
                if header_report['accepted']:
                    pair=header_report['output_header']
                    filtered=candidate[:12]+struct.pack('<HH',pair['preQ14'],pair['brightQ14'])+candidate[16:]
                    consider(filtered,dict(local_beam_patch=index,groups=4,transferred_header=True))
        if best_beam is not None:
            # Refine the best admissible pulse proposal even when it has not
            # yet overtaken the header-only incumbent.
            filtered,_,_=refine(target,best_beam,decoder,speech=speech)
            consider(filtered,dict(beam_then_filters=True))
    # Verify even the rollback/header-only result through the independent C path.
    expanded=sparse.expand(repack(best,8)[0] if short else best)
    if not np.array_equal(decoder.decode_one_s16(expanded,n),best_pcm) or not np.array_equal(decoder.decode_one(expanded,n),pwm_duties(best_pcm)):
        raise AssertionError('Selected/native output differs')
    report=dict(schema='lpx-sparse80-beam-filter-v1',samples=n,input_bytes=len(original),selected_bytes=len(best),
        decoder_changed=False,native_pcm_pwm_exact=True,accepted=best!=original,
        baseline_score=header_report['baseline_score'],selected_score=best_score,
        header_refinement=header_report,beam_alternatives=rows,seconds=time.perf_counter()-start)
    return best,best_pcm,report
