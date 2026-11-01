"""Fixed anchor pilot arms and pure finite-scope/report contracts."""
from __future__ import annotations

ARMS=('T-time-0','T-priority-0','G-time-0','G-priority-0')


def settings(job,*,synthetic=False):
    if job['arm'] not in ARMS:raise ValueError('Unknown frozen anchor-study arm')
    i=ARMS.index(job['arm']);new=i>=2;order='priority' if i%2 else 'time'
    if job['new_generation']!=new or job['anchor_order']!=order:
        raise ValueError('The fixed generation/order mapping differs')
    return dict(frame_limit=1 if synthetic else 64,window_frames=2,beam_width=1 if synthetic else 3,
        spectral_candidates=1 if synthetic else 4,excitation_candidates=1 if synthetic else 2,
        excitation_horizon=160,max_evaluations=32 if synthetic else 4096,objective=None,
        objective_name='sse',selection='conservative',capacity_policy='amplitude',
        allocation_evaluations=256 if new else 0,rate_lambda=0.,screening='full',screening_horizon=1280,
        rate_search=new,anchor_order=order)


def validate_scope(manifest):
    jobs=manifest['jobs'];bases={b['id']:b for b in manifest['baselines']}
    if (len(bases)!=104 or len(manifest['pilot_baseline_ids'])!=12 or len(jobs)!=48 or
            [j['id'] for j in jobs]!=list(range(48))):
        raise ValueError('The frozen anchor-study context count differs')
    calls=0
    for identifier in manifest['pilot_baseline_ids']:
        base=bases[identifier];group=[j for j in jobs if j['baseline_id']==identifier]
        if len(group)!=4 or set(j['arm'] for j in group)!=set(ARMS):
            raise ValueError('Every full context needs four fixed arms')
        for job in group:
            if (job['reset_indices']!=list(range(len(base['segments']))) or
                    any(job[k]!=base[k] for k in ('source_ordinal','nonspeech','profile','mode')) or
                    job['local_byte_cap']!=min(base['stream_bytes'],65535) or
                    job['whole_caps']!={str(p):base['stream_bytes']*p//100 for p in (100,95,90)} or
                    job['cpu_seconds_per_reset']!=2. or job['rate_lambda']!=0.):
                raise ValueError('Full-record geometry, actual B caps or quota differs')
            settings(job);calls+=len(job['reset_indices'])
    if calls!=80:raise ValueError('The fixed eighty-call scope differs')
    return bases


def validate_counters(report):
    nominated,planned=report['nominated_anchors'],report['planned_anchors']
    started,completed=report['started_anchors'],report['completed_anchors']
    if (nominated!=sorted(set(nominated)) or sorted(planned)!=nominated or
            any(type(i) is not int or i<0 for i in nominated) or
            started!=planned[:len(started)] or completed!=started[:len(completed)] or
            len(started)-len(completed) not in (0,1) or len(completed)!=report['completed_windows'] or
            len(planned)>report['frame_limit']):
        raise AssertionError('The frozen anchor set/order/progress contract differs')
    if report['anchor_order']=='time' and planned!=nominated:
        raise AssertionError('Temporal order is not ascending')
    if not len(started)-1<=len(report['checkpoints'])<=len(started):
        raise AssertionError('An anchor lacks its checkpoint or interrupted prefix rebuild')
    for start,end in (('refit_calls_started','refit_calls_completed'),
            ('repeat_spectrum_opportunities','repeat_spectrum_proposals'),
            ('rate_allocation_calls_started','completed_rate_allocation_calls')):
        a,b=report[start],report[end]
        if type(a) is not int or type(b) is not int or not 0<=a-b<=1 or b<0:
            raise AssertionError('A paid branch-call progress counter differs')
    if type(report['joint_candidates_completed']) is not int or report['joint_candidates_completed']<0:
        raise AssertionError('A joint candidate counter is invalid')
    if (type(report['refit_candidates_completed']) is not int or
            not 0<=report['refit_calls_completed']-report['refit_candidates_completed']<=1 or
            report['refit_candidates_completed']<0):
        raise AssertionError('A refit return was confused with a completed scored candidate')


def compare_nominated(left,right):
    if left['nominated_anchors']!=right['nominated_anchors']:
        raise AssertionError('Time/priority changed the nominated anchor set')


def priority_plan(nominated,errors,savings=None):
    """Independent fixed ordering recipe; duplicate skips retain the turn."""
    if nominated!=sorted(set(nominated)) or any(f not in errors for f in nominated):
        raise ValueError('A priority plan needs the exact nominated set and errors')
    error=sorted(nominated,key=lambda f:(-errors[f],f))
    if savings is None:return error
    rate=sorted((f for f in nominated if savings.get(f,0)>0),key=lambda f:(-savings[f],f))
    queues=[rate,error];positions=[0,0];result=[];used=set()
    while len(result)<len(nominated):
        for q,queue in enumerate(queues):
            while positions[q]<len(queue) and queue[positions[q]] in used:positions[q]+=1
            if positions[q]<len(queue):
                f=queue[positions[q]];positions[q]+=1;result.append(f);used.add(f)
    return result


def repeat_savings(spectra,profile,bit_cost):
    """Exact adjacent-spectrum feature; encoding and acceptance are unchanged."""
    result={}
    for f in range(1,len(spectra)):
        prior,current=spectra[f-1],spectra[f]
        before=bit_cost(current,prior,profile);after=bit_cost(prior,prior,profile)
        if f+1<len(spectra):
            following=spectra[f+1]
            before+=bit_cost(following,current,profile);after+=bit_cost(following,prior,profile)
        if before>after:result[f]=before-after
    return result
