"""Post-pilot diagnostics requested after outcomes; saved numeric values only."""
from __future__ import annotations

import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path

from baselines import Inputs,sha
from pilot_policy import HERE,ARMS
from pilot_runtime import save


def change(new,old):
    result=dict(joint_delta=new['score']-old['score'],joint_improvement_percent=100*(old['score']-new['score'])/old['score'],
        clipped_sample_delta=new['clipped_samples']-old['clipped_samples'],
        pcm_period_coverage_delta=new['voice']['within_tolerance_frames']-old['voice']['within_tolerance_frames'],
        pwm_period_coverage_delta=new['pwm_voice']['within_tolerance_frames']-old['pwm_voice']['within_tolerance_frames'],
        pcm_noise_score_delta=new['noise']['score']-old['noise']['score'],
        pwm_noise_score_delta=new['pwm_noise']['score']-old['pwm_noise']['score'])
    for domain in ('pcm16','pwm8'):
        a,b=new['metrics'][domain],old['metrics'][domain]
        result[domain+'_sse_delta']=a['error_energy']-b['error_energy']
        result[domain+'_ser_delta_db']=None if a['ser_db'] is None or b['ser_db'] is None else a['ser_db']-b['ser_db']
        result[domain+'_stoi_delta']=None if a['stoi'] is None or b['stoi'] is None else a['stoi']-b['stoi']
    return result


