"""Read-only final 248-arm gate and exact changed-selection player handoff."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import sys
import traceback

THIS = Path(__file__).resolve()
HERE = THIS.parent
PACKAGE = HERE.parent
GENERIC = PACKAGE.parent/'v5-adaptive-player-union-2026-10-30/reproduction'
RETENTION = PACKAGE.parent/'v5-retention-player-2026-10-30/reproduction'
sys.path.insert(0,str(RETENTION))
from prepare_retention import (Epoch,Union,FLASH_BYTES,PHASES,FLAGS,sha,
                               require,decision_from_rows,loaded_module)

VALUE_KEYS = ('metrics','voice','pwm_voice','noise','pwm_noise','domain_scores','score',
              'clipped_samples','voice_components','pwm_voice_components')
PRIORITY = {'speech-default':0,'speech-screen':1,'nonspeech-default':0}


def equal(a,b):
    if isinstance(b,dict):
        return isinstance(a,dict) and a.keys()==b.keys() and all(equal(a[k],v) for k,v in b.items())
    if isinstance(b,list):
        return isinstance(a,list) and len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
    if isinstance(b,(int,float)) and not isinstance(b,bool):
        return isinstance(a,(int,float)) and math.isfinite(a) and abs(a-b)<=1e-12
    return type(a)==type(b) and a==b


def baseline_key(row):
    return row['phase']=='nonspeech-default',row['source_ordinal'],row['profile'],row['mode']


def canonical100(row):
    decision = next(d for d in row['decisions'] if d['percent']==100)
    expected = decision_from_rows(row['report']['candidates'],decision['cap'])
    require(all(decision[name]==value for name,value in expected.items()),'Canonical100 budget decision differs')
    identifier = decision['selected_id']
    require(identifier is not None,'A common canonical100 baseline is missing')
    value = row['report']['candidates'][identifier]
    require(value['automatic_quality_eligible'] and value['stream_bytes']<=decision['cap'],
            'Canonical100 source is not admitted')
    return identifier,value


def strongest(rows):
    require(bool(rows) and len({baseline_key(row) for row in rows})==1,'Different source/level contexts competed')
    return min(rows,key=lambda row:(canonical100(row)[1]['score'],canonical100(row)[1]['stream_bytes'],PRIORITY[row['phase']]))


def selection_context(context,rollback):
    names = ('job_id','baseline_id','phase','source_ordinal','profile','mode','arm','tier_label','percent')
    return tuple(context[name] for name in names)+(rollback,)


def manifest_map(items,chain):
    result = {}
    for item in items:
        blobs = chain(item,item['profile'])
        require(blobs not in result,'Duplicate selected ordered bytes in export inventory')
        contexts = []
        for context in item['contexts']:
            require(context['profile']==item['profile'],'Inventory context changed profile')
            rollback = chain(dict(samples=item['samples'],stream_bytes=sum(p['file_bytes'] for p in context['rollback']),
                                  segments=context['rollback']),item['profile'])
            contexts.append(selection_context(context,rollback))
        require(len(contexts)==len(set(contexts)),'Duplicate selected context in export inventory')
        result[blobs] = sorted(contexts)
    return result


def nonnegative(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>=0


def prepare(args):
    epoch = Epoch(args.source_root)
    union = Union(epoch.modules['speech_compact'].unpack)
    read = lambda path:json.loads(union.read(path))
    summary = read(args.export/'summary.json')
    export_binding = read(args.export/'binding-private.json')
    inventory = read(args.export/'changed-selected-chains-private.json')
    for path,digest in export_binding['inputs_sha256'].items():union.read(path,digest)
    require(summary['status']=='PASS' and summary['arm_records']==248 and summary['helper_calls']==312
            and summary['pair_contexts']==124 and summary['cap_views']==744 and not summary['new_initial_fits']
            and summary['no_old_whole_metric_reuse'] and not summary['end_to_end_same_cpu_claim']
            and summary['source_commit']==args.producer_commit,'Final finite study/export is incomplete')
    preflight = read(args.preflight/'summary.json')
    require(preflight==summary['synthetic_preflight'] and preflight['status']=='PASS'
            and preflight['warmup_only'] and preflight['helper_calls']==0,'Synthetic preflight gate differs')
    bindings,rows,provenance,events = [],[],[],[]
    for shard,folder in enumerate(args.shards):
        binding = read(folder/'binding-private.json')
        attempt = read(folder/'attempt-private.json')
        terminal = read(folder/'summary.json')
        results = read(folder/'results-private.json')
        origins = read(folder/'metric-cache-provenance-private.json')
        require(terminal['status']=='PASS' and not terminal['warmup_only'] and binding['shard']==terminal['shard']==shard
                and terminal['arm_records']==len(results)==len(binding['assigned_jobs'])
                and terminal['helper_calls']==len(attempt['helper_calls'])
                and not terminal['new_initial_fits'] and terminal['no_old_whole_metric_reuse']
                and attempt['status']=='complete' and not attempt['forbidden_fit_or_build_attempts']
                and len(attempt['arm_records'])==len(results)
                and all(e['status']=='complete' for e in attempt['helper_calls']+attempt['arm_records']),
                'A fixed source-parity study shard is not terminal PASS')
        require(binding['source_commit']==args.producer_commit,'Producer epoch differs')
        for name,digest in binding['research_sources'].items():union.read(args.trial_source/name,digest)
        for path,digest in binding['inputs_sha256'].items():union.read(path,digest)
        for name,digest in binding['production_sources'].items():union.read(Path(binding['source_root'])/name,digest)
        require([row['id'] for row in results]==binding['assigned_jobs']
                and all(row['source_ordinal']%2==shard for row in results),'Assigned fixed job order/parity differs')
        for row in results:
            folder_arm = folder/'arms'/('job-%03d'%row['id'])
            require(read(folder_arm/'result-private.json')==row and row['status']=='complete','Arm result changed')
            require([local['index'] for local in row['locals']]==row['edited_segments'],'Actual helper reset scope changed')
            for local in row['locals']:
                reset = folder_arm/('reset-%03d'%local['index'])
                returned = read(reset/'helper-return-private.json')
                endpoint = read(reset/'endpoint-private.json')
                event = read(reset/'attempt-private.json')
                require(returned['status']=='returned' and returned['cost']==local['helper_cost']
                        and returned['report']['cpu_budget']==local['cpu_budget'] and endpoint==local
                        and event['status']=='complete' and event['job_id']==row['id'] and event['reset']==local['index']
                        and event['cost']==local['helper_cost'],'Actual helper/CPU receipt changed')
                require(all(nonnegative(local['helper_cost'][name]) for name in ('cpu_seconds','wall_seconds')),
                        'Invalid measured helper cost')
                for part in local['captured_streams']:union.read(part['path'],part['stream_sha256'])
        require(len(origins)==sum(len(row['whole_rows']) for row in results),'Whole metric cache provenance is incomplete')
        bindings.append(binding);rows.extend(results);provenance.append(origins);events.extend(attempt['helper_calls'])
    require(len(rows)==248 and len({row['id'] for row in rows})==248 and len(events)==312
            and bindings[0]['research_sources']==bindings[1]['research_sources']
            and bindings[0]['production_sources']==bindings[1]['production_sources'],
            'Complete population, helper count or executing sources differ')
    require(bool(bindings[0]['research_commit']) and bindings[0]['research_commit']==bindings[1]['research_commit'],
            'Executing research source commits differ')

    base_path = Path(bindings[0]['baselines_path'])
    require(Path(bindings[1]['baselines_path'])==base_path,'Arms use different common baseline manifests')
    manifest = read(base_path)
    require(manifest['schema']=='lpx-matched-search-cpu-baselines-private-v1'
            and manifest['status']=='prepared-not-launched' and not manifest['search_outcomes_present']
            and len(manifest['baselines'])==104 and len(manifest['jobs'])==248,'Predeclared baseline scope changed')
    canonical = {}
    for path,digest in manifest['inputs_sha256'].items():
        raw = union.read(path,digest)
        if Path(path).name=='result-private.json':
            value = json.loads(raw)
            if all(name in value for name in ('phase','source_ordinal','profile','report','chains','decisions')):
                key = value['phase'],value['source_ordinal'],value['profile']
                require(key not in canonical or canonical[key][0]==value,'Conflicting canonical source result')
                canonical[key] = value,Path(path)
    require(len(canonical)==118,'The exact original canonical population is incomplete')
    grouped = defaultdict(list)
    for value,_ in canonical.values():grouped[baseline_key(value)].append(value)
    require(len(grouped)==104,'Canonical baseline context count changed')

    prior_raw = union.read(args.prior_handoff);prior = json.loads(prior_raw)
    prior_proof = read(args.prior_proof)
    retention_raw = union.read(args.retention_handoff);retention = json.loads(retention_raw)
    retention_proof = read(args.retention_proof)
    require(prior['image_launch_allowed'] and len(prior['chains'])==75 and prior_proof['status']=='complete'
            and prior_proof['handoff_sha256']==sha(prior_raw) and prior_proof['summary']['passed']==150,
            'Original75-chain/150-row complete proof differs')
    require(retention['image_launch_allowed'] and len(retention['chains'])==8 and retention_proof['status']=='complete'
            and retention_proof['handoff_sha256']==sha(retention_raw) and retention_proof['summary']['rows']==16
            and retention_proof['summary']['passed']==12 and retention_proof['summary']['no_fit']==4,
            'Retention8-chain/16-row complete proof differs')
    for old in (prior,retention):
        require(old['source_inventory']==epoch.snapshot(),'Frozen player consumer changed')
        for field in ('input_files_sha256','dispatcher_sources_sha256'):
            for path,digest in old[field].items():union.read(path,digest)
    prepared = read(Path(prior['admission_gate']['prepared_path']))
    require(prepared['source_inventory']==epoch.snapshot(),'Player source preparation changed')
    audit = read(Path(prior['admission_gate']['private_audit_path']))
    require(audit['status']=='passed' and audit['completed_records']==audit['expected_records']==118
            and not audit['missing_records'] and audit['all_final_worker_receipts_verified']
            and audit['binding_sha256']==prior['study_binding_sha256']
            and audit['auditor_sha256']==sha(union.read(prior['admission_gate']['auditor_source'])),
            'Original independent118-record source gate differs')
    study = Path(prior['study_root'])
    helper_path = args.trial_source.parent/'v5-canonical-retention-corpus-2026-10-30/saved_corpus.py'
    union.read(helper_path);helper = loaded_module(helper_path);inputs = helper.Inputs()
    original_binding,originals = helper.load_saved(study,inputs)
    indexed = {helper.key(item['saved']):item for item in originals}
    require(set(canonical)==set(indexed),'Canonical source population differs from original audit')
    consumer = {n:d for n,d in epoch.snapshot().items() if n.startswith('Codecs/LPX/01_ACTIVE_Q0_CODEC/src/')}
    producer = {n:d for n,d in bindings[0]['production_sources'].items() if n.startswith('Codecs/LPX/01_ACTIVE_Q0_CODEC/src/')}
    require(consumer==producer,'Producer and player decoder sources differ')
    bases = {base['id']:base for base in manifest['baselines']}
    require(set(bases)==set(range(104)),'Common baseline IDs differ')
    for base in bases.values():
        identity = base['nonspeech'],base['source_ordinal'],base['profile'],base['mode']
        winner = strongest(grouped[identity]);identifier,value = canonical100(winner)
        item = indexed[(winner['phase'],winner['source_ordinal'],winner['profile'])]
        require(base['source_phase']==winner['phase'] and base['canonical_whole_candidate_id']==identifier
                and base['samples']==winner['samples'] and base['stream_bytes']==value['stream_bytes']
                and base['canonical_whole_value']==value and read(Path(base['source_result_path']))==winner,
                'Common baseline is not the strongest exact canonical100 whole source')
        require(base['reference']==item['record']['reference'] and base['level']==item['saved']['level']
                and base['target_reference_pcm16_sha256']==item['saved']['target_reference_pcm16_sha256'],
                'Common baseline reference/declared-level provenance changed')
        entry = dict(samples=base['samples'],stream_bytes=base['stream_bytes'],segments=base['segments'])
        expected = {**entry,'segments':winner['chains'][identifier]['segments']}
        require(union.chain(entry,base['profile'])==union.chain(expected,base['profile']),
                'Common baseline ordered bytes changed')
    jobs = {job['id']:job for job in manifest['jobs']}
    require(set(jobs)==set(range(248)),'Predeclared arm IDs changed')
    row_index = {row['id']:row for row in rows}
    actual,comparisons,view_counts = {},{},Counter()
    blobs_by_job = {}
    model_parts = {}
    def register(entry,profile,blobs,role):
        pcm_sha = pwm_sha = None
        if entry['stream_bytes']<=FLASH_BYTES:
            import numpy as np
            for blob in blobs:
                if blob not in model_parts:model_parts[blob]=epoch.modules['speech_compact'].decode_model(blob)
            pcm = np.concatenate([model_parts[blob] for blob in blobs])
            require(len(pcm)==entry['samples'],'Expected whole model length changed')
            pcm_sha = sha(pcm.astype('<i2').tobytes())
            pwm_sha = sha(epoch.modules['standard_metrics'].pwm_duties(pcm).tobytes())
        return union.register({**entry,'pcm16_sha256':pcm_sha,'pwm_sha256':pwm_sha},profile,blobs,role)
    for row in sorted(rows,key=lambda value:value['id']):
        job = jobs[row['id']];base = bases[job['baseline_id']]
        require(all(row[name]==value for name,value in job.items()),'Actual arm differs from fixed job')
        require(row['baseline_samples']==base['samples'] and row['reset_segments']==len(base['segments'])
                and row['arm'] in ('single-path','trajectory') and row['cpu_seconds_per_reset'] in (2,8)
                and row['whole_byte_caps']=={str(p):base['stream_bytes']*p//100 for p in (100,95,90)},
                'Arm baseline/tier/data budgets changed')
        require([d['percent'] for d in row['decisions']]==[100,95,90],'Cap decision population changed')
        values,artifacts = row['whole_rows'],row['whole_chains']
        require(len(values)==len(artifacts) and values,'Whole artifact/metric population differs')
        blobs = []
        for identifier,(value,artifact) in enumerate(zip(values,artifacts)):
            require(value['id']==artifact['id']==identifier
                    and value['automatic_quality_eligible']==all(value[flag] for flag in FLAGS),
                    'Whole row identity or quality flags changed')
            blobs.append(union.chain(dict(samples=base['samples'],stream_bytes=value['stream_bytes'],segments=artifact['segments']),base['profile']))
        baseline_entry = dict(samples=base['samples'],stream_bytes=base['stream_bytes'],segments=base['segments'])
        baseline = union.chain(baseline_entry,base['profile'])
        require(blobs[0]==baseline and all(equal(values[0][name],base['canonical_whole_value'][name]) for name in VALUE_KEYS),
                'Measured anchor is not the exact common canonical baseline')
        blobs_by_job[row['id']] = blobs
        helper_cpu = sum(local['helper_cost']['cpu_seconds'] for local in row['locals'])
        require(equal(helper_cpu,row['total_helper_cpu']),'Actual helper total differs')
        prior2 = [r for r in rows if r['baseline_id']==row['baseline_id'] and r['arm']==row['arm'] and r['cpu_seconds_per_reset']==2]
        require(len(prior2)==1,'The same-arm tier2 incumbent is missing or repeated')
        prior_cpu = 0 if row['cpu_seconds_per_reset']==2 else prior2[0]['total_helper_cpu']
        require(row['tier_label']==('2' if row['cpu_seconds_per_reset']==2 else 'cumulative-2+8')
                and equal(row['prior2_helper_cpu'],prior_cpu)
                and equal(row['cumulative_total_helper_cpu'],helper_cpu+prior_cpu),
                'Cumulative tier2+8 accounting differs')
        if row['cpu_seconds_per_reset']==8:
            require(row['prior2_whole_views']==len(prior2[0]['whole_rows'])
                    and set(blobs_by_job[prior2[0]['id']]).issubset(set(blobs)),
                    'A retained same-arm tier2 whole chain disappeared')
        for decision in row['decisions']:
            expected = decision_from_rows(values,base['stream_bytes']*decision['percent']//100)
            require(all(decision[name]==value for name,value in expected.items()) and decision['incumbent_nonregression'],
                    'Actual final automatic budget decision differs')
            identifier = decision['selected_id']
            if identifier is None:view_counts['no-automatic-selection']+=1;continue
            if blobs[identifier]==baseline:view_counts['unchanged-baseline']+=1;continue
            view_counts['changed-automatic-selection']+=1
            context = dict(job_id=row['id'],baseline_id=base['id'],phase=row['phase'],source_ordinal=row['source_ordinal'],
                profile=row['profile'],mode=row['mode'],arm=row['arm'],tier_label=row['tier_label'],percent=decision['percent'])
            actual.setdefault(blobs[identifier],[]).append(selection_context(context,baseline))
            old = register(baseline_entry,base['profile'],baseline,'declared-level-rollback')
            entry = dict(samples=base['samples'],stream_bytes=values[identifier]['stream_bytes'],segments=artifacts[identifier]['segments'])
            new = register(entry,base['profile'],blobs[identifier],'changed-automatic-selection')
            ckey = base['id'],old,new
            if ckey not in comparisons:
                comparisons[ckey] = dict(id='comparison-%03d'%(len(comparisons)+1),baseline_id=base['id'],
                    rollback_chain=old,candidate_chain=new,profile=base['profile'],cohort='nonspeech' if base['nonspeech'] else 'speech',
                    source_ordinal=base['source_ordinal'],mode=base['mode'],input_gain=base['level']['gain'],
                    reference_domain='declared-auto-target' if base['mode']=='auto-quiet' else 'original-level',
                    perceptual_adoption=False,selections=[])
            comparisons[ckey]['selections'].append({**context,'cap':decision['cap'],'role':'whole-%03d'%identifier})
    require(sum(view_counts.values())==744,'Cap views do not partition the fixed study')
    require(manifest_map(inventory,union.chain)=={blobs:sorted(contexts) for blobs,contexts in actual.items()}
            and len(actual)==summary['distinct_changed_selected_whole_chains'],
            'Final inventory does not exactly match all changed automatic choices')
    for origins,binding in zip(provenance,bindings):
        seen,covered = {},set()
        for origin in origins:
            event = origin['event'];row = row_index[event['job_id']];base = bases[row['baseline_id']]
            event_key = event['job_id'],event['chain_id']
            require(event_key not in covered and event['baseline_id']==base['id'],'Whole provenance event is repeated')
            covered.add(event_key)
            key = (base['target_reference_pcm16_sha256'],row['speech'],binding['source_context'],tuple(blobs_by_job[row['id']][event['chain_id']]))
            digest = sha(repr(key).encode())
            require(origin['key_sha256']==digest and all(nonnegative(origin['evaluation_body_cost'][name]) for name in ('cpu_seconds','wall_seconds')),
                    'Whole cache key or actual creating-event cost differs')
            require(origin['reused_from']==seen.get(digest),'Whole metrics were not created inside this exact study shard')
            seen.setdefault(digest,event)
        require(len(covered)==sum(len(row_index[i]['whole_rows']) for i in binding['assigned_jobs']),
                'Whole creating-event provenance coverage differs')
    for name,digest in original_binding['native_libraries_sha256'].items():union.read(study/'native'/name,digest)
    inputs.verify()
    for path,digest in inputs.pins.items():union.read(path,digest)
    prior_paths = list(map(Path,prior['admission_gate']['prior_paths']))+[args.prior_proof.parent,args.retention_proof.parent]
    for directory in prior_paths:require(read(directory/'results-private.json')['status']=='complete','Prior evidence index incomplete')
    sources = (THIS,HERE/'test_preparation.py',PACKAGE/'PROTOCOL.md',GENERIC/'measure_union.py',GENERIC/'prepare_union.py',
               GENERIC/'test_protocol.py',GENERIC.parent/'PROTOCOL.md',RETENTION/'prepare_retention.py',
               Path(sys.modules['admit'].__file__),Path(sys.modules['admit'].__file__).parent/'player_evidence.py')
    source_pins = {str(path):sha(path.read_bytes()) for path in sources}
    chains = list(union.registry.values())
    selected = {item['id'] for item in chains if 'changed-automatic-selection' in item['roles']}
    rollback = {item['id'] for item in chains if 'declared-level-rollback' in item['roles']}
    stats = dict(schema='lpx-v5-matched-search-player-scope-v1',image_launch_allowed=bool(chains),
        preliminary_unaudited=False,independent_audit_gate='passed',all_six_workers_complete=True,
        expected_records=118,observed_complete_records=118,missing_records=0,
        trial_arm_records=248,trial_helper_calls=312,trial_cap_views=744,common_baseline_contexts=104,
        automatic_changed_selection_views=view_counts['changed-automatic-selection'],
        unchanged_selection_views_skipped=view_counts['unchanged-baseline'],no_automatic_selection_views=view_counts['no-automatic-selection'],
        distinct_union_chains=len(chains),distinct_candidate_chains=len(selected),distinct_rollback_chains=len(rollback),
        candidate_rollback_overlap=len(selected & rollback),distinct_comparisons=len(comparisons),logical_image_rows=2*len(chains),
        selected_image_rows=2*len(selected),rollback_image_rows=2*len(rollback),
        data_alone_no_fit_rows=2*sum(item['entry']['file_bytes']>FLASH_BYTES for item in chains),
        maximum_new_build_attempts=2*sum(item['entry']['file_bytes']<=FLASH_BYTES for item in chains),
        potential_full_playback_samples=2*sum(item['entry']['samples'] for item in chains if item['entry']['file_bytes']<=FLASH_BYTES),
        maximum_chain_segments=max((len(item['entry']['segments']) for item in chains),default=0),
        new_fits=0,new_refinements=0,new_images=0,new_simulations=0,perceptual_adoption=False,
        scope='Final248-arm/744-view changed automatic whole choices versus exact strongest common canonical100 baseline. Original118-record audit is a separate source gate; no images or quality adoption at preparation.')
    handoff = dict(schema='lpx-v5-adaptive-player-union-final-private-v1',image_launch_allowed=bool(chains),
        study_root=str(study),study_binding_sha256=prior['study_binding_sha256'],producer_core_commit=args.producer_commit,
        consumer_root=str(epoch.root),source_inventory=epoch.snapshot(),chains=chains,comparisons=list(comparisons.values()),missing=[],summary=stats,
        input_files_sha256=union.inputs,dispatcher_sources_sha256=source_pins,
        admission_gate={**prior['admission_gate'],'prior_paths':list(map(str,prior_paths))},
        configuration=dict(irq_loads=[0,100],queue=256,prefill=192,assembly=True,flash_bytes=FLASH_BYTES),
        matched_search_gate=dict(status='passed',arm_records=248,helper_calls=312,cap_views=744,common_baselines=104,
            export_root=str(args.export),trial_source=str(args.trial_source),producer_commit=args.producer_commit,
            research_commit=bindings[0]['research_commit'],
            replay_shards=list(map(str,args.shards)),end_to_end_same_cpu_claim=False,perceptual_adoption=False))
    require(epoch.snapshot()==prior['source_inventory'],'Consumer source changed during preparation')
    for path,digest in union.inputs.items():require(sha(Path(path).read_bytes())==digest,'A final bound input changed')
    for path in (args.output,args.public_output):require(not path.exists(),'Use fresh immutable preparation outputs')
    epoch.modules['output_paths'].protect_outputs([*map(Path,union.inputs),*sources],[args.output,args.public_output])
    epoch.save(args.output,handoff)
    args.public_output.parent.mkdir(parents=True,exist_ok=True)
    args.public_output.write_bytes(json.dumps(stats,indent=2,allow_nan=False).encode()+b'\n')
    print(json.dumps(stats),flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-root','export','trial-source','preflight','prior-handoff','prior-proof',
                 'retention-handoff','retention-proof','output','public-output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--shards',type=Path,nargs=2,required=True)
    parser.add_argument('--producer-commit',required=True)
    args = parser.parse_args()
    for name in ('source_root','export','trial_source','preflight','prior_handoff','prior_proof',
                 'retention_handoff','retention_proof','output','public_output'):
        setattr(args,name,getattr(args,name).resolve())
    args.shards = list(map(Path.resolve,args.shards))
    try:prepare(args)
    except Exception as exc:
        target = args.output.with_name('preparation-failure-private.json')
        target.parent.mkdir(parents=True,exist_ok=True)
        require(not target.exists(),'Preserve the earlier failed preparation')
        target.write_bytes(json.dumps(dict(exception_type=type(exc).__name__,traceback=traceback.format_exc()),indent=2).encode()+b'\n')
        print(json.dumps(dict(status='failed',exception_type=type(exc).__name__)),flush=True)
        return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
