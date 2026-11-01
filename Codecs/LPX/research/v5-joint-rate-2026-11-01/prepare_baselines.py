"""Prepare current admitted baselines/targets; no decoding or new search."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

from baselines import Inputs,admission_registry,load_current,pilot_ids,sha

HERE=Path(__file__).resolve().parent
PREFIX='Codecs/LPX/01_ACTIVE_Q0_CODEC/'
ARMS=(('T-local-0',0.,'local',False),('T-full-0',0.,'full',False),
    ('G-full-0',0.,'full',True),('G-full-.1',.1,'full',True),('G-full-1',1.,'full',True))


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:
        stream.write((json.dumps(value,indent=2,allow_nan=False)+'\n').encode())


def snapshot():
    return {p.name:sha(p.read_bytes()) for p in HERE.iterdir() if p.suffix in ('.py','.md')}


def origin_target_tools(root,commit,inputs):
    path=root/PREFIX/'tools/voice_input.py'
    expected=subprocess.check_output(['git','-C',str(root),'show',commit+':'+PREFIX+'tools/voice_input.py'])
    if inputs.read(path)!=expected:
        raise ValueError('Declared target code differs from the explicit preparation epoch')
    sys.path.insert(0,str(root/PREFIX/'tools'))
    import numpy as np
    import soundfile as sf
    import voice_input
    if Path(voice_input.__file__).resolve()!=path.resolve():
        raise ValueError('Target planning code was loaded from another checkout')
    return np,sf,voice_input


def prepare(args):
    started=time.perf_counter(),time.process_time()
    inputs=Inputs();sources=snapshot()
    registry=admission_registry(inputs,args.rom_handoff,args.rom_proof,args.spi_handoff,args.spi_proof)
    baselines=load_current(inputs,args.producer_study,registry)
    old=inputs.json(args.original_study/'binding-private.json')
    records={}
    for job in old['jobs']:
        source=old['speech_records'] if job['speech'] else old['nonspeech_records']
        record=source[job['record_index']]
        records[(not job['speech'],job['source_ordinal'],record['profile'])]=record
    np,sf,voice=origin_target_tools(args.source_root,args.source_commit,inputs)
    targets={}
    for base in baselines:
        record=records[(base['nonspeech'],base['source_ordinal'],base['profile'])]
        if base['reference']!=record['reference'] or base['samples']!=record['samples']:
            raise ValueError('A current baseline acquired another reference or length')
        base['split'],base['cohort']=record['split'],record['cohort']
        descriptor=base['reference']
        raw=inputs.read(descriptor['path'],descriptor['file_sha256'])
        if len(raw)!=descriptor['file_bytes']:
            raise ValueError('Original reference length differs')
        pcm,rate=sf.read(descriptor['path'],dtype='int16')
        if (rate!=8000 or pcm.ndim!=1 or len(pcm)!=base['samples']
                or sha(pcm.astype('<i2').tobytes())!=descriptor['pcm16_sha256']):
            raise ValueError('Original full PCM reference differs')
        plan=voice.plan_level(pcm,base['mode']);target,clipped=voice.quantize_target(pcm,plan)
        for name in ('policy','gain','gain_power2_exponent','gain_db','output_level_matches_original'):
            if plan[name]!=base['level'][name]:
                raise ValueError('Declared source level changed')
        digest=sha(target.astype('<i2').tobytes())
        if clipped or digest!=base['target_reference_pcm16_sha256']:
            raise ValueError('Declared target PCM differs or clips')
        if digest not in targets:
            path=args.output/'targets'/('target-%03d.pcm16le'%len(targets))
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as stream:stream.write(target.astype('<i2').tobytes())
            inputs.read(path,digest)
            targets[digest]=str(path.resolve())
        base['prepared_target']=dict(path=targets[digest],pcm16_sha256=digest,samples=len(target),sample_rate=8000)
        base['whole_caps']={str(percent):base['stream_bytes']*percent//100 for percent in (100,95,90)}
        sse=base['stored_expected_whole_value']['metrics']['pcm16']['error_energy']
        base['expected_prices_from_stored_baseline']={str(alpha):alpha*sse/(8*base['stream_bytes']) for alpha in (0.,.1,1.)}
        base['price_requires_fresh_baseline_sse_agreement']=True
    selected=pilot_ids(baselines)
    chosen=[b for b in baselines if b['id'] in selected]
    ids={(b['nonspeech'],b['source_ordinal']) for b in chosen}
    expected={(False,20),(False,3),(False,16),(False,42),(True,10),(True,65)}
    if ids!=expected or len(chosen)!=12 or sum(len(b['segments']) for b in chosen)!=20:
        raise ValueError('The metadata-selected full-record pilot changed')
    jobs=[]
    for base in chosen:
        # Rotation depends only on identifiers, not new algorithm outcomes.
        shift=(base['source_ordinal']+base['profile']//2)%len(ARMS)
        ordered=ARMS[shift:]+ARMS[:shift]
        for name,alpha,screening,new_generation in ordered:
            jobs.append(dict(id=len(jobs),baseline_id=base['id'],source_ordinal=base['source_ordinal'],
                nonspeech=base['nonspeech'],profile=base['profile'],mode=base['mode'],arm=name,
                alpha=alpha,screening=screening,new_generation=new_generation,
                reset_indices=list(range(len(base['segments']))),cpu_seconds_per_reset=2.,
                local_byte_cap=min(base['stream_bytes'],65535),whole_caps=base['whole_caps'],
                expected_rate_lambda=base['expected_prices_from_stored_baseline'][str(alpha)],
                frame_limit=64,window_frames=2,beam_width=3,spectral_candidates=4,excitation_candidates=2,
                excitation_horizon=160,screening_horizon=1280,max_evaluations=4096,
                allocation_evaluations=256 if new_generation else 0,per_branch_allocation_evaluations=16 if new_generation else 0,
                cross_rate_allocations=3 if new_generation else 0))
    calls=sum(len(job['reset_indices']) for job in jobs)
    if len(jobs)!=60 or calls!=100:
        raise ValueError('The five-arm 60-record/100-call pilot scope changed')
    structural=[]
    for base in baselines:
        if base['nonspeech'] and len(base['segments'])==60:
            previous=[35,59]
            fixed=sum(p['file_bytes'] for i,p in enumerate(base['segments']) if i not in previous)
            floor=fixed+22*len(previous)
            structural.append(dict(profile=base['profile'],source_ordinal=base['source_ordinal'],
                previous_edit_indices=previous,fixed_stored_bytes=fixed,header_only_whole_lower_bound=floor,
                whole_bytes=base['stream_bytes'],cap95=base['whole_caps']['95'],cap90=base['whole_caps']['90'],
                impossible95_under_previous_two_reset_policy=floor>base['whole_caps']['95'],
                scope='Structural diagnostic only; eventual corpus searches every reset'))
    inputs.verify()
    if sources!=snapshot():raise ValueError('Preparation source/protocol changed')
    cost=dict(wall_seconds=time.perf_counter()-started[0],cpu_seconds=time.process_time()-started[1])
    binding=dict(schema='lpx-joint-rate-baselines-private-v1',status='prepared-no-search',
        preparation_source_commit=args.source_commit,preparer_commit=subprocess.check_output(['git','-C',str(HERE),'rev-parse','HEAD'],text=True).strip(),
        preparation_sources_sha256=sources,input_files_sha256=inputs.pins,source_root=str(args.source_root),
        baselines=baselines,pilot_baseline_ids=selected,pilot_jobs=jobs,structural_diagnostics=structural,
        preparation_cost=cost,fresh_whole_baseline_checks_pending=True,new_search_calls=0,model_decode_calls=0,
        native_builds=0,initial_fits=0,target_images=0,source_epochs_and_target_origins_private=True)
    save(args.output/'binding-private.json',binding)
    replaced=sum(chain['source_choice']['kind']=='matched-cpu' for chain in baselines)
    smaller=sum(chain['stream_bytes']<chain['canonical_rollback_bytes'] for chain in baselines)
    summary=dict(status='prepared-no-search',baseline_contexts=104,unique_declared_targets=len(targets),
        matched_cpu_replacements=replaced,already_smaller_than_old_canonical=smaller,
        pilot_contexts=12,pilot_arm_records=60,pilot_helper_calls=100,pilot_cap_views=180,pilot_nominal_cpu_seconds=200,
        pilot_sources=[dict(nonspeech=domain,source_ordinal=ordinal) for domain,ordinal in sorted(ids)],
        pilot_samples=sum(b['samples'] for b in chosen),pilot_reset_contexts=20,
        future_corpus_contexts=104,future_corpus_searched_resets=242,future_corpus_arms=4,
        future_corpus_helper_calls=968,future_corpus_cap_views=1248,future_corpus_nominal_cpu_seconds=1936,
        domain_context_counts=dict(Counter('nonspeech' if b['nonspeech'] else b['mode'] for b in baselines)),
        structural_diagnostics=structural,preparation_cost=cost,new_search_calls=0,model_decode_calls=0,
        native_builds=0,initial_fits=0,target_images=0,fresh_whole_baseline_checks_pending=True)
    save(args.output/'summary.json',summary)
    save(args.output/'complete-private.json',dict(status='complete',binding_sha256=sha((args.output/'binding-private.json').read_bytes()),
        prepared_not_searched=True,all_input_and_source_guards_passed=True))
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source-root','producer-study','original-study','rom-handoff','rom-proof','spi-handoff','spi-proof','output'):
        parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--source-commit',required=True)
    args=parser.parse_args()
    for name in ('source_root','producer_study','original_study','rom_handoff','rom_proof','spi_handoff','spi_proof','output'):
        setattr(args,name,getattr(args,name).resolve())
    if args.output.exists() or not args.output.is_relative_to((HERE.parents[3]/'build').resolve()):
        parser.error('Use fresh private output under this research worktree build directory')
    args.output.mkdir(parents=True)
    try:
        result=prepare(args)
        print(json.dumps(result),flush=True)
        return 0
    except Exception as exc:
        save(args.output/'failure-private.json',dict(exception_type=type(exc).__name__,traceback=traceback.format_exc()))
        print(json.dumps(dict(status='failed',exception_type=type(exc).__name__)),flush=True)
        return 1


if __name__=='__main__':main_result=main();raise SystemExit(main_result)
