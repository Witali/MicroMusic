"""Finite synthetic-only probe of causal optional-pulse candidate coverage."""
from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import inspect
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

from recipe import cases,fields,old_positions,SAMPLES,START,END,HORIZON,CAPACITY

HERE=Path(__file__).resolve().parent
V1=HERE.parent/'v5-joint-rate-2026-11-01'
sys.path.insert(0,str(V1))
from baselines import Inputs,sha
from pilot_runtime import (save,bind_production,production_snapshot,load_production,check_origins,
    bridge_native,no_initial_fits)


def timed():return time.perf_counter(),time.process_time()
def elapsed(at):return dict(wall_seconds=time.perf_counter()-at[0],cpu_seconds=time.process_time()-at[1])


def source_snapshot():
    paths=[p for p in HERE.iterdir() if p.suffix in ('.py','.md')]
    paths += [V1/name for name in ('baselines.py','pilot_policy.py','pilot_runtime.py')]
    shared=HERE.parent/'v5-matched-search-cpu-2026-10-30'
    paths += [shared/name for name in ('study_policy.py','study_runtime.py')]
    return {p.relative_to(HERE.parent).as_posix():sha(p.read_bytes()) for p in paths}


def prototype(C,out):
    source=inspect.getsource(C.single.adapt_excitation.py_func)
    marker='        positions[peak]=1\n'
    signature='start,end,horizon,hist,dd,cc,ring,capacity):'
    if source.count(marker)!=1 or source.count(signature)!=1:
        raise ValueError('The frozen refitter insertion point changed')
    addition=('        if include_mandatory:\n'
        '            for half in range(2):\n'
        '                causal=half*20+ii[at//20+half,0]\n'
        '                if 0<=causal<valid:positions[causal]=1\n')
    patched=source.replace('def adapt_excitation(','def experimental_adapt(').replace(signature,
        'start,end,horizon,hist,dd,cc,ring,capacity,include_mandatory):').replace(marker,marker+addition)
    text='from refine_speech_lpc import np,njit,advance,sse\n\n'+patched
    path=out/'generated_refitter.py';path.write_bytes(text.encode())
    spec=importlib.util.spec_from_file_location('synthetic_causal_refitter',path)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    return module.experimental_adapt,dict(original_function_sha256=sha(source.encode()),generated_source_sha256=sha(text.encode()))


class Verifier:
    def __init__(self,C,common,only,out):self.C,self.receivers,self.out=C,(common,only),out;self.cache={};self.counts=Counter();self.manifest=[]
    def verify(self,blob):
        if blob in self.cache:self.counts['exact_synthetic_stream_cache_hits']+=1;return self.cache[blob]
        C=self.C;pcm=C.compact.decode_model(blob);duty=C.pwm_duties(pcm)
        if C.compact.unpack(blob)[:2]!=(SAMPLES,blob[5]&127):raise AssertionError('Synthetic full geometry differs')
        for decoder in self.receivers:
            a,b=decoder.decode_one_s16(blob,SAMPLES),decoder.decode_one(blob,SAMPLES)
            if a is None or b is None or not C.np.array_equal(a,pcm) or not C.np.array_equal(b,duty):
                raise AssertionError('Synthetic model/common/v5 PCM/PWM mismatch')
            self.counts['native_output_domain_comparisons']+=2
        index=len(self.cache);path=self.out/'streams'/('synthetic-%04d.l4hy'%index);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(blob)
        self.manifest.append(dict(id=index,path=str(path.resolve()),stream_sha256=sha(blob),file_bytes=len(blob),
            samples=SAMPLES,profile=blob[5]&127,pcm16_sha256=sha(pcm.astype('<i2').tobytes()),
            pwm_sha256=sha(duty.tobytes()),model_common_v5_pcm_pwm_exact=True))
        self.cache[blob]=(pcm,duty,index);self.counts['unique_serialized_streams_verified']+=1;self.counts['model_samples_verified']+=SAMPLES
        return self.cache[blob]


def build(C,case,target=False):
    spectra,params,pulses,extras=fields(case,target)
    return C.compact.pack(SAMPLES,case['profile'],spectra,params,pulses,0,0,extras=extras)


def context(C,blob):
    n,profile,spectra,params,pulses,pre,bright,extras=C.compact.unpack(blob)
    shift=5 if profile==4 else 4
    vectors=[[(int(v)<<shift)+(1<<(shift-1)) for v in row] for row in spectra for _ in range(2)]
    co=C.single.coefficient_trace(C.single.pack_frames(vectors),n)
    arrays=[C.np.asarray(x,C.np.int64) for x in (params,pulses,extras)]
    steps=C.single.table('scale_table.inc');zero=C.np.zeros(10,C.np.int64);ring=C.np.zeros(256,C.np.int64)
    full=C.single.advance(co,*arrays,steps,pre,bright,0,n,zero,0,0,ring)[0]
    _,h,dd,cc,qr=C.single.advance(co,*arrays,steps,pre,bright,0,START,zero,0,0,ring)
    return spectra,co,arrays,steps,(h,dd,cc,qr),full


