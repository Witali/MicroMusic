"""Opt-in, fixed-size sparse80 filter refinement; other profiles are untouched.

All extra work is offline. The selected stream changes only its two existing
filter words. Selection preserves PCM/PWM error, available STOI, measured voice
period/count floors and clipping, or returns the exact original stream. The
joint voice/noise score ranks admitted candidates; individual spectral-shape
diagnostics may trade off and remain visible in the report.
"""
from __future__ import annotations

import math
import struct
import time

import numpy as np

import speech_compact as compact
import speech_sparse80 as sparse
from speech_v9 import repack
from refine_speech_compact import refine as proposals,quality,no_regression,set_header
from speech_noise_objective import NoiseObjective
from voice_character import track_pitch,compare_voice
from standard_metrics import pwm_duties,pwm_pcm16


def voice_floor(candidate,baseline):
    if candidate['within_tolerance_frames']<baseline['within_tolerance_frames']:return False
    if candidate['decoded_collapsed_active_frames']>baseline['decoded_collapsed_active_frames']:return False
    old=baseline['fixed_decoded_period_error_mean'];new=candidate['fixed_decoded_period_error_mean']
    return old is None or (new is not None and math.isfinite(new) and new<=old+1e-12)


def refine(reference,blob,decoder,*,trial_limit=1024,metric_limit=64,speech=True):
    """Return same-size selected bytes, exact PCM16 and numerical diagnostics.

    ``decoder`` is the existing independent ordinary-v5/P6 native receiver.
    Both long-header v8 and compact v9 sparse80 streams are accepted. This
    routine does not re-encode P4/P6, change their settings or fit output gain.
    """
    started=time.perf_counter();original=bytes(blob)
    short=original[:2]==b'L9'
    if short:
        if len(original)<13 or original[2]!=15:raise ValueError('Expected sparse80 profile15')
        legacy,_=repack(original,8)
    else:
        if original[:6]!=b'L4HY\x08\x0f':raise ValueError('Expected sparse80 profile15')
        legacy=original
    n,_,_,_,pre,bright=sparse.unpack(legacy)
    target=np.asarray(reference)
    if target.shape!=(n,) or target.dtype.kind not in 'iu' or np.any(target<-32768) or np.any(target>32767):
        raise ValueError('Expected the complete original PCM16 reference')
    expanded=sparse.expand(legacy)
    # Include paired moves: raising deemphasis and brightness together can
    # preserve the spectral envelope while moving toward a waveform optimum.
    # SSE-only coordinate descent can miss this valley from brightness zero.
    pres=sorted(set(max(0,min(16384,pre+d)) for d in
                    (0,-4096,-2048,-1024,-512,-256,-128,-64,-16,-4,-1,1,4,16,64,128,256,512,1024,2048,4096)))
    brights=sorted(set(max(0,min(11469,bright+d)) for d in
                       (0,-2048,-1024,-256,-64,1,4,16,64,128,256,512,1024,2048,4096,8192,11469)))
    _,_,search=proposals(target,expanded,decoder,trial_limit=trial_limit,
                         metric_limit=metric_limit,speech=speech,
                         extra_pairs=((p,b) for p in pres for b in brights))
    baseline=compact.decode_model(expanded)
    track=track_pitch(target);objective=NoiseObjective(target,track.period)
    def evaluate(pcm):
        pwm=pwm_pcm16(pcm)
        voice=[compare_voice(target,x,reference_track=track) for x in (pcm,pwm)]
        score=float(np.mean([objective.voice_objective(x)+objective(x) for x in (pcm,pwm)]))
        clipped=(int(np.count_nonzero((pcm<=-32768)|(pcm>=32767))),
                 int(np.count_nonzero((pwm<=-32768)|(pwm>=32512))))
        return voice,score,clipped
    before=quality(target,baseline,speech)
    base_voice,base_score,base_clip=evaluate(baseline)
    selected=(pre,bright);best=baseline;best_metrics=before
    best_voice=base_voice;best_score=base_score;best_clip=base_clip;checks=[]
    for trial in search['alternatives']:
        if not trial['conservative_floors_passed']:continue
        pair=(trial['preQ14'],trial['brightQ14'])
        pcm=compact.decode_model(set_header(expanded,*pair))
        measured=trial['metrics'];voice,score,clipped=evaluate(pcm)
        allowed=(no_regression(measured,before) and math.isfinite(score)
                 and all(voice_floor(a,b) for a,b in zip(voice,base_voice))
                 and all(a<=b for a,b in zip(clipped,base_clip)))
        checks.append(dict(preQ14=pair[0],brightQ14=pair[1],score=score,admissible=bool(allowed),voice=voice,clipped=list(clipped)))
        if allowed and score<best_score-1e-12:
            selected=pair;best=pcm;best_metrics=measured;best_voice=voice
            best_score=score;best_clip=clipped
    offset=7 if short else 12
    result=original[:offset]+struct.pack('<HH',*selected)+original[offset+4:]
    recovered,_=repack(result,8) if short else (result,None)
    if len(result)!=len(original) or result[:offset]!=original[:offset] or result[offset+4:]!=original[offset+4:]:
        raise AssertionError('Refinement changed size, payload or other parameters')
    if not np.array_equal(sparse.decode_model(recovered),best):raise AssertionError('Sparse80 model differs')
    received=decoder.decode_one_s16(set_header(expanded,*selected),n)
    if received is None or not np.array_equal(received,best):raise AssertionError('Native PCM differs')
    if not np.array_equal(decoder.decode_one(set_header(expanded,*selected),n),pwm_duties(best)):
        raise AssertionError('Native PWM differs')
    report=dict(schema='lpx-sparse80-filter-refinement-v1',samples=n,file_bytes=len(result),
        extra_bytes=0,payload_exact=True,native_model_pwm_exact=True,
        accepted=selected!=(pre,bright),input_header=dict(preQ14=pre,brightQ14=bright),
        output_header=dict(preQ14=selected[0],brightQ14=selected[1]),
        baseline=before,selected=best_metrics,baseline_voice=base_voice,selected_voice=best_voice,
        baseline_score=base_score,selected_score=best_score,
        baseline_clipped=list(base_clip),selected_clipped=list(best_clip),
        candidate_evaluations=search['candidate_evaluations'],full_metric_evaluations=len(checks),
        alternatives=checks,seconds=time.perf_counter()-started,
        scope='Fixed-size offline search; numeric proxies do not establish subjective quality.')
    return result,best,report


def main():
    import argparse,json
    from pathlib import Path
    import soundfile as sf
    from batch_decoder import BatchSession
    from output_paths import protect_outputs
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference',type=Path)
    parser.add_argument('input',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--trials',type=int,default=1024)
    parser.add_argument('--metric-candidates',type=int,default=64)
    parser.add_argument('--non-speech',action='store_true')
    args=parser.parse_args()
    paths=[args.output/'audio.lpx',args.output/'decoded.wav',args.output/'report-private.json']
    protect_outputs([args.reference,args.input],paths)
    source,rate=sf.read(args.reference,dtype='int16')
    if rate!=8000:raise ValueError('Expected an 8 kHz reference')
    with BatchSession('batch',speech=True,speech_compact=True,compact_only=True) as decoder:
        blob,pcm,report=refine(source,args.input.read_bytes(),decoder,trial_limit=args.trials,
                               metric_limit=args.metric_candidates,speech=not args.non_speech)
    args.output.mkdir(parents=True,exist_ok=True);paths[0].write_bytes(blob)
    sf.write(paths[1],pwm_pcm16(pcm),8000,subtype='PCM_16')
    paths[2].write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('file_bytes','accepted','seconds')}))


if __name__=='__main__':main()
