"""Bounded joint base/extra-pulse refinement for existing v5 speech streams.

Keep spectra and header filters fixed, preserve the input as rollback, and
optionally spend a larger complete-stream budget on additional existing v5
extra pulses. Selected output obeys full-reference PCM/PWM SSE/STOI floors;
raw best-SSE proposals remain available for listening to metric tradeoffs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from numba import njit
import speech_compact as compact
from speech_rate_allocation import bit_accounting, extra_capacity
from enhance_speech_compact import advance, sse
from refine_speech_compact import quality, no_regression
from q0_model import coefficient_trace, table
from standard_metrics import pwm_duties
from wav_lpc import pack_frames


@njit(cache=True)
def optimize_group(reference,co,params,pulses,extras,steps,pre,bright,profile,
                   start,end,horizon,hist,dd,cc,ring,capacity):
    parameters=params.copy();innovations=pulses.copy();added=extras.copy()
    h=hist.copy();qring=ring.copy();evaluations=0;changed=0
    active=np.count_nonzero(added[:,1])
    for at in range(start,end,40):
        stop=min(len(reference),at+horizon);target=reference[at:stop]
        if at%160==0:
            index=at//160;original=parameters[index].copy();best=original.copy()
            out,_,_,_,_=advance(co,parameters,innovations,added,steps,pre,bright,at,stop,h,dd,cc,qring)
            best_loss=sse(target,out);evaluations+=1
            for field in range(3):
                for delta in (-1,1):
                    proposal=original.copy()
                    proposal[field]=max(0,min(31,original[0]+delta)) if field==0 else max(18,min(145,original[1]+delta)) if field==1 else max(0,min(14,original[2]+delta*2))
                    parameters[index]=proposal
                    out,_,_,_,_=advance(co,parameters,innovations,added,steps,pre,bright,at,stop,h,dd,cc,qring)
                    trial=sse(target,out);evaluations+=1
                    if trial<best_loss:best_loss=trial;best=proposal.copy()
            parameters[index]=best
            if np.any(best!=original):changed+=1
        # Extra-pulse proposals start at the complete40-sample chunk boundary,
        # before either base pulse has changed its synthesis history.
        index=at//40;original=added[index].copy();best=original.copy()
        out,_,_,_,_=advance(co,parameters,innovations,added,steps,pre,bright,at,stop,h,dd,cc,qring)
        best_loss=sse(target,out);evaluations+=1
        positions=np.zeros(40,np.uint8);valid=min(40,len(reference)-at)
        if original[1]:
            for offset in range(-2,3):
                pos=original[0]+offset
                if 0<=pos<valid:positions[pos]=1
        positions[innovations[at//20,0]]=1
        if valid>20:positions[20+innovations[at//20+1,0]]=1
        # Largest current PCM error supplies another bounded proposal location;
        # exact synthesis, not this heuristic, decides whether it is useful.
        peak=0;peakerror=-1
        for j in range(valid):
            error=abs(np.int64(target[j])-np.int64(out[j]))
            if error>peakerror:peakerror=error;peak=j
        positions[peak]=1
        amplitudes=np.zeros(16,np.uint8)
        for amp in (-8,-4,-2,-1,0,1,2,4,7):amplitudes[amp+8]=1
        for delta in (-2,-1,1,2):amplitudes[max(-8,min(7,original[1]+delta))+8]=1
        for pos in range(valid):
            if not positions[pos]:continue
            for amp in range(-8,8):
                if not amplitudes[amp+8] or amp and not original[1] and active>=capacity:continue
                added[index,0]=pos if amp else -1;added[index,1]=amp
                trialout,_,_,_,_=advance(co,parameters,innovations,added,steps,pre,bright,at,stop,h,dd,cc,qring)
                trial=sse(target,trialout);evaluations+=1
                if trial<best_loss:best_loss=trial;best=added[index].copy()
        added[index]=best
        active+=int(best[1]!=0)-int(original[1]!=0)
        if np.any(best!=original):changed+=1
        for half in range(2):
            begin=at+half*20
            if begin>=end:break
            stop=min(len(reference),begin+horizon);target=reference[begin:stop]
            pi=begin//20;original=innovations[pi].copy();best=original.copy()
            out,_,_,_,_=advance(co,parameters,innovations,added,steps,pre,bright,begin,stop,h,dd,cc,qring)
            best_loss=sse(target,out);evaluations+=1
            for pos in range(min(20,len(reference)-begin)):
                if profile==4 and (pos==2 or pos==7 or pos==12 or pos==17):continue
                # All legal amplitudes for profile6, both signs for profile4.
                for amp in range(-8,9):
                    if profile==4:
                        if amp not in (-8,8):continue
                    elif amp>7:continue
                    innovations[pi,0]=pos;innovations[pi,1]=amp
                    trialout,_,_,_,_=advance(co,parameters,innovations,added,steps,pre,bright,begin,stop,h,dd,cc,qring)
                    trial=sse(target,trialout);evaluations+=1
                    if trial<best_loss:best_loss=trial;best=innovations[pi].copy()
            innovations[pi]=best
            if np.any(best!=original):changed+=1
            _,h,dd,cc,qring=advance(co,parameters,innovations,added,steps,pre,bright,begin,
                                   min(end,begin+20),h,dd,cc,qring)
    return parameters,innovations,added,evaluations,changed


def refine(reference,blob,decoder,max_bytes,*,horizon=160,group_samples=1280,passes=1):
    """Return (selected stream, PCM16, report, raw best-SSE stream).

    The raw alternative can trade off intelligibility or PWM. Its existence is
    not an adoption decision; preserve it for explicit comparison/listening.
    """
    if (any(isinstance(value,bool) or not isinstance(value,int) for value in (horizon,passes,group_samples)) or
            horizon not in (80,160,320) or passes not in (1,2) or not 160<=group_samples<=2560 or group_samples%160):
        raise ValueError('Expected supported bounded search settings')
    if isinstance(max_bytes,bool) or int(max_bytes)!=max_bytes or not len(blob)<=max_bytes<=65535:
        raise ValueError('Expected complete file cap >= input size and <=65535')
    ref=np.asarray(reference)
    if ref.ndim!=1 or ref.dtype.kind not in 'iu' or np.any(ref<-32768) or np.any(ref>32767):
        raise ValueError('Expected mono PCM16 reference')
    n,profile,spectra,params,pulses,pre,bright,extras=compact.unpack(blob)
    if len(ref)!=n:raise ValueError('Reference/stream sample count mismatch')
    started=time.perf_counter();shift=5 if profile==4 else 4
    vectors=[[(v<<shift)+(1<<(shift-1)) for v in row] for row in spectra for _ in range(2)]
    co=coefficient_trace(pack_frames(vectors[:(n+159)//160]),n);steps=table('scale_table.inc')
    parameters=np.asarray(params,np.int64);innovations=np.asarray(pulses,np.int64);added=np.asarray(extras,np.int64)
    zero_h=np.zeros(10,np.int64);zero_ring=np.zeros(256,np.int64)
    def render(pp,ii,ee):return advance(co,pp,ii,ee,steps,pre,bright,0,n,zero_h,0,0,zero_ring)[0]
    pcm=render(parameters,innovations,added);native=decoder.decode_one_s16(blob,n)
    if native is None or not np.array_equal(native,pcm) or not np.array_equal(pcm,compact.decode_model(blob)):
        raise AssertionError('Joint baseline snapshot/native/model mismatch')
    before=quality(ref,pcm);after=before;result=bytes(blob);raw=bytes(blob);raw_sse=before['pcm16']['error_energy']
    layout=bit_accounting(spectra,profile)
    capacity=extra_capacity(layout['spectrum_bits'],len(spectra),profile,int(max_bytes),len(extras))
    if capacity<np.count_nonzero(added[:,1]):raise AssertionError('Existing extras exceed derived capacity')
    evaluations=0;accepted=0;checks=[]
    for pass_index in range(passes if before['pcm16']['error_energy'] else 0):
        pass_accepted=0
        for start in range(0,n,group_samples):
            end=min(n,start+group_samples)
            _,h,dd,cc,ring=advance(co,parameters,innovations,added,steps,pre,bright,0,start,zero_h,0,0,zero_ring)
            pp,ii,ee,count,changed=optimize_group(ref.astype(np.int64),co,parameters,innovations,added,
                steps,pre,bright,profile,start,end,horizon,h,dd,cc,ring,capacity)
            evaluations+=int(count)
            if not changed:continue
            trial=render(pp,ii,ee);loss=int(sse(ref,trial))
            if loss>=after['pcm16']['error_energy']:continue
            candidate,meta=compact.pack(n,profile,spectra,pp,ii,pre,bright,extras=ee.tolist())
            if len(candidate)>max_bytes:raise AssertionError('Joint complete stream cap failed')
            measured=quality(ref,trial);allowed=no_regression(measured,before)
            checks.append({'pass':pass_index,'start_sample':start,'stop_sample':end,
                           'file_bytes':len(candidate),'extra_pulses':meta['extra_pulses'],
                           'metrics':measured,'conservative_floors_passed':bool(allowed)})
            if loss<raw_sse:raw=candidate;raw_sse=loss
            if allowed:
                parameters=pp;innovations=ii;added=ee;pcm=trial;after=measured;result=candidate
                accepted+=1;pass_accepted+=1
        if not pass_accepted:break
    for candidate in set((bytes(blob),result,raw)):
        receiver=decoder.decode_one_s16(candidate,n)
        if receiver is None or not np.array_equal(receiver,compact.decode_model(candidate)):
            raise AssertionError('Joint result native/model mismatch')
        if not np.array_equal(decoder.decode_one(candidate,n),pwm_duties(receiver)):
            raise AssertionError('Joint result native PWM mismatch')
    if not np.array_equal(decoder.decode_one_s16(result,n),pcm):raise AssertionError('Joint selected snapshot mismatch')
    if compact.unpack(result)[2]!=spectra or result[12:16]!=blob[12:16]:
        raise AssertionError('Joint result changed frozen spectrum/filters')
    report={'proposal':'compact_joint_excitation','profile':profile,'samples':n,'baseline_bytes':len(blob),
            'file_bytes':len(result),'max_file_bytes':int(max_bytes),'extra_capacity':int(capacity),
            'baseline':before,'selected':after,'raw_best_sse':quality(ref,decoder.decode_one_s16(raw,n)),
            'raw_file_bytes':len(raw),'raw_stream_sha256':hashlib.sha256(raw).hexdigest(),
            'accepted_groups':accepted,'candidate_evaluations':evaluations,'spectra_filters_exact':True,
            'native_model_pwm_exact':True,'horizon':horizon,'group_samples':group_samples,'passes':passes,
            'checkpoints':checks,'seconds':time.perf_counter()-started}
    return result,pcm,report,raw


def main():
    import soundfile as sf
    from batch_decoder import BatchSession
    from output_paths import protect_outputs
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference',type=Path);parser.add_argument('input',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--max-bytes',type=int,required=True);parser.add_argument('--horizon',type=int,default=160,choices=(80,160,320))
    parser.add_argument('--group-samples',type=int,default=1280);parser.add_argument('--passes',type=int,default=1,choices=(1,2))
    args=parser.parse_args();paths=[args.output/'audio.l4hy',args.output/'decoded.wav',args.output/'raw.l4hy',args.output/'report.json']
    protect_outputs([args.reference,args.input],paths);ref,rate=sf.read(args.reference,dtype='int16')
    if rate!=8000:raise ValueError('Reference must be8kHz')
    with BatchSession('batch',speech=True,speech_compact=True,compact_only=True) as decoder:
        result,pcm,report,raw=refine(ref,args.input.read_bytes(),decoder,args.max_bytes,
            horizon=args.horizon,group_samples=args.group_samples,passes=args.passes)
    args.output.mkdir(parents=True,exist_ok=True);paths[0].write_bytes(result);paths[2].write_bytes(raw)
    sf.write(paths[1],pcm,8000,subtype='PCM_16');paths[3].write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('profile','file_bytes','accepted_groups','candidate_evaluations','seconds')}))


if __name__=='__main__':main()
