"""Experimental, opt-in sparse80 pulse-neighbor search on the host.

Keep spectra, pitch/scale metadata, filters and the seven-bit pulse alphabet.
Rank local pulse proposals with exact snapshot synthesis, then check complete
PCM/PWM output against the predecessor. A selected change must also change
actual PWM bytes and improve its voice/noise proxy; PCM-only gains roll back.

Not admitted as a perceptual quality improvement: listening to the public
Chego tuning clip found almost no improvement and higher-frequency rasp in a
preceding local-neighbor prototype despite its lower aggregate proxy scores.
Keep this tool opt-in. Fixed upper-band and burst guards are enabled by default;
their numerical bounds are not a perceptual-quality validation.
"""
from __future__ import annotations

import time
from numbers import Integral

import numpy as np
from numba import njit
import speech_compact as compact
import speech_sparse80 as sparse
from speech_v9 import repack
from enhance_speech_compact import advance
from q0_model import coefficient_trace,table
from wav_lpc import pack_frames
from refine_speech_compact import quality,no_regression
from refine_sparse80 import voice_floor
from voice_character import track_pitch,compare_voice
from speech_noise_objective import NoiseObjective
from standard_metrics import pwm_duties,pwm_pcm16


def _band_context(reference):
    source=np.asarray(reference)
    if (source.ndim!=1 or not len(source) or source.dtype.kind not in 'iu'
            or np.any(source<-32768) or np.any(source>32767)):
        raise ValueError('Expected a nonempty mono PCM16 reference')
    frame=640;hop=160;n=len(source);starts=list(range(0,n,hop))
    valid=np.minimum(frame,n-np.asarray(starts));windows=np.zeros((len(starts),frame))
    for i,count in enumerate(valid):
        # A half-sample Hann stays nonzero at both ends, including a one-sample
        # tail. Padding is excluded from the window-power normalization.
        windows[i,:count]=.5-.5*np.cos(2*np.pi*(np.arange(count)+.5)/count)
    norm=frame*np.sum(windows*windows,axis=1)
    frequencies=np.fft.rfftfreq(frame,1/8000)
    masks=((frequencies>=1500)&(frequencies<2500),(frequencies>=2500)&(frequencies<=4000))
    context=dict(source=source.astype(np.float64),frame=frame,hop=hop,starts=starts,valid=valid,
                 windows=windows,norm=norm,masks=masks)
    context['source_power']=_band_power(context,context['source'])
    return context


def _band_power(context,signal):
    frames=np.zeros_like(context['windows'])
    for i,(start,count) in enumerate(zip(context['starts'],context['valid'])):
        frames[i,:count]=signal[start:start+count]
    power=abs(np.fft.rfft(frames*context['windows'],axis=1))**2/context['norm'][:,None]
    power[:,1:-1]*=2
    return np.stack([np.sum(power[:,mask],axis=1) for mask in context['masks']],axis=1)


def _band_measure(context,decoded):
    signal=np.asarray(decoded)
    if (signal.shape!=context['source'].shape or signal.dtype.kind not in 'iu'
            or np.any(signal<-32768) or np.any(signal>32767)):
        raise ValueError('Expected complete decoded PCM16 output')
    error=_band_power(context,signal.astype(np.float64)-context['source'])
    relative=error/np.maximum(context['source_power'],1.)
    partial=context['valid']<context['frame']
    return dict(samples=len(signal),frame_samples=context['frame'],hop_samples=context['hop'],
        bands_hz=[[1500,2500],[2500,4000]],starts=context['starts'],valid_samples=context['valid'].tolist(),
        error_power=error.tolist(),source_power=context['source_power'].tolist(),
        band_error_totals=np.sum(error*(context['valid']/context['frame'])[:,None],axis=0).tolist(),
        max_source_relative_frame_error=np.max(relative,axis=0).tolist(),
        partial_window_indices=np.flatnonzero(partial).tolist(),partial_source_relative_error=relative[partial].tolist(),
        window='Half-sample Hann; 80ms frames /20ms hops; every real tail window retained; no alignment or gain fitting')