def refit(C,function,enabled,reference,case,ctx,attempt,out,phase):
    spectra,co,arrays,steps,state,_=ctx;h,dd,cc,qr=state
    event=dict(phase=phase,profile=case['profile'],case_index=case['index'],
        path='original' if enabled is None else 'mandatory' if enabled else 'disabled',status='started')
    attempt['refit_calls'].append(event);save(out/'attempt-private.json',attempt)
    at=timed();args=(reference.astype(C.np.int64),co,*arrays,steps,0,0,case['profile'],START,END,HORIZON,h,dd,cc,qr,CAPACITY)
    result=function(*args) if enabled is None else function(*args,enabled)
    cost=elapsed(at);pp,ii,ee,count=result
    blob,meta=C.compact.pack(SAMPLES,case['profile'],spectra,pp.tolist(),ii.tolist(),0,0,extras=ee.tolist())
    event.update(status='complete',trial_evaluations=int(count),cost=cost)
    save(out/'attempt-private.json',attempt)
    return blob,meta,dict(trial_evaluations=int(count),cost=cost,params=pp.tolist(),pulses=ii.tolist(),extras=ee.tolist())


def clipped(C,pcm):return int(C.np.count_nonzero((pcm==-32768)|(pcm==32767)))
def loss(C,target,actual):d=target.astype(C.np.int64)-actual.astype(C.np.int64);return int(C.np.sum(d*d))