def non_sse(row,base):
    stoi=all(base['metrics'][d]['stoi'] is None or row['metrics'][d]['stoi'] is not None and
        row['metrics'][d]['stoi']>=base['metrics'][d]['stoi']-1e-12 for d in ('pcm16','pwm8'))
    sse_fail=any(row['metrics'][d]['error_energy']>base['metrics'][d]['error_energy'] for d in ('pcm16','pwm8'))
    period=row['pcm_period_coverage_floor_passed'] and row['pwm_period_coverage_floor_passed']
    noise=all(row[d]['score']<=base[d]['score']+1e-12 for d in ('noise','pwm_noise'))
    return dict(stoi_pass=stoi,period_pass=period,clipping_pass=row['clipped_sample_floor_passed'],
        independent_noise_summary_pass=noise,joint_pass=row['joint_objective_nonregression'],sse_fail=sse_fail,
        f0_stoi_clip_noise_pass=bool(stoi and period and noise and row['clipped_sample_floor_passed']),
        only_sse_common_gate_failure=bool(stoi and period and row['clipped_sample_floor_passed'] and
            row['joint_objective_nonregression'] and sse_fail))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();args.study=args.study.resolve();args.output=args.output.resolve()
    if args.output.exists() or not args.output.is_relative_to((HERE.parents[3]/'build').resolve()):
        parser.error('Use fresh ignored private build output')
    args.output.mkdir(parents=True);inputs=Inputs()
    summary=inputs.json(args.study/'export-v1/summary.json')
    binding=inputs.json(args.study/'export-v1/binding-private.json')
    if summary['status']!='PASS' or binding['status']!='PASS':raise ValueError('The completed saved-decision export is required')
    for path,digest in binding['input_files_sha256'].items():inputs.read(path,digest)
    rows=[];work={};first_anchors=Counter()
    keys=('full_synthesis_evaluations','spectral_trials','excitation_trials','repeat_spectrum_proposals',
        'completed_rate_allocation_calls','rate_allocation_points','allocation_evaluations',
        'completed_parent_expansions','completed_windows','incomplete_windows')
    for shard in binding['shard_paths']:
        shard=Path(shard);results=inputs.json(shard/'results-private.json');rows.extend(results)
        for row in results:
            counts=work.setdefault(row['arm'],Counter())
            for local in row['locals']:
                report=inputs.json(shard/'arms'/('job-%03d'%row['id'])/('reset-%03d'%local['index'])/'helper-return-private.json')['report']
                counts['helpers']+=1
                for key in keys:counts[key]+=report.get(key,0)
                counts['helpers_with_repeat_proposals']+=report.get('repeat_spectrum_proposals',0)>0
                counts['helpers_with_completed_allocation']+=report.get('completed_rate_allocation_calls',0)>0
                counts['helpers_with_completed_parent_expansion']+=report['completed_parent_expansions']>0
                if report['checkpoints']:first_anchors[row['arm']+':'+str(report['checkpoints'][0]['anchor'])]+=1
    contexts=defaultdict(dict)
    for row in rows:contexts[row['baseline_id']][row['arm']]=row
    generation=[];gains=[];raw=[];raw_sets=defaultdict(set)
    for base_id,arms in contexts.items():
        control=arms['T-full-0'];new=arms['G-full-0']
        chosen=lambda r:r['whole_rows'][r['decisions'][0]['selected_id']]
        a,b=chosen(new),chosen(control)
        if abs(a['score']-b['score'])>1e-12 or a['stream_bytes']!=b['stream_bytes']:
            generation.append(dict(baseline_id=base_id,source_ordinal=new['source_ordinal'],profile=new['profile'],
                nonspeech=new['nonspeech'],new_lower_joint=a['score']<b['score'],
                new_bytes=a['stream_bytes'],control_bytes=b['stream_bytes'],**change(a,b)))
        for arm in ARMS[2:]:
            row=arms[arm];base=row['whole_rows'][0];point=chosen(row)
            if row['decisions'][0]['selected_id']!=0:
                gains.append(dict(arm=arm,baseline_id=base_id,source_ordinal=row['source_ordinal'],profile=row['profile'],
                    nonspeech=row['nonspeech'],baseline_bytes=base['stream_bytes'],selected_bytes=point['stream_bytes'],
                    saved_bytes=base['stream_bytes']-point['stream_bytes'],**change(point,base)))
        for arm,row in arms.items():
            base=row['whole_rows'][0]
            for decision in row['decisions'][1:]:
                if decision['raw_id'] is None:continue
                point=row['whole_rows'][decision['raw_id']];flags=non_sse(point,base)
                key=tuple((p['stream_sha256'],p['file_bytes']) for p in row['whole_chains'][point['id']]['segments'])
                raw_sets[decision['percent']].add(key)
                raw.append(dict(arm=arm,baseline_id=base_id,source_ordinal=row['source_ordinal'],profile=row['profile'],
                    nonspeech=row['nonspeech'],percent=decision['percent'],raw_bytes=point['stream_bytes'],
                    baseline_bytes=base['stream_bytes'],**flags,**change(point,base)))
    result=dict(status='PASS',posthoc_requested_after_pilot=True,new_search_decode_metric_native_calls=0,
        generation_non_ties=generation,new_selected_changes_vs_strongest_baseline=gains,
        fitting_raw_cap_views=raw,distinct_fitting_raw_ordered_chains={str(p):len(v) for p,v in raw_sets.items()},
        fitting_raw_views_passing_f0_stoi_clip_noise=sum(r['f0_stoi_clip_noise_pass'] for r in raw),
        fitting_raw_views_failing_only_sse_common_gates=sum(r['only_sse_common_gate_failure'] for r in raw),
        work_by_arm={arm:dict(counts) for arm,counts in work.items()},first_anchor_histogram=dict(first_anchors),
        refit_call_counter_unavailable=True,
        completed_new_allocation_calls_imply_at_least_that_many_preceding_cap_aware_refits=True,
        independent_noise_summary_definition='Both saved PCM/PWM noise.summary scores <= baseline +1e-12; descriptive, not a new admission rule')
    inputs.verify();save(args.output/'diagnostics.json',result)
    save(args.output/'binding-private.json',dict(status='PASS',input_files_sha256=inputs.pins,
        diagnosis_source_sha256=sha(Path(__file__).read_bytes()),export_binding_sha256=sha((args.study/'export-v1/binding-private.json').read_bytes())))
    print(json.dumps(result),flush=True)


if __name__=='__main__':main()
