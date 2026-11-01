"""Fixed V1 pool restrictions, one exact allocation, and bounded whole recipes."""
from __future__ import annotations

import importlib.util
from numbers import Integral
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('chain_study_v1_policy',
    HERE.parent/'v5-matched-search-cpu-2026-10-30/study_policy.py')
V1=importlib.util.module_from_spec(spec);sys.modules[spec.name]=V1;spec.loader.exec_module(V1)
ARMS=('T-local-0','T-full-0','G-full-0','G-full-.1','G-full-1')
PERCENTS=(100,95,90)
PRODUCER='654ada493202f565d24cb9dcf22f16137c825329'
V1_PRODUCER='b21cb028bdb2ae3c285fbc2d9ccac96ca3c447d0'
DP_LIMITS=dict(max_states=250000,max_transitions=10000000)


def integer(value):
    if isinstance(value,bool) or not isinstance(value,Integral) or value<0:
        raise ValueError('Expected nonnegative integer saved cost/ID')
    return int(value)


def restrict_pool(pool,frontier_ids,baseline,selected_id,raw_id,cap):
    """Use exactly the saved bounded frontier plus required protected options."""
    if [row['id'] for row in pool]!=list(range(len(pool))):
        raise ValueError('The saved stable pool IDs changed')
    for row in pool:
        if not isinstance(row['blob'],bytes) or len(row['blob'])<22:
            raise ValueError('Expected actual serialized saved bytes')
        if row['sse'] is not None:integer(row['sse'])
    frontier=V1.local_frontier([row for row in pool if row['sse'] is not None],cap)
    if [row['id'] for row in frontier]!=frontier_ids or len(frontier)>16:
        raise ValueError('The exact retained V1 frontier changed')
    baseline_ids=[row['id'] for row in pool if row['blob']==baseline]
    if not baseline_ids:raise ValueError('The original baseline is absent')
    baseline_id=min(baseline_ids)
    wanted=set(frontier_ids+[baseline_id])
    for value in (selected_id,raw_id):
        if value is not None:
            value=integer(value)
            if value>=len(pool):raise ValueError('A protected local ID is missing')
            wanted.add(value)
    by_blob={};aliases={}
    for identifier in sorted(wanted):
        row=pool[identifier];integer(row['sse'])
        if len(row['blob'])>cap:raise ValueError('A required option is outside its saved local cap')
        if row['blob'] in by_blob:
            old=by_blob[row['blob']]
            if old['sse']!=row['sse']:raise ValueError('Identical bytes have inconsistent saved SSE')
            aliases[identifier]=old['id']
        else:
            by_blob[row['blob']]=dict(id=identifier,stream=row['blob'],sse=integer(row['sse']))
            aliases[identifier]=identifier
    return dict(rows=list(by_blob.values()),baseline_id=aliases[baseline_id],
        selected_id=None if selected_id is None else aliases[selected_id],
        raw_id=None if raw_id is None else aliases[raw_id],
        frontier=frontier,selected=None if selected_id is None else pool[selected_id]['blob'],
        raw=None if raw_id is None else pool[raw_id]['blob'])


