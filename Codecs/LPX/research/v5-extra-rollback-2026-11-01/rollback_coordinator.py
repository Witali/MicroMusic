"""One bounded four-stage recording, with immediate tuple/value retention."""
from __future__ import annotations
from collections import defaultdict
from pathlib import Path
import time

from rollback_policy import accept_block,coverage_targets,retained_attempts
from rollback_runtime import VALUE_KEYS,equal,save,sha
from run_pilot import persist_stream
from run_existing import validate_fields as validate_frozen_fields


def clock():return time.perf_counter(),time.process_time()
def elapsed(t):return dict(wall_seconds=time.perf_counter()-t[0],cpu_seconds=time.process_time()-t[1])


def progress(walk):
    return dict(covered=walk.covered,trials=walk.trials,cursor=walk.cursor,visited=list(walk.visited),
        active=walk.active,cumulative_changed=walk.changed,committed_changed_groups=walk.committed_changed_groups)


def run_record(job,base,target,C,evaluator,inputs,out,attempt,phase,old_control=None):
    begin=clock();folder=out/phase/('record-'+str(job['id']));folder.mkdir(parents=True)
    timing=defaultdict(lambda:dict(calls=0,wall_seconds=0.,cpu_seconds=0.))
    record=dict(id=job['id'],phase=phase,arm=job['arm'],baseline_id=base['id'],status='started',
        stage_events=[],points=[],api_call_costs=timing)
    attempt['records'].append(record)
    def journal():save(out/'attempt-private.json',attempt)
    def call(kind,function,*args,**kwargs):
        started=clock()
        try:return function(*args,**kwargs)
        finally:
            cost=elapsed(started);row=timing[kind];row['calls']+=1
            for key in ('wall_seconds','cpu_seconds'):row[key]+=cost[key]
    baseline=tuple(inputs.stream(meta) for meta in base['segments'])
    history=[];values=[];artifacts=[];walks=[];instances=[];anchor=None;protected=None
    journal()

    def retain(slot,parts):
        history.append((slot,tuple(parts)));catalogue,events=retained_attempts(history)
        event=events[-1];identifier=event['candidate_id']
        if event['new_tuple']:
            point_folder=folder/'whole'/('candidate-%02d'%identifier)
            meta=dict(id=identifier,first_slot=slot,segments=[persist_stream(point_folder/('reset-%02d.l4hy'%i),blob,i,base)
                for i,blob in enumerate(parts)])
            artifacts.append(meta)
            record['points'].append(dict(id=identifier,status='serialized-unverified',first_slot=slot,tuple=meta))
            save(point_folder/'tuple-private.json',dict(status='serialized-unverified',**meta))
            journal()
        return event

    def complete(event,parts,source_pcm=None):
        identifier=event['candidate_id'];point_folder=folder/'whole'/('candidate-%02d'%identifier)
        if source_pcm is not None:
            for index,(blob,pcm) in enumerate(zip(parts,source_pcm)):
                validate_frozen_fields(C,baseline[index],blob,base['reset_plans'][index]['eligible_group_indices'])
                native_model=evaluator.decode(blob,base['segments'][index]['samples'],4)
                if not C.np.array_equal(pcm,native_model):raise AssertionError('State-owner full synthesis differs from native/model PCM/PWM')
        if not event['new_tuple']:return values[identifier]
        value=evaluator.measure(tuple(parts),base,target,True,
            dict(record_id=job['id'],phase=phase,arm=job['arm'],candidate_id=identifier,first_slot=event['slot']))
        flags=C.chain._admission(value,value if anchor is None else anchor)
        row=dict(id=identifier,labels=['baseline' if event['slot']==0 else 'coverage-slot-'+str(event['slot'])],
            stream_bytes=sum(map(len,parts)),full_flash_bytes=None,**value,**flags,automatic_quality_eligible=all(flags.values()))
        values.append(row)
        record['points'][identifier].update(status='complete',value=row)
        save(point_folder/'admission-private.json',dict(status='complete',whole_row=row,whole_chain=artifacts[identifier]))
        journal()
        return row

    try:
        baseline_event=call('durable_tuple_io',retain,0,baseline)
        anchor=call('whole_verification_metrics_io',complete,baseline_event,baseline)
        if phase=='real':
            for key in VALUE_KEYS:equal(anchor[key],base['stored_expected_whole_value'][key])
        protected=anchor
        for index,meta in enumerate(base['segments']):
            state=dict(record_id=job['id'],arm=job['arm'],phase=phase,reset=index,status='started')
            attempt['real_instances' if phase=='real' else 'synthetic_instances'].append(state);instances.append(state);journal()
            at,n=meta['start'],meta['samples'];plan=base['reset_plans'][index]
            walk=call('construct',C.extras.ExistingExtraPass,target[at:at+n],baseline[index],max_bytes=job['local_byte_cap'],
                causal_positions=True,horizon=160,max_trial_evaluations=plan['trial_limit'],cpu_seconds=None)
            walks.append(walk)
            if (walk.n!=n or walk.profile!=4 or tuple(walk.eligible)!=tuple(plan['eligible_group_indices']) or
                    walk.initial_active!=plan['initial_active'] or walk.trial_limit!=plan['trial_limit'] or
                    walk.atomic_bound!=49 or walk.covered or walk.trials or walk.visited or
                    walk.horizon!=160 or walk.causal_positions is not True or walk.budget.limit_seconds is not None):
                raise AssertionError('The constructed fixed initial eligibility/settings differ')
            state.update(status='active',progress=progress(walk));journal()
        for slot in range(1,5):
            protected_parts=tuple(inputs.stream(m) for m in artifacts[protected['id']]['segments'])
            checkpoints=[call('snapshot',walk.snapshot) for walk in walks]
            before=[progress(walk) for walk in walks]
            for index,walk in enumerate(walks):
                plan=base['reset_plans'][index];goal=coverage_targets(plan['initial_eligible'])[slot-1]
                while walk.covered<goal:
                    if call('step',walk.step) is not True:raise AssertionError('Full trial allowance did not complete a common coverage goal')
                if (walk.covered!=goal or tuple(walk.visited)!=tuple(walk.eligible[:goal]) or
                        walk.trials>plan['trial_limit']):raise AssertionError('A group was revisited or common coverage changed')
            parts=tuple(call('serialize',walk.serialize) for walk in walks)
            event=call('durable_tuple_io',retain,slot,parts)
            control_exact=None
            if old_control is not None:
                matches=[row for row in old_control['slots'] if row['slot']==slot]
                if len(matches)!=1 or parts!=tuple(inputs.stream(m) for m in matches[0]['segments']):
                    raise AssertionError('Fresh uninterrupted common-slot tuple differs from saved causal control')
                control_exact=True
            pcm=[call('synthesize',walk.synthesize) for walk in walks]
            value=call('whole_verification_metrics_io',complete,event,parts,pcm)
            flags=C.chain._admission(value,anchor);decision=accept_block(value,flags,protected)
            stage=dict(slot=slot,candidate_id=event['candidate_id'],new_tuple=event['new_tuple'],
                control_slot_bytes_exact=control_exact,original_anchor_gates=flags,protected_before_id=protected['id'],
                **decision,progress_before=before,progress_proposed=[progress(w) for w in walks],status='measured')
            record['stage_events'].append(stage);journal()
            if job['arm']=='rollback' and not decision['accepted']:
                for index,(walk,checkpoint) in enumerate(zip(walks,checkpoints)):
                    consumed=progress(walk);call('rollback',walk.rollback,checkpoint);restored=progress(walk)
                    for name in ('covered','trials','cursor','visited','cumulative_changed'):
                        if restored[name]!=consumed[name]:raise AssertionError('Rollback refunded paid progress/work')
                    if restored['active']!=before[index]['active'] or restored['committed_changed_groups']!=before[index]['committed_changed_groups']:
                        raise AssertionError('Rollback did not restore protected active/meaningful pulse fields')
                    blob=call('serialize',walk.serialize)
                    if blob!=protected_parts[index]:raise AssertionError('Rollback did not restore exact protected complete bytes')
                    pcm=call('synthesize',walk.synthesize)
                    if not C.np.array_equal(pcm,evaluator.decode(blob,walk.n,4)):
                        raise AssertionError('Rolled-back complete output differs from verified protected stream')
                stage['action']='rollback'
            else:
                stage['action']='continue'
                if decision['accepted']:protected=value
            stage.update(status='complete',protected_after_id=protected['id'],progress_after=[progress(w) for w in walks])
            for state,walk in zip(instances,walks):state.update(progress=progress(walk),work_counts=walk.work_counts())
            journal()
        decisions=[]
        for percent in (100,95,90):decisions.append(dict(percent=percent,**C.chain.choose_budget(values,job['whole_caps'][str(percent)])))
        for walk,state in zip(walks,instances):
            if walk.covered!=len(walk.eligible) or tuple(walk.visited)!=tuple(walk.eligible):raise AssertionError('The pass did not finish initial eligibility')
            walk.budget.finish_search()
            state.update(status='complete',progress=progress(walk),work_counts=walk.work_counts(),
                nonadditive_lifetime_budget=walk.budget.report())
        result=dict(**job,phase=phase,status='complete',baseline_samples=base['samples'],baseline_bytes=base['stream_bytes'],
            whole_rows=values,whole_chains=artifacts,stage_events=record['stage_events'],decisions=decisions,
            instances=instances,protected_final_id=protected['id'],api_call_costs=dict(timing),record_workflow_cost=elapsed(begin))
        save(folder/'result-private.json',result);record['status']='complete';journal()
        return result
    except Exception as exc:
        for state,walk in zip(instances,walks):
            state.update(status='interrupted',progress=progress(walk),work_counts=walk.work_counts())
        record.update(status='failed',exception_type=type(exc).__name__,record_workflow_cost=elapsed(begin));journal()
        raise
