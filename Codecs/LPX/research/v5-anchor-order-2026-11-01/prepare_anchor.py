"""Bind exactly the original pre-pilot seeds/targets; no codec execution."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import time
import traceback

from anchor_policy import ARMS,validate_scope
from anchor_runtime import HERE,Inputs,sha,save,source_snapshot,load_original_manifest


def prepare(args):
    began=time.perf_counter(),time.process_time();inputs=Inputs();sources=source_snapshot()
    original=load_original_manifest(args.original_binding,inputs)
    chosen={b['id']:b for b in original['baselines'] if b['id'] in original['pilot_baseline_ids']}
    if (len(original['baselines'])!=104 or len(chosen)!=12 or sum(len(b['segments']) for b in chosen.values())!=20 or
            {(b['nonspeech'],b['source_ordinal']) for b in chosen.values()}!=
            {(False,3),(False,16),(False,20),(False,42),(True,10),(True,65)}):
        raise ValueError('The identical pre-pilot complete context set differs')
    jobs=[]
    for base in chosen.values():
        if sum(len(inputs.stream(meta)) for meta in base['segments'])!=base['stream_bytes']:
            raise ValueError('The exact current-strong baseline B differs')
        target=base['prepared_target']
        if len(inputs.read(target['path'],target['pcm16_sha256']))!=base['samples']*2 or target['sample_rate']!=8000:
            raise ValueError('The exact complete target geometry differs')
        shift=(base['source_ordinal']+base['profile']//2)%4
        ordered=ARMS[shift:]+ARMS[:shift]
        for arm in ordered:
            i=ARMS.index(arm)
            jobs.append(dict(id=len(jobs),baseline_id=base['id'],source_ordinal=base['source_ordinal'],
                nonspeech=base['nonspeech'],profile=base['profile'],mode=base['mode'],arm=arm,
                new_generation=i>=2,anchor_order='priority' if i%2 else 'time',rate_lambda=0.,
                reset_indices=list(range(len(base['segments']))),cpu_seconds_per_reset=2.,
                local_byte_cap=min(base['stream_bytes'],65535),
                whole_caps={str(p):base['stream_bytes']*p//100 for p in (100,95,90)}))
    binding=dict(schema='lpx-anchor-order-baselines-private-v1',status='prepared-no-search',
        original_binding_path=str(args.original_binding),original_binding_sha256=sha(args.original_binding.read_bytes()),
        preparation_commit=subprocess.check_output(['git','-C',str(HERE),'rev-parse','HEAD'],text=True).strip(),
        preparation_sources=sources,input_files_sha256=inputs.pins,baselines=original['baselines'],
        pilot_baseline_ids=original['pilot_baseline_ids'],jobs=jobs,
        same_pre_pilot_baseline_targets_geometry_and_level=True,prior_pilot_winners_excluded=True,
        fresh_baseline_checks_pending=True,new_search_calls=0,model_decode_calls=0,native_builds=0,initial_fits=0)
    validate_scope(binding);inputs.verify()
    if sources!=source_snapshot():raise ValueError('Preparation source changed')
    cost=dict(wall_seconds=time.perf_counter()-began[0],cpu_seconds=time.process_time()-began[1])
    binding['preparation_cost']=cost
    save(args.output/'binding-private.json',binding)
    summary=dict(status='prepared-no-search',baseline_contexts=104,pilot_contexts=12,arm_records=48,
        corpus_helper_calls=80,cap_views=144,reset_contexts_per_arm=20,nominal_corpus_cpu_seconds=160,
        profiles=[4,6],prior_pilot_winners_excluded=True,initial_fits=0,model_decode_calls=0,native_builds=0,
        new_search_calls=0,preparation_cost=cost,awaiting_frozen_production_source=True)
    save(args.output/'summary.json',summary)
    save(args.output/'complete-private.json',dict(status='complete',binding_sha256=sha((args.output/'binding-private.json').read_bytes()),
        all_source_and_input_guards_passed=True))
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original-binding',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();args.original_binding=args.original_binding.resolve();args.output=args.output.resolve()
    if args.output.exists() or not args.output.is_relative_to((HERE.parents[3]/'build').resolve()):
        parser.error('Use fresh ignored private research build output')
    args.output.mkdir(parents=True)
    try:
        print(json.dumps(prepare(args)),flush=True);return 0
    except Exception as exc:
        save(args.output/'failure-private.json',dict(exception_type=type(exc).__name__,traceback=traceback.format_exc()))
        print(json.dumps(dict(status='failed',exception_type=type(exc).__name__)),flush=True);return 1


if __name__=='__main__':raise SystemExit(main())
