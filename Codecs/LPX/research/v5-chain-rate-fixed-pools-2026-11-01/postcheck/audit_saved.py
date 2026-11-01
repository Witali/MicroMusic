"""Saved-only chain-study verification/export; no allocator or codec imports."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import time

STUDY_COMMIT='700147a571aacaf56b9587053e7f96385d403bc6'
PRODUCER='654ada493202f565d24cb9dcf22f16137c825329'
VALUE_KEYS=('metrics','voice','pwm_voice','noise','pwm_noise','domain_scores','score',
            'clipped_samples','voice_components','pwm_voice_components')
PERCENTS=(100,95,90)


def sha(raw):return hashlib.sha256(raw).hexdigest()
def load(path):return json.loads(Path(path).read_bytes())
def save(path,value):Path(path).write_bytes((json.dumps(value,indent=2,allow_nan=False)+'\n').encode())


def same(a,b):
    if isinstance(b,dict):
        assert isinstance(a,dict) and a.keys()==b.keys()
        for k in b:same(a[k],b[k])
    elif isinstance(b,list):
        assert isinstance(a,list) and len(a)==len(b)
        for x,y in zip(a,b):same(x,y)
    elif isinstance(b,(int,float)) and not isinstance(b,bool):assert abs(a-b)<=1e-12
    else:assert a==b and type(a)==type(b)


def flags(row,anchor):
    old=True
    for domain in ('pcm16','pwm8'):
        a,b=row['metrics'][domain],anchor['metrics'][domain]
        old &= a['error_energy']<=b['error_energy']
        old &= b['stoi'] is None or a['stoi'] is not None and a['stoi']>=b['stoi']-1e-12
    return dict(old_pcm_pwm_floors_passed=bool(old),
        clipped_sample_floor_passed=row['clipped_samples']<=anchor['clipped_samples'],
        pcm_period_coverage_floor_passed=row['voice']['within_tolerance_frames']>=anchor['voice']['within_tolerance_frames'],
        pwm_period_coverage_floor_passed=row['pwm_voice']['within_tolerance_frames']>=anchor['pwm_voice']['within_tolerance_frames'],
        joint_objective_nonregression=row['score']<=anchor['score']+1e-12)


def choose(rows,cap):
    fitting=[r for r in rows if r['stream_bytes']<=cap]
    eligible=[r for r in fitting if r['automatic_quality_eligible']]
    key=lambda r:(r['score'],r['stream_bytes'],r['id'])
    return dict(cap=cap,full_flash_cap=None,
        selected_id=None if not eligible else min(eligible,key=key)['id'],
        raw_id=None if not fitting else min(fitting,key=key)['id'],
        fitting_chains=len(fitting),eligible_chains=len(eligible),no_fit=not fitting,no_automatic_admission=not eligible)


def outcome(old,new,absent,exact):
    if new is None:return dict(kind='no-new-admission',exact_primary_success=False)
    kind=('new-admission' if old is None else 'lower-joint-score' if new['score']<old['score']-1e-12
          else 'smaller-no-worse-joint' if new['stream_bytes']<old['stream_bytes'] and new['score']<=old['score']+1e-12
          else 'no-strict-win')
    success=absent and kind not in ('no-new-admission','no-strict-win')
    return dict(kind=kind,absent_from_original_five=absent,new_admitted_win=success,
                exact_primary_success=success and exact,nonexact_retained_success=success and not exact)


def dominates(old,new):
    return old['automatic_quality_eligible'] and old['stream_bytes']<=new['stream_bytes'] and old['score']<=new['score']+1e-12


def archive_hashes(root,commit,names):
    raw=subprocess.check_output(['git','-C',str(root),'archive',commit,'--',*names])
    wanted=set(names);found={}
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for member in archive:
            if member.isfile() and member.name in wanted:found[member.name]=sha(archive.extractfile(member).read())
    assert found.keys()==wanted
    return found


def audit(args):
    began=time.perf_counter(),time.process_time();pins={}
    def read(path,digest=None):
        path=Path(path).resolve();raw=path.read_bytes();value=sha(raw)
        assert digest is None or digest==value
        assert str(path) not in pins or pins[str(path)]==value
        pins[str(path)]=value
        return raw
    def document(path,digest=None):return json.loads(read(path,digest))
    manifest=document(args.prepared/'manifest-private.json')
    closed=document(args.prepared/'complete-private.json')
    assert closed['status']=='complete' and closed['manifest_sha256']==pins[str((args.prepared/'manifest-private.json').resolve())]
    assert manifest['producer_commit']==PRODUCER and Path(manifest['producer_root']).resolve()==args.root
    assert archive_hashes(args.root,PRODUCER,list(manifest['production_sources']))==manifest['production_sources']
    assert archive_hashes(args.root,STUDY_COMMIT,list(manifest['study_sources']))==manifest['study_sources']
    for name,digest in {**manifest['production_sources'],**manifest['study_sources']}.items():read(args.root/name,digest)
    for name,digest in manifest['input_files_sha256'].items():read(name,digest)
    terminal=document(args.run/'complete-private.json');assert terminal['status']=='complete'
    for name,digest in terminal['files_sha256'].items():read(args.run/name,digest)
    binding=document(args.run/'binding-private.json');summary=document(args.run/'summary.json')
    clocks={}
    for phase in ('preflight','run'):
        receipt=document(args.run.parent/(phase+'-process-private.json'))
        assert receipt['status']=='terminal' and receipt['phase']==phase and receipt['exit_code']==0
        read(args.run.parent/'launch_study.py',receipt['launcher_sha256'])
        read(args.run.parent/'invoke_study.py',receipt['invocation_sha256'])
        assert receipt['full_child_process_cpu_seconds']>=0 and receipt['full_child_process_wall_seconds']>0
        clocks[phase]={name:receipt[name] for name in ('full_child_process_cpu_seconds','full_child_process_wall_seconds')}
    assert binding['study_sources']==manifest['study_sources'] and binding['production_sources']==manifest['production_sources']
    for name,digest in binding['input_files_sha256'].items():read(name,digest)
    for name,digest in binding['artifact_files_sha256'].items():read(args.run/name,digest)
    rows=document(args.run/'rows.json');secondary=document(args.run/'secondary.json')
    provenance=document(args.run/'metric-cache-provenance-private.json');attempt=document(args.run/'attempt-private.json')
    assert summary['status']=='PASS' and not summary['synthetic_only'] and summary['dp_calls']==60
    assert attempt['status']=='complete' and attempt['dp_calls_started']==attempt['dp_calls_returned']==60
    assert attempt['active_dp'] is None and not attempt['forbidden_work_attempts']
    assert len(rows)==len(manifest['jobs'])==60 and sorted(r['id'] for r in rows)==list(range(60))
    assert summary['new_helpers']==summary['new_fits']==summary['new_native_builds']==summary['target_jobs']==0
    expected_events=[];all_parts={};checked_parts={};records={};contexts={};primary=[];dpwork=Counter();peaks=[]
    def values(row):return {k:row[k] for k in VALUE_KEYS}
    for job,public in zip(manifest['jobs'],rows):
        assert public['id']==job['id']
        folder=args.run/'arms'/('job-%03d'%job['id'])
        private=document(folder/'result-private.json');allocation=document(folder/'allocation-private.json')
        assert private['public']==public and private['context']==binding['context']
        pools=[]
        for local,meta in zip(job['pools'],job['baseline']):
            options={}
            assert len(local['rows'])<=19
            for item in local['rows']:
                stream=item['stream'];blob=read(stream['path'],stream['stream_sha256'])
                assert len(blob)==stream['file_bytes'] and blob[:4]==b'L4HY' and blob[4]==5
                assert int.from_bytes(blob[8:12],'little')==meta['samples'] and blob[5]&127==job['profile']
                assert type(item['sse']) is int and item['sse']>=0
                options[item['id']]=(blob,item['sse']);all_parts[blob]=meta['samples']
            pools.append(options)
        def point(point):
            assert len(point['ids'])==len(pools)
            parts=tuple(p[k][0] for p,k in zip(pools,point['ids']))
            assert point['file_bytes']==sum(map(len,parts))
            assert point['sse']==sum(p[k][1] for p,k in zip(pools,point['ids']))
            return parts
        result=allocation['result'];frontier=result['frontier'];previous_size=-1;previous_sse=None
        assert result['exact']==public['exact'] and result['status']==public['dp_status']
        assert result['work']['transitions']<=10000000 and result['work']['peak_states']<=250000
        for p in frontier:
            point(p);assert p['file_bytes']<=job['baseline_bytes'] and p['file_bytes']>previous_size
            assert previous_sse is None or p['sse']<previous_sse
            previous_size,previous_sse=p['file_bytes'],p['sse']
        if result['exact']:
            assert result['status'] in ('complete','no_pool_combination_fits')
            assert result['best']==(min(frontier,key=lambda p:(p['sse'],p['file_bytes'],p['ids'])) if frontier else None)
            assert result['work']['processed_resets']==len(pools) or not frontier
        else:assert result['status'] in ('state_limit','transition_limit') and not frontier and result['best'] is None
        assert allocation['retained']['callback_completed']==result['work']['completed_candidates']
        views=[dict(ids=old['ids'],labels=list(old['labels'])) for old in job['originals']]
        def parts_for(ids):return tuple(p[k][0] for p,k in zip(pools,ids))
        positions={parts_for(v['ids']):i for i,v in enumerate(views)}
        for percent in PERCENTS:
            winner=allocation['winners'][str(percent)];cap=job['caps'][str(percent)]
            if result['exact']:
                fits=[p for p in frontier if p['file_bytes']<=cap]
                assert winner==(min(fits,key=lambda p:(p['sse'],p['file_bytes'],p['ids'])) if fits else None)
            else:assert winner==allocation['retained']['best'].get(str(percent))
            if winner is None:continue
            parts=point(winner);assert sum(map(len,parts))<=cap
            label='dp-%s-%d'%('exact' if result['exact'] else 'retained-nonexact',percent)
            if parts in positions:views[positions[parts]]['labels'].append(label)
            else:positions[parts]=len(views);views.append(dict(ids=winner['ids'],labels=[label]))
            if len(pools)==1 and result['exact']:
                candidates=[dict(ids=[k],file_bytes=len(v[0]),sse=v[1]) for k,v in pools[0].items() if len(v[0])<=cap]
                assert winner==min(candidates,key=lambda p:(p['sse'],p['file_bytes'],p['ids']))
        assert private['tuples']==views and len(views)<=len(job['originals'])+3
        whole=private['complete_whole_rows'];assert len(whole)==len(views)==len(public['whole_rows'])
        expected_events.append((dict(job_id=job['id'],role='baseline-before-dp'),parts_for(views[0]['ids']),private['anchor'],job))
        for i,(view,value) in enumerate(zip(views,whole)):
            parts=parts_for(view['ids']);assert value['id']==i and value['labels']==view['labels']
            for blob in parts:checked_parts[blob]=all_parts[blob]
            assert value['stream_bytes']==sum(map(len,parts))
            assert value['additive_pcm_sse']==sum(p[k][1] for p,k in zip(pools,view['ids']))==value['metrics']['pcm16']['error_energy']
            f=flags(value,private['anchor']);assert all(value[k]==v for k,v in f.items())
            assert value['automatic_quality_eligible']==all(f.values())
            assert all(value[k]==v for k,v in public['whole_rows'][i].items())
            if i<len(job['originals']):
                for key in VALUE_KEYS:same(value[key],job['originals'][i]['old_value'][key])
            expected_events.append((dict(job_id=job['id'],chain_id=i),parts,value,job))
        for d in public['decisions']:
            cap=job['caps'][str(d['percent'])];old=choose(whole[:len(job['originals'])],cap);new=choose(whole,cap)
            assert old==d['old'] and new==d['new']
            a=None if old['selected_id'] is None else whole[old['selected_id']]
            b=None if new['selected_id'] is None else whole[new['selected_id']]
            absent=b is not None and parts_for(views[b['id']]['ids']) not in {parts_for(v['ids']) for v in views[:len(job['originals'])]}
            o=outcome(a,b,absent,result['exact']);assert all(d[k]==v for k,v in o.items())
            if o['exact_primary_success']:
                primary.append(dict(id=job['id'],source_ordinal=job['source_ordinal'],profile=job['profile'],arm=job['arm'],
                    percent=d['percent'],mechanism=public['mechanism'],kind=o['kind'],old_bytes=d['old_bytes'],
                    new_bytes=d['new_bytes'],old_score=d['old_score'],new_score=d['new_score']))
        records[job['id']]=(job,public,private,[parts_for(v['ids']) for v in views])
        context=contexts.setdefault(job['baseline_id'],{})
        for i,value in enumerate(whole[:len(job['originals'])]):
            key=parts_for(views[i]['ids'])
            if key in context:
                for field in VALUE_KEYS:same(value[field],context[key]['value'][field])
                context[key]['origins'].append(dict(job=job['id'],chain=i,arm=job['arm']))
            else:context[key]=dict(value=value,origins=[dict(job=job['id'],chain=i,arm=job['arm'])])
        dpwork.update({k:v for k,v in result['work'].items() if type(v) is int and k!='peak_states'})
        peaks.append(result['work']['peak_states'])
    assert len(expected_events)==len(provenance)==summary['whole_counters']['fresh_whole_metric_rows_completed']+summary['whole_counters']['whole_metric_cache_hits']
    seen={};fresh=hits=0
    for (event,parts,value,job),saved in zip(expected_events,provenance):
        key=(job['base']['prepared_target']['pcm16_sha256'],not job['nonspeech'],binding['context'],parts)
        digest=sha(repr(key).encode());assert saved['event']==event and saved['key_sha256']==digest
        if digest not in seen:
            assert saved['reused_from'] is None;seen[digest]=(event,values(value));fresh+=1
        else:
            assert saved['reused_from']==seen[digest][0];same(values(value),seen[digest][1]);hits+=1
    assert fresh==summary['whole_counters']['fresh_whole_metric_rows_completed'] and hits==summary['whole_counters']['whole_metric_cache_hits']
    assert fresh==summary['whole_counters']['fresh_whole_metric_rows_started']
    assert len(checked_parts)==summary['whole_counters']['unique_verified_reset_streams']
    assert sum(checked_parts.values())==summary['whole_counters']['verified_model_samples']
    assert len(checked_parts)*4==summary['whole_counters']['native_domain_comparisons']
    assert len({j['base']['prepared_target']['pcm16_sha256'] for j in manifest['jobs']})==summary['whole_counters']['target_feature_rows']
    assert sum(len(record[2]['complete_whole_rows']) for record in records.values())==summary['fresh_integer_whole_sse_checks']
    assert sum(len(pool['rows']) for j in manifest['jobs'] for pool in j['pools'])==summary['reused_v1_integer_sse_rows']
    assert len(primary)==summary['exact_primary_wins']
    assert len(secondary['rows'])==180
    for saved in secondary['rows']:
        job,public,private,parts=records[saved['id']]
        context=contexts[job['baseline_id']]
        originals=[dict(entry['value'],id=i) for i,entry in enumerate(context.values())]
        old=choose(originals,job['caps'][str(saved['percent'])])
        control=None if old['selected_id'] is None else originals[old['selected_id']]
        decision=next(d for d in public['decisions'] if d['percent']==saved['percent'])
        identifier=decision['new']['selected_id']
        new=None if identifier is None else private['complete_whole_rows'][identifier]
        absent=new is not None and parts[identifier] not in context
        extension=new is not None and new['automatic_quality_eligible'] and absent and not any(dominates(old,new) for old in originals)
        assert saved['context_original_choices']==len(originals)
        assert saved['absent_from_context_original_union']==absent
        assert saved['known_other_arm_point']==(decision.get('absent_from_original_five',False) and new is not None and not absent)
        assert saved['context_frontier_extension']==extension
        assert saved['context_rank_comparison']==outcome(control,new,absent,public['exact'])['kind']
        assert saved['old_context_bytes']==(None if control is None else control['stream_bytes'])
        assert saved['old_context_score']==(None if control is None else control['score'])
    assert sum(r['known_other_arm_point'] for r in secondary['rows'])==summary['secondary_known_other_arm_views']
    expected_frontier=[(job['id'],i,p) for job,public,private,parts in records.values()
        for i in range(public['original_recipes'],len(private['complete_whole_rows']))
        for p in PERCENTS if private['complete_whole_rows'][i]['stream_bytes']<=job['caps'][str(p)]]
    assert [(r['id'],r['chain_id'],r['percent']) for r in secondary['frontier_rows']]==expected_frontier
    classifications=[];extensions=set()
    for saved in secondary['frontier_rows']:
        job,public,private,parts=records[saved['id']];value=private['complete_whole_rows'][saved['chain_id']]
        prior=contexts[job['baseline_id']];known=parts[saved['chain_id']] in prior
        dominant=[entry for entry in prior.values() if dominates(entry['value'],value)]
        extension=value['automatic_quality_eligible'] and not known and not dominant
        assert saved['known_other_arm_point']==known and saved['absent_from_context_original_union']==(not known)
        assert saved['context_frontier_extension']==extension and saved['exact_context_frontier_extension']==(extension and public['exact'])
        if extension and public['exact']:extensions.add((job['baseline_id'],saved['percent'],parts[saved['chain_id']]))
        classification=('rejected-whole-gates' if not value['automatic_quality_eligible'] else
            'known-other-V1-arm-tuple' if known else 'dominated-or-equivalent-context-original' if dominant else 'context-frontier-extension')
        classifications.append(dict(**saved,classification=classification,
            related_originals=[origin for entry in ([prior[parts[saved['chain_id']]]] if known else dominant) for origin in entry['origins']]))
    assert len(extensions)==secondary['exact_distinct_context_cap_tuples']==summary['secondary_exact_distinct_context_cap_tuples']
    assert len(classifications)==len(secondary['frontier_rows'])
    assert sum(r['exact_context_frontier_extension'] for r in classifications)==summary['secondary_exact_context_frontier_views']
    assert all(sha(Path(name).read_bytes())==digest for name,digest in pins.items())
    costs=dict(metadata_preparation_execute_body=manifest['preparation_cost'],
        synthetic_preflight_process=clocks['preflight'],
        synthetic_preflight_execute_body=document(args.run.parent/'preflight-v1/summary.json')['actual_cost'],
        real_campaign_process=clocks['run'],real_campaign_execute_body=summary['actual_cost'],
        dp_cpu_seconds=summary['dp_cpu_seconds'],dp_wall_seconds_sum=summary['dp_wall_seconds_sum'],
        prior_v1_raw_model_audit_cpu_seconds=summary['prior_v1_raw_model_audit_cpu_seconds'],
        process_cpu_scope='Windows worker-process kernel+user through exit; excludes git/source-binding subprocess CPU and external launcher',
        execute_body_scope='execute() entry through pre-terminal snapshot; excludes imports/CLI and final receipt writes',
        overlapping_clocks_must_not_be_added=True)
    report=dict(status='PASS',saved_only=True,new_dp_model_metric_native_calls=0,records=60,cap_views=180,
        exact_records=sum(r['exact'] for r in rows),single_reset_controls=sum(r['single_reset_identity_checked'] for r in rows),
        within_arm_exact_primary_wins=len(primary),context_frontier_extensions=len(extensions),
        exact_cache_fresh_rows=fresh,exact_cache_reuses=hits,dp_work_sums=dict(dpwork),maximum_dp_peak_states=max(peaks),
        classification_counts=dict(Counter(r['classification'] for r in classifications)),
        source_inventory_files=len(manifest['production_sources']),study_recipe_files=len(manifest['study_sources']),
        execution_production_commit=PRODUCER,execution_study_commit=STUDY_COMMIT,
        audit_cost=dict(wall_seconds=time.perf_counter()-began[0],cpu_seconds=time.process_time()-began[1]))
    args.output.mkdir(parents=True,exist_ok=False)
    save(args.output/'audit-summary.json',report);save(args.output/'primary-wins.json',primary)
    save(args.output/'classifications.json',classifications)
    save(args.output/'costs.json',costs)
    save(args.output/'binding-private.json',dict(status='PASS',inputs_sha256=pins,
        auditor_sha256=sha(Path(__file__).read_bytes())))
    if args.public is not None:
        args.public.mkdir(parents=True,exist_ok=False)
        for name,value in (('audit-summary.json',report),('summary.json',summary),('rows.json',rows),
                           ('secondary.json',secondary),('primary-wins.json',primary),('classifications.json',classifications),('costs.json',costs)):
            save(args.public/name,value)
        save(args.public/'sources.json',dict(production_commit=PRODUCER,study_commit=STUDY_COMMIT,
            production_sources=manifest['production_sources'],study_sources=manifest['study_sources'],
            postcheck_sha256=sha(Path(__file__).read_bytes()),private_asset_bindings_exported=False))
    print(json.dumps(report),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','prepared','run','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--public',type=Path);args=p.parse_args()
    for name in ('root','prepared','run','output','public'):
        if getattr(args,name) is not None:setattr(args,name,getattr(args,name).resolve())
    audit(args)


if __name__=='__main__':main()