def band_diagnostics(reference,decoded):
    """Return fixed source-referenced high-band diagnostics in both domains.

    The two frequency cutoffs and window geometry never depend on a candidate.
    Totals weight partial frames by their real duration; per-frame ratios use
    a one-count mean-square source floor. These are diagnostic error measures,
    not a calibrated roughness, audibility or quality scale.
    """
    context=_band_context(reference)
    return dict(schema='lpx-source-highband-errors-v1',
        pcm16=_band_measure(context,decoded),pwm8=_band_measure(context,pwm_pcm16(decoded)))


def band_error_floors(candidate,baseline):
    """Fail closed on band totals, burst maxima and EVERY partial tail frame.

    Compare one output domain, normally PWM8. Recompute summaries from the
    full frame matrix so missing/mismatched tail rows cannot evade a guard.
    """
    try:
        for key in ('samples','frame_samples','hop_samples','bands_hz','starts','valid_samples'):
            if candidate[key]!=baseline[key]:return False
        n=baseline['samples'];starts=list(range(0,n,160));valid=np.minimum(640,n-np.asarray(starts))
        if (not n or baseline['frame_samples']!=640 or baseline['hop_samples']!=160
                or baseline['bands_hz']!=[[1500,2500],[2500,4000]] or baseline['starts']!=starts
                or baseline['valid_samples']!=valid.tolist()):return False
        summaries=[];powers=[]
        for data in (candidate,baseline):
            error=np.asarray(data['error_power'],np.float64);source=np.asarray(data['source_power'],np.float64)
            if (error.shape!=(len(starts),2) or source.shape!=error.shape or not np.all(np.isfinite(error))
                    or not np.all(np.isfinite(source)) or np.any(error<0) or np.any(source<0)):return False
            relative=error/np.maximum(source,1.);powers.append(source)
            summaries.append((np.sum(error*(valid/640)[:,None],axis=0),
                              np.max(relative,axis=0),relative[valid<640]))
        if not np.array_equal(*powers):return False
        return all(np.all(new<=old+1e-12*np.maximum(1.,old)) for new,old in zip(*summaries))
    except (KeyError,TypeError,ValueError):
        return False


@njit(cache=True)
def errors(reference,pcm):
    pcm_error=np.int64(0);pwm_error=np.int64(0)
    for i in range(len(reference)):
        delta=np.int64(reference[i])-pcm[i];pcm_error+=delta*delta
        q14=(np.int64(pcm[i])+1)//2
        duty=min(255,max(0,128+((q14*130+8192)>>14)))
        delta=np.int64(reference[i])-(duty-128)*256;pwm_error+=delta*delta
    return pcm_error,pwm_error