def run(args):
    began=timed();sources=source_snapshot();inputs=Inputs();attempt=dict(status='started',refit_calls=[],cases=[],forbidden_fit_or_build_attempts=0)
    save(args.output/'attempt-private.json',attempt)
    try:
        commit=subprocess.check_output(['git','-C',str(args.source_root),'rev-parse','654ada49'],text=True).strip()
        inventory=bind_production(args.source_root,commit);native,bridge=bridge_native(args.source_root,args.native_cases,inputs)
        C=load_production(args.source_root);experimental,patch=prototype(C,args.output)
        setup=elapsed(began)
        binding=dict(source_commit=commit,source_root=str(args.source_root),production_sources=inventory,research_sources=sources,
            native_bridge=bridge,input_files_sha256=inputs.pins,module_origins=check_origins(args.source_root),prototype=patch,
            bounds=dict(cases_per_profile=120,profiles=[4,6],samples=SAMPLES,start=START,end=END,horizon=HORIZON),setup_cost=setup,
            corpus_audio_or_stream_reads=0,initial_fits=0,native_builds=0,target_jobs=0)
        save(args.output/'binding-private.json',binding)
        with no_initial_fits(attempt,args.output),C.BatchSession('batch',prebuilt=native['common']) as common,C.BatchSession('batch',prebuilt=native['v5-only']) as only:
            verifier=Verifier(C,common,only,args.output);warm=timed();warm_rows=[]
            for profile in (4,6):
                case=next(cases(profile));base,meta=build(C,case);pcm,_,_=verifier.verify(base);ctx=context(C,base)
                if not C.np.array_equal(ctx[-1],pcm):raise AssertionError('Real integer snapshot differs from model')
                values=[]
                for name,function,enabled in (('original',C.single.adapt_excitation,None),('disabled',experimental,False),('mandatory',experimental,True)):
                    stream,_,row=refit(C,function,enabled,pcm,case,ctx,attempt,args.output,'warm')
                    if stream!=base:raise AssertionError('Exact synthetic warm reference was changed')
                    verifier.verify(stream);values.append((stream,row));warm_rows.append(dict(profile=profile,path=name,**row))
                if values[0][0]!=values[1][0] or values[0][1]['trial_evaluations']!=values[1][1]['trial_evaluations']:
                    raise AssertionError('Disabled prototype differs from unchanged original')
            warm_cost=elapsed(warm);successes=[];all_rows=[];search=timed()
            for profile in (4,6):
                for case in cases(profile):
                    at=timed();base,base_meta=build(C,case);target,target_meta=build(C,case,True)
                    pcm,duty,base_id=verifier.verify(base);reference,target_duty,target_id=verifier.verify(target);ctx=context(C,base)
                    if not C.np.array_equal(ctx[-1],pcm) or not C.np.array_equal(reference[:START],pcm[:START]):
                        raise AssertionError('Synthetic prefix state is not shared exactly')
                    error=C.np.abs(reference[START:START+40].astype(C.np.int64)-pcm[START:START+40].astype(C.np.int64))
                    peak=int(C.np.argmax(error));different=C.np.flatnonzero(error)
                    causal=case['mandatory_position'];positions=old_positions(peak,case['original_extra_position'])
                    row=dict(**case,baseline_bytes=len(base),target_bytes=len(target),fixed_cap=len(base),baseline_stream_id=base_id,target_stream_id=target_id,
                        error_peak_offset=peak,first_output_difference_offset=None if not len(different) else int(different[0]),
                        old_positions=positions,added_mandatory_positions=sorted({causal,25}-set(positions)),
                        baseline_clipped_samples=clipped(C,pcm),target_clipped_samples=clipped(C,reference),status='skipped')
                    eligible=(not row['baseline_clipped_samples'] and not row['target_clipped_samples'] and
                        row['first_output_difference_offset']==causal and peak>causal and causal not in positions)
                    if eligible:
                        calls={};order=('old','expanded') if not case['index']%2 else ('expanded','old')
                        for name in order:
                            function,enabled=(C.single.adapt_excitation,None) if name=='old' else (experimental,True)
                            stream,meta,details=refit(C,function,enabled,reference,case,ctx,attempt,args.output,'measured')
                            actual,pwm,stream_id=verifier.verify(stream)
                            if len(stream)>len(base) or stream[12:16]!=base[12:16]:raise AssertionError('Synthetic cap/header changed')
                            calls[name]=dict(stream_id=stream_id,bytes=len(stream),payload_bits=meta['payload_bits'],extra_count=meta['extra_pulses'],
                                pcm_sse=loss(C,reference,actual),pwm_mismatch_samples=int(C.np.count_nonzero(pwm!=target_duty)),
                                clipped_samples=clipped(C,actual),**details)
                        amplitude=8 if profile==4 else 7
                        allowed=sum(a in (-4,-2,0,2,4) or abs(a+amplitude)<=1 for a in range(-8,8))
                        if calls['expanded']['trial_evaluations']-calls['old']['trial_evaluations']!=len(row['added_mandatory_positions'])*allowed:
                            raise AssertionError('Extra trials are not exactly the additional candidate positions')
                        success=(calls['expanded']['pcm_sse']==0 and calls['old']['pcm_sse']>0 and
                            all(v['bytes']==len(base) and v['payload_bits']==base_meta['payload_bits'] and v['extra_count']==1 and not v['clipped_samples'] for v in calls.values()))
                        row.update(status='counterexample' if success else 'not_strict_counterexample',baseline_payload_bits=base_meta['payload_bits'],
                            baseline_pcm_sse=loss(C,reference,pcm),old=calls['old'],expanded=calls['expanded'])
                        if success:
                            if (calls['expanded']['params'],calls['expanded']['pulses'],calls['expanded']['extras'])!=tuple(fields(case,True)[1:]):
                                raise AssertionError('Exact cancellation changed fields beyond the legal target')
                            successes.append(row)
                    row['cost']=elapsed(at);all_rows.append(row);attempt['cases'].append(dict(profile=profile,index=case['index'],status=row['status']))
                    save(args.output/('case-%d-%03d-private.json'%(profile,case['index'])),row)
                    save(args.output/'attempt-private.json',attempt)
                    if row['status']=='counterexample':break
            search_cost=elapsed(search);counts=dict(verifier.counts);artifacts=verifier.manifest
        if sources!=source_snapshot() or inventory!=production_snapshot(args.source_root) or attempt['forbidden_fit_or_build_attempts']:
            raise ValueError('Frozen source or forbidden-fit/build guard changed')
        check_origins(args.source_root);inputs.verify()
        if sha((args.output/'generated_refitter.py').read_bytes())!=patch['generated_source_sha256']:
            raise ValueError('Generated experimental source changed')
        for item in artifacts:
            if sha(Path(item['path']).read_bytes())!=item['stream_sha256']:raise ValueError('A synthetic serialized artifact changed')
        if any(r['status']!='complete' for r in attempt['refit_calls']):raise AssertionError('A synthetic refit did not complete')
        result=dict(status='PASS',synthetic_only=True,source_commit=commit,profiles_succeeded=[r['profile'] for r in successes],
            cases_examined={str(p):sum(r['profile']==p for r in all_rows) for p in (4,6)},warm_refit_calls=6,
            measured_refit_calls=sum(r['phase']=='measured' for r in attempt['refit_calls']),new_initial_fits=0,native_builds=0,
            corpus_audio_or_stream_reads=0,target_jobs=0,default_changes=0,setup_cost=setup,warm_cost=warm_cost,
            measured_search_cost=search_cost,total_cost=elapsed(began),native_verification_counts=counts,fixtures=successes,
            scope='Constructive synthetic coverage counterexample only; no corpus, rate, quality or audibility claim')
        save(args.output/'streams-private.json',artifacts)
        save(args.output/'all-cases-private.json',all_rows);save(args.output/'warm-private.json',warm_rows)
        save(args.output/'results.json',result);attempt.update(status='complete');save(args.output/'attempt-private.json',attempt)
        print(json.dumps(result),flush=True);return 0
    except Exception as exc:
        attempt.update(status='failed',exception_type=type(exc).__name__,cost=elapsed(began));save(args.output/'attempt-private.json',attempt)
        save(args.output/'failure-private.json',dict(exception_type=type(exc).__name__,traceback=traceback.format_exc()))
        print(json.dumps(dict(status='failed',exception_type=type(exc).__name__)),flush=True);return 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,default=HERE.parents[3]);parser.add_argument('--native-cases',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    for name in ('source_root','native_cases','output'):setattr(args,name,getattr(args,name).resolve())
    if args.output.exists() or not args.output.is_relative_to((HERE.parents[3]/'build').resolve()):parser.error('Use fresh ignored private build output')
    args.output.mkdir(parents=True);return run(args)


if __name__=='__main__':raise SystemExit(main())
