"""Bounded v5-only header refinement with cached exact integer synthesis.

Keep the entire excitation, spectrum and payload unchanged. Search the existing
preQ14/brightQ14 fields against full-length PCM16 and fixed PWM output. Return a
conservative candidate and also report the best raw SSE alternative for review;
objective metrics do not establish perceptual improvement.
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
from q0_model import clamp, coefficient_trace, table
from standard_metrics import error_metrics, pwm_duties, pwm_pcm16
from tune_pcm16 import set_header
from wav_lpc import pack_frames


@njit(cache=True)
def lpc_signal(co, params, pulses, extras, steps):
    """Header-independent LPC output, before deemphasis and brightness.

    This is the integer recurrence used by enhance_speech_compact.advance.
    Retain the unclipped-to-Q14 LPC value; decoding with zero filters would
    already clip it and cannot recover this signal.
    """
    history=np.zeros(10,np.int64);ring=np.zeros(256,np.int64)
    result=np.empty(len(co),np.int64)
    for j in range(len(co)):
        scale,lag,gain=params[j//160];pos,amp=pulses[j//20];ep,ea=extras[j//40]
        q=(gain*ring[(j-lag)&255]+8)>>4
        q=min(31,max(-32,q+(amp if j%20==pos else 0)+(ea if j%40==ep else 0)))
        ring[j&255]=q;acc=0
        for k in range(10):acc+=(co[j,k]*history[k])>>12
        value=clamp(q*steps[scale*8]-acc)
        for k in range(9,0,-1):history[k]=history[k-1]
        history[0]=value;result[j]=value
    return result


@njit(cache=True)
def filter_signal(signal, pre, bright):
    out=np.empty(len(signal),np.int16);dd=cc=0
    for j in range(len(signal)):
        dd=clamp(signal[j]+((pre*dd)>>14));clipped=clamp(dd,-16384,16384)
        value=clamp(clipped-((bright*cc)>>14),-16384,16384);cc=clipped
        out[j]=clamp(value*2,-32768,32767)
    return out


@njit(cache=True)
def errors(reference, signal, pre, bright):
    pcm=filter_signal(signal,pre,bright);pcm_sse=np.int64(0);pwm_sse=np.int64(0)
    for j in range(len(reference)):
        delta=np.int64(reference[j])-np.int64(pcm[j]);pcm_sse+=delta*delta
        q14=(np.int64(pcm[j])+1)//2
        duty=min(255,max(0,128+((q14*130+8192)>>14)))
        delta=np.int64(reference[j])-(duty-128)*256;pwm_sse+=delta*delta
    return pcm_sse,pwm_sse


def quality(reference, pcm):
    result={'pcm16':error_metrics(reference,pcm,True),
            'pwm8':error_metrics(reference,pwm_pcm16(pcm),True)}
    for value in result.values():
        if value['stoi'] is not None and not np.isfinite(value['stoi']):
            value['stoi']=None
    return result


def no_regression(candidate, baseline):
    for domain in ('pcm16','pwm8'):
        new,old=candidate[domain],baseline[domain]
        if new['error_energy']>old['error_energy']:return False
        if old['stoi'] is not None and (new['stoi'] is None or new['stoi']<old['stoi']-1e-12):return False
    return True


def refine(reference, blob, decoder, *, trial_limit=256, metric_limit=16):
    """Return (same-size v5 stream, exact PCM16, anonymous numerical report).

    Multi-scale coordinate/diagonal descent proposes at most trial_limit valid
    header pairs. Full PCM/PWM STOI is checked for at most metric_limit pairs
    spread across the measured SSE range. This is a bounded local search, not a global or perceptual optimum.
    """
    if isinstance(trial_limit,bool) or not isinstance(trial_limit,int) or not 1<=trial_limit<=4096:
        raise ValueError('Expected integer trial_limit in 1..4096')
    if isinstance(metric_limit,bool) or not isinstance(metric_limit,int) or not 1<=metric_limit<=128:
        raise ValueError('Expected integer metric_limit in 1..128')
    ref=np.asarray(reference)
    if ref.ndim!=1 or ref.dtype.kind not in 'iu' or np.any(ref<-32768) or np.any(ref>32767):
        raise ValueError('Expected mono PCM16 reference')
    n,profile,spectra,params,pulses,pre,bright,extras=compact.unpack(blob)
    if len(ref)!=n:raise ValueError('Reference/stream sample count mismatch')
    started=time.perf_counter();shift=5 if profile==4 else 4
    vectors=[[(v<<shift)+(1<<(shift-1)) for v in row] for row in spectra for _ in range(2)]
    co=coefficient_trace(pack_frames(vectors[:(n+159)//160]),n)
    signal=lpc_signal(co,np.asarray(params,np.int64),np.asarray(pulses,np.int64),
                      np.asarray(extras,np.int64),table('scale_table.inc'))
    initial=(pre,bright);pcm=filter_signal(signal,*initial)
    native=decoder.decode_one_s16(blob,n)
    if native is None or not np.array_equal(native,pcm) or not np.array_equal(pcm,compact.decode_model(blob)):
        raise AssertionError('Cached LPC/filter baseline differs from native/model')
    before=quality(ref,pcm);reference64=ref.astype(np.int64);cache={}
    def score(pair):
        if pair in cache:return cache[pair]
        if len(cache)>=trial_limit or not 0<=pair[0]<=16384 or not 0<=pair[1]<=11469:return None
        value=errors(reference64,signal,*pair);cache[pair]=tuple(int(v) for v in value)
        return cache[pair]
    score(initial);current=initial
    for step in (2048,1024,512,256,128,64,32,16,8,4,2,1):
        while len(cache)<trial_limit:
            pairs=[(current[0]+a*step,current[1]+b*step) for a,b in
                   ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1))]
            for pair in pairs:score(pair)
            best=min((pair for pair in pairs if pair in cache),
                     key=lambda pair:(cache[pair],pair),default=current)
            if cache[best]>=cache[current]:break
            current=best
    ranked=sorted((pair for pair in cache if cache[pair][0]<cache[initial][0]),
                  key=lambda pair:(cache[pair],pair))
    eligible=[pair for pair in ranked if cache[pair][1]<=cache[initial][1]]
    # Include a raw alternative even when its PWM metric trades off quality.
    # Spread costly intelligibility checks over the measured SSE range. The
    # nearest SSE optima often have almost identical filters and miss a useful
    # intermediate tradeoff near the original header.
    quantiles=([eligible[int(i*(len(eligible)-1)/max(1,metric_limit-1))]
                for i in range(metric_limit)] if eligible else [])
    short=list(dict.fromkeys(([ranked[0]] if ranked else [])+quantiles))[:metric_limit]
    selected=initial;after=before;checks=[]
    for pair in short:
        actual=filter_signal(signal,*pair);measured=quality(ref,actual)
        assert int(measured['pcm16']['error_energy'])==cache[pair][0]
        assert int(measured['pwm8']['error_energy'])==cache[pair][1]
        allowed=no_regression(measured,before)
        checks.append({'preQ14':pair[0],'brightQ14':pair[1],'metrics':measured,
                       'conservative_floors_passed':bool(allowed)})
        if allowed and measured['pcm16']['error_energy']<after['pcm16']['error_energy']:
            selected=pair;after=measured
    result=set_header(blob,*selected);pcm=filter_signal(signal,*selected)
    raw=ranked[0] if ranked else initial
    # Check both the selected and unconstrained best-SSE byte streams through
    # the receiver and independent full model, including existing extra pulses.
    for pair in set((initial,selected,raw)):
        trial=set_header(blob,*pair);actual=filter_signal(signal,*pair)
        received=decoder.decode_one_s16(trial,n)
        if received is None or not np.array_equal(received,actual) or not np.array_equal(actual,compact.decode_model(trial)):
            raise AssertionError('Cached header candidate differs from native/model')
        if not np.array_equal(decoder.decode_one(trial,n),pwm_duties(actual)):
            raise AssertionError('Cached header candidate differs from native PWM')
    if result[:12]!=blob[:12] or result[16:]!=blob[16:] or len(result)!=len(blob):
        raise AssertionError('Header refinement changed payload, geometry or size')
    report={'proposal':'compact_header_filters','profile':profile,'samples':n,
            'file_bytes':len(result),'extra_bytes':0,'payload_exact':True,'native_model_pwm_exact':True,
            'input_header':{'preQ14':pre,'brightQ14':bright},
            'output_header':{'preQ14':selected[0],'brightQ14':selected[1]},
            'raw_best_sse_header':{'preQ14':raw[0],'brightQ14':raw[1]},
            'baseline':before,'selected':after,'accepted':selected!=initial,
            'candidate_evaluations':len(cache),'trial_limit':trial_limit,
            'full_metric_evaluations':len(checks),'metric_limit':metric_limit,'alternatives':checks,
            'seconds':time.perf_counter()-started}
    return result,pcm,report


def main():
    import soundfile as sf
    from batch_decoder import BatchSession
    from output_paths import protect_outputs
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference',type=Path);parser.add_argument('input',type=Path)
    parser.add_argument('output',type=Path);parser.add_argument('--trials',type=int,default=256)
    parser.add_argument('--metric-candidates',type=int,default=16)
    args=parser.parse_args();paths=[args.output/'audio.l4hy',args.output/'decoded.wav',args.output/'report.json']
    protect_outputs([args.reference,args.input],paths)
    reference,rate=sf.read(args.reference,dtype='int16')
    if rate!=8000:raise ValueError('Reference must be 8kHz')
    with BatchSession('batch',speech=True,speech_compact=True,compact_only=True) as decoder:
        blob,pcm,report=refine(reference,args.input.read_bytes(),decoder,
                               trial_limit=args.trials,metric_limit=args.metric_candidates)
    report.update(reference_pcm16_sha256=hashlib.sha256(reference.astype('<i2').tobytes()).hexdigest(),
                  input_sha256=hashlib.sha256(args.input.read_bytes()).hexdigest(),
                  stream_sha256=hashlib.sha256(blob).hexdigest())
    args.output.mkdir(parents=True,exist_ok=True);paths[0].write_bytes(blob)
    sf.write(paths[1],pcm,8000,subtype='PCM_16')
    paths[2].write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('profile','file_bytes','accepted','candidate_evaluations','seconds')}))


if __name__=='__main__':main()