@njit(cache=True)
def proposals(reference,co,parameters,pulses,extras,steps,pre,bright,source_pulses,horizon):
    """Rank five legal neighbors per played 80-sample packet.

    This snapshot recurrence is the existing exact advance() implementation.
    Each trial starts from the predecessor's state and only a bounded horizon
    is scored. That score is a proposal heuristic, never a whole-file gate.
    """
    history=np.zeros(10,np.int64);ring=np.zeros(256,np.int64);dd=cc=0
    work=pulses.copy();result=[]
    for index in range((len(reference)+79)//80):
        at=index*80;stop=min(len(reference),at+horizon)
        baseline=advance(co,parameters,work,extras,steps,pre,bright,at,stop,history,dd,cc,ring)[0]
        old_errors=errors(reference[at:stop],baseline);original=source_pulses[index]
        code=0
        for value in range(64):
            if value+((value+2)>>2)==original[0]:code=value;break
        first=index*4
        for delta in (-2,-1,1,2,0):
            trial_code=code+delta
            if not 0<=trial_code<64:continue
            position=trial_code+((trial_code+2)>>2)
            amplitude=original[1] if delta else (7 if original[1]==-8 else -8)
            for half in range(4):work[first+half,0]=0;work[first+half,1]=0
            work[first+position//20,0]=position%20;work[first+position//20,1]=amplitude
            actual=advance(co,parameters,work,extras,steps,pre,bright,at,stop,history,dd,cc,ring)[0]
            new_errors=errors(reference[at:stop],actual)
            if new_errors[0]<old_errors[0] and new_errors[1]<old_errors[1]:
                benefit=old_errors[0]+old_errors[1]-new_errors[0]-new_errors[1]
                result.append((benefit,index,position,amplitude))
        # Rewind every changed 20-sample entry before advancing the snapshot.
        for half in range(4):work[first+half]=pulses[first+half]
        _,history,dd,cc,ring=advance(co,parameters,work,extras,steps,pre,bright,
            at,min(at+80,len(reference)),history,dd,cc,ring)
    return result


def _native_exact(decoder,legacy,pcm):
    expanded=sparse.expand(legacy);n=len(pcm)
    if (not np.array_equal(decoder.decode_one_s16(expanded,n),pcm)
            or not np.array_equal(decoder.decode_one(expanded,n),pwm_duties(pcm))):
        raise AssertionError('Sparse pulse/model/native PCM or PWM differs')


def _measure(reference,pcm,track,objective,speech):
    domains=(pcm,pwm_pcm16(pcm))
    voice=[compare_voice(reference,x,reference_track=track) for x in domains]
    noise=[objective.summary(x) for x in domains]
    voice_score=[float(objective.voice_objective(x)) for x in domains]
    joint=[a+b['score'] for a,b in zip(voice_score,noise)]
    return dict(metrics=quality(reference,pcm,speech),voice=voice,
        score=float(np.mean(joint)),pwm_joint_score=float(joint[1]),
        pwm_voice_score=voice_score[1],pwm_noise=noise[1],
        clipped=[int(np.count_nonzero((pcm<=-32768)|(pcm>=32767))),
                 int(np.count_nonzero((domains[1]<=-32768)|(domains[1]>=32512)))])


def _floors(candidate,baseline):
    return (no_regression(candidate['metrics'],baseline['metrics'])
        and all(voice_floor(a,b) for a,b in zip(candidate['voice'],baseline['voice']))
        and all(a<=b for a,b in zip(candidate['clipped'],baseline['clipped'])))


def _difference(after,before,key):
    a=after[key];b=before[key]
    return None if a is None or b is None else a-b


def refine(reference,blob,decoder,*,horizon=320,full_candidates=12,speech=True,frequency_guard=True):
    """Return same-budget stream, exact PCM and predecessor-bound diagnostics.

    Accept v8/15 or v9/15 only. All extra work is offline. At most one of the
    five neighbors from each packet enters the complete-output candidate list;
    the input is the exact rollback, including noncanonical ignored fields.
    """
    if isinstance(horizon,bool) or not isinstance(horizon,Integral) or horizon not in (160,320):
        raise ValueError('Expected a 160 or 320-sample proposal horizon')
    if isinstance(full_candidates,bool) or not isinstance(full_candidates,Integral) or not 1<=full_candidates<=32:
        raise ValueError('Expected 1..32 complete candidates')
    if type(frequency_guard) is not bool:raise ValueError('Frequency guard selection must be boolean')
    start=time.perf_counter();original=bytes(blob);short=original[:2]==b'L9'
    if short:
        if len(original)<13 or original[2]!=15:raise ValueError('Expected sparse80 profile 15')
        legacy=repack(original,8)[0]
    else:
        if original[:6]!=b'L4HY\x08\x0f':raise ValueError('Expected sparse80 profile 15')
        legacy=original
    n,spectra,parameters,source_pulses,pre,bright=sparse.unpack(legacy)
    target=np.asarray(reference)
    if (target.shape!=(n,) or target.dtype.kind not in 'iu'
            or np.any(target<-32768) or np.any(target>32767)):
        raise ValueError('Expected the complete mono PCM16 reference')
    original_pcm=sparse.decode_model(legacy);_native_exact(decoder,legacy,original_pcm)
    original_pwm=pwm_duties(original_pcm)
    track=track_pitch(target);objective=NoiseObjective(target,track.period)
    baseline=_measure(target,original_pcm,track,objective,speech)
    band_context=_band_context(target)
    baseline_bands=dict(pcm16=_band_measure(band_context,original_pcm),
                        pwm8=_band_measure(band_context,pwm_pcm16(original_pcm)))
    best=baseline;best_pcm=original_pcm;best_pwm=original_pwm;selected=original
    expanded=sparse.expand(legacy)
    _,_,_,params,pulses,_,_,extras=compact.unpack(expanded)
    vectors=[[(int(value)<<4)+8 for value in row] for row in spectra for _ in range(2)]
    co=coefficient_trace(pack_frames(vectors),len(spectra)*320)[:n]
    ranked=proposals(target.astype(np.int64),co,np.asarray(params,np.int64),
        np.asarray(pulses,np.int64),np.asarray(extras,np.int64),table('scale_table.inc'),
        pre,bright,np.asarray(source_pulses,np.int64),int(horizon))
    order=sorted(ranked,key=lambda row:(-int(row[0]),int(row[1]),int(row[2]),int(row[3])))
    trials=[];packets=set()
    for row in order:
        if row[1] in packets:continue
        trials.append(row);packets.add(row[1])
        if len(trials)>=full_candidates:break
    current=list(source_pulses);checks=[];accepted=[]
    for benefit,index,position,amplitude in trials:
        index=int(index);position=int(position);amplitude=int(amplitude)
        trial=list(current);trial[index]=(position,amplitude)
        candidate=sparse.pack(n,spectra,parameters,trial,pre,bright)
        encoded=repack(candidate)[0] if short else candidate
        entry=dict(packet=index,position=position,amplitude=amplitude,local_benefit=int(benefit))
        if len(encoded)>len(original):entry['reason']='complete_byte_budget';checks.append(entry);continue
        pcm=sparse.decode_model(candidate);pcm_error,pwm_error=errors(target.astype(np.int64),pcm)
        if (pcm_error>baseline['metrics']['pcm16']['error_energy']
                or pwm_error>baseline['metrics']['pwm8']['error_energy']):
            entry['reason']='complete_error_floor';checks.append(entry);continue
        pwm=pwm_duties(pcm)
        if np.array_equal(pwm,best_pwm):
            entry['reason']='unchanged_pwm';checks.append(entry);continue
        if frequency_guard:
            bands=_band_measure(band_context,pwm_pcm16(pcm))
            if not band_error_floors(bands,baseline_bands['pwm8']):
                entry.update(reason='pwm_frequency_guard',pwm_band_error_totals=bands['band_error_totals'],
                             pwm_max_relative_frame_error=bands['max_source_relative_frame_error'])
                checks.append(entry);continue
        measured=_measure(target,pcm,track,objective,speech)
        finite=np.isfinite(measured['score']) and np.isfinite(measured['pwm_joint_score'])
        allowed=(finite and _floors(measured,baseline)
                 and measured['score']<best['score']-1e-12
                 and measured['pwm_joint_score']<best['pwm_joint_score']-1e-12)
        entry.update(admissible=bool(allowed),score=measured['score'],pwm_joint_score=measured['pwm_joint_score'])
        checks.append(entry)
        if allowed:
            _native_exact(decoder,candidate,pcm)
            selected=encoded;best_pcm=pcm;best_pwm=pwm;best=measured;current=trial;accepted.append(entry)
    recovered=repack(selected,8)[0] if short else selected
    fields=sparse.unpack(recovered)
    if fields[:3]!=(n,spectra,parameters) or fields[4:]!=(pre,bright) or len(selected)>len(original):
        raise AssertionError('Pulse refinement changed metadata, filters or complete byte budget')
    _native_exact(decoder,recovered,best_pcm)
    changed=int(np.count_nonzero(best_pwm!=original_pwm))
    noise_keys=('score','balance_absolute_error_mean_with_missing_penalty','fine_shape_hellinger_mean',
                'candidate_off_harmonic_fraction_mean_observed')
    voice_keys=('within_tolerance_frames','decoded_collapsed_active_frames',
                'fixed_decoded_period_error_mean','relative_spectral_shape_rms_db_mean')
    report=dict(schema='lpx-sparse80-local-pulses-v1',status='experimental_not_admitted',
        samples=n,input_bytes=len(original),selected_bytes=len(selected),
        decoder_changed=False,spectra_parameters_filters_exact=True,selected_native_pcm_pwm_exact=True,
        accepted=bool(changed),pwm_bytes_changed=bool(changed),pwm_changed_samples=changed,
        proposal_horizon=int(horizon),local_proposals=len(ranked),full_candidate_limit=int(full_candidates),
        complete_candidates=len(trials),accepted_patches=len(accepted),alternatives=checks,
        baseline=baseline,selected=best,
        frequency_guard_enabled=frequency_guard,
        baseline_band_diagnostics=baseline_bands,
        selected_band_diagnostics=dict(pcm16=_band_measure(band_context,best_pcm),
                                       pwm8=_band_measure(band_context,pwm_pcm16(best_pcm))),
        pwm_voice_score_delta=best['pwm_voice_score']-baseline['pwm_voice_score'],
        pwm_joint_score_delta=best['pwm_joint_score']-baseline['pwm_joint_score'],
        pwm_noise_deltas={key:_difference(best['pwm_noise'],baseline['pwm_noise'],key) for key in noise_keys},
        pwm_voice_deltas={key:_difference(best['voice'][1],baseline['voice'][1],key) for key in voice_keys},
        pwm_quality_deltas={key:_difference(best['metrics']['pwm8'],baseline['metrics']['pwm8'],key)
                            for key in ('error_energy','ser_db','stoi')},
        seconds=time.perf_counter()-start,
        scope='Experimental numerical selection only; the preceding Chego tuning prototype was subjectively rejected. No audibility, original-transparency or corpus-majority claim.')
    return selected,best_pcm,report


def main():
    import argparse,json
    from pathlib import Path
    import soundfile as sf
    from batch_decoder import BatchSession
    from output_paths import protect_outputs
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference',type=Path);parser.add_argument('input',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--horizon',type=int,choices=(160,320),default=320)
    parser.add_argument('--candidates',type=int,default=12);parser.add_argument('--non-speech',action='store_true')
    parser.add_argument('--allow-frequency-regression',dest='frequency_guard',action='store_false',default=True,
                        help='Research control: disable the fixed upper-band error floors')
    args=parser.parse_args();paths=[args.output/'audio.lpx',args.output/'decoded.wav',args.output/'report-private.json']
    protect_outputs([args.reference,args.input],paths)
    target,rate=sf.read(args.reference,dtype='int16')
    if rate!=8000:raise ValueError('Expected an 8 kHz reference')
    with BatchSession('batch',speech=True,speech_compact=True,compact_only=True) as decoder:
        blob,pcm,report=refine(target,args.input.read_bytes(),decoder,horizon=args.horizon,
            full_candidates=args.candidates,speech=not args.non_speech,frequency_guard=args.frequency_guard)
    args.output.mkdir(parents=True,exist_ok=True);paths[0].write_bytes(blob)
    sf.write(paths[1],pwm_pcm16(pcm),8000,subtype='PCM_16')
    paths[2].write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('selected_bytes','accepted','pwm_changed_samples','seconds')}))


if __name__=='__main__':main()