def validate_jobs(jobs):
    if len(jobs)!=60 or sorted(j['id'] for j in jobs)!=list(range(60)):
        raise ValueError('The fixed 60 V1 arm records changed')
    contexts={}
    for job in jobs:
        contexts.setdefault(job['baseline_id'],[]).append(job)
        if job['arm'] not in ARMS or job['profile'] not in (4,6):raise ValueError('Unexpected V1 arm/profile')
        if job['caps']!={str(p):job['baseline_bytes']*p//100 for p in PERCENTS}:
            raise ValueError('The fixed whole caps changed')
        if [p['index'] for p in job['pools']]!=list(range(len(job['baseline']))):
            raise ValueError('Every original reset must retain its own supplied pool')
        if (not job['originals'] or len(job['originals'])>5 or 'baseline' not in job['originals'][0]['labels']
                or any('baseline' in r['labels'] for r in job['originals'][1:])):
            raise ValueError('The original five recipes/baseline changed')
    if len(contexts)!=12 or any(len(rows)!=5 or {r['arm'] for r in rows}!=set(ARMS) for rows in contexts.values()):
        raise ValueError('The 12 contexts must retain all five original arms')
    if sum(len(j['pools']) for j in jobs)!=100:
        raise ValueError('The original 100 searched reset pools changed')
    if {p:sum(j['profile']==p for j in jobs) for p in (4,6)}!={4:30,6:30}:
        raise ValueError('Both original balanced profiles are required')


def allocate_views(pools,baseline_ids,protected_ids,baseline_bytes,allocator,capture=None):
    """One call at B; retain completed per-cap winners even on a resource limit."""
    caps={str(p):baseline_bytes*p//100 for p in PERCENTS};retained={};published=0
    costs=[{row['id']:(len(row['stream']),row['sse']) for row in pool} for pool in pools]
    if capture is not None:capture.update(callback_completed=0,best={})
    def remember(point):
        nonlocal published
        if len(point.ids)!=len(pools):raise AssertionError('A partial prefix escaped the allocator')
        if (any(k not in rows for rows,k in zip(costs,point.ids))
                or sum(rows[k][0] for rows,k in zip(costs,point.ids))!=point.file_bytes
                or sum(rows[k][1] for rows,k in zip(costs,point.ids))!=point.sse):
            raise AssertionError('A completed callback differs from actual saved costs/IDs')
        published+=1
        if capture is not None:capture['callback_completed']=published
        for percent in PERCENTS:
            if point.file_bytes<=caps[str(percent)]:
                old=retained.get(percent)
                if old is None or (point.sse,point.file_bytes,point.ids)<(old.sse,old.file_bytes,old.ids):
                    retained[percent]=point
                    if capture is not None:capture['best'][str(percent)]=dict(ids=list(point.ids),file_bytes=point.file_bytes,sse=point.sse)
    result=allocator(pools,baseline_bytes,baseline_ids=baseline_ids,protected_chains=protected_ids,
                     on_candidate=remember,**DP_LIMITS)
    if result.exact!=(result.status in ('complete','no_pool_combination_fits')):
        raise AssertionError('Allocator exactness contradicts its status')
    winners={}
    for percent in PERCENTS:
        if result.exact:
            fits=[point for point in result.frontier if point.file_bytes<=caps[str(percent)]]
            winners[percent]=min(fits,key=lambda p:(p.sse,p.file_bytes,p.ids)) if fits else None
        else:winners[percent]=retained.get(percent)
        if len(pools)==1 and result.exact:
            fitting=[row for row in pools[0] if len(row['stream'])<=caps[str(percent)]]
            expected=min(fitting,key=lambda r:(r['sse'],len(r['stream']),r['id'])) if fitting else None
            actual=winners[percent]
            if (None if actual is None else actual.ids)!=(None if expected is None else (expected['id'],)):
                raise AssertionError('Single-reset exact allocation differs from direct cap selection')
    unique={}
    for percent,point in winners.items():
        if point is None:continue
        entry=unique.setdefault(point.ids,dict(ids=point.ids,point=point,labels=[]))
        entry['labels'].append('dp-%s-%d'%('exact' if result.exact else 'retained-nonexact',percent))
    if len(unique)>3:raise AssertionError('The fixed DP endpoint cap expanded')
    return dict(result=result,points=list(unique.values()),winners=winners,
                callback_best=retained,callback_completed=published,caps=caps)


def new_outcome(old,new,absent,exact):
    if new is None:return dict(kind='no-new-admission',exact_primary_success=False)
    if old is None:kind='new-admission'
    elif new['score']<old['score']-1e-12:kind='lower-joint-score'
    elif new['stream_bytes']<old['stream_bytes'] and new['score']<=old['score']+1e-12:kind='smaller-no-worse-joint'
    else:kind='no-strict-win'
    success=absent and kind not in ('no-new-admission','no-strict-win')
    return dict(kind=kind,absent_from_original_five=absent,new_admitted_win=success,
                exact_primary_success=success and exact,nonexact_retained_success=success and not exact)


def extends_context_frontier(originals,new,absent):
    """Saved-only size/joint Pareto test, independent of the arm's control."""
    if new is None or not absent or not new['automatic_quality_eligible']:return False
    return not any(old['automatic_quality_eligible'] and old['stream_bytes']<=new['stream_bytes']
                   and old['score']<=new['score']+1e-12 for old in originals)
