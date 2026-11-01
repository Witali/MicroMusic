"""Fixed finite endpoint, whole-chain and accounting rules; no codec imports."""
from __future__ import annotations

import math

ARMS = ('single-path','trajectory')
SINGLE = dict(frame_limit=64,spectral_candidates=4,lookahead=1280,excitation_horizon=160,passes=2,refit=True)
TRAJECTORY = dict(frame_limit=64,window_frames=2,beam_width=3,spectral_candidates=4,
    excitation_candidates=2,excitation_horizon=160,max_evaluations=4096,objective=None,
    objective_name='sse',selection='conservative',capacity_policy='amplitude',allocation_evaluations=0,
    rate_lambda=0.,screening='local',screening_horizon=1280)


def local_frontier(rows,cap,limit=16):
    """Actual bytes/SSE dominance, then deterministic bounded ordinal coverage."""
    if type(cap) is not int or cap<22 or type(limit) is not int or limit<2:
        raise ValueError('Invalid frontier bound')
    seen,unique = set(),[]
    for row in rows:
        if row['blob'] in seen:
            continue
        if (type(row['sse']) is not int or row['sse']<0 or type(row['id']) is not int
                or not isinstance(row['blob'],bytes) or len(row['blob'])<22):
            raise ValueError('Invalid actual endpoint')
        seen.add(row['blob'])
        if len(row['blob'])<=cap:
            unique.append(row)
    frontier,best = [],None
    for row in sorted(unique,key=lambda r:(len(r['blob']),r['sse'],r['id'])):
        if best is None or row['sse']<best:
            frontier.append(row)
            best = row['sse']
    if len(frontier)>limit:
        indices = [i*(len(frontier)-1)//(limit-1) for i in range(limit)]
        frontier = [frontier[i] for i in indices]
    return frontier


def whole_views(baseline,locals):
    """Exactly five role recipes, with sparse searched-reset replacement only."""
    baseline = tuple(baseline)
    indices = [row['index'] for row in locals]
    if indices!=sorted(set(indices)) or any(type(i) is not int or not 0<=i<len(baseline) for i in indices):
        raise ValueError('Invalid sparse reset list')
    result = [('baseline',baseline)]
    for name in ('selected','raw','minimum-byte','minimum-sse'):
        parts = list(baseline)
        for row in locals:
            if name in ('selected','raw'):
                blob = row[name]
            else:
                points = row['frontier']
                point = (min(points,key=lambda r:(len(r['blob']),r['sse'],r['id'])) if name=='minimum-byte'
                    else min(points,key=lambda r:(r['sse'],len(r['blob']),r['id']))) if points else None
                blob = None if point is None else point['blob']
            if blob is None:
                parts = None
                break
            parts[row['index']] = blob
        result.append((name,None if parts is None else tuple(parts)))
    return result


def distinct_whole(views,prior=()):
    positions,result = {},[]
    entries = list(views)+[('prior2-'+str(i),tuple(blobs)) for i,blobs in enumerate(prior)]
    for label,blobs in entries:
        if blobs is None:
            continue
        key = tuple(bytes(blob) for blob in blobs)
        if not key:
            raise ValueError('A whole tuple cannot be empty')
        if key in positions:
            result[positions[key]]['labels'].append(label)
        else:
            positions[key] = len(result)
            result.append(dict(id=len(result),labels=[label],blobs=key,stream_bytes=sum(map(len,key))))
    return result


def pair_cpu(a,b,*,prior_a=0.,prior_b=0.):
    values = (a,b,prior_a,prior_b)
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 for v in values):
        raise ValueError('CPU costs must be finite nonnegative measurements')
    left,right = a+prior_a,b+prior_b
    ratio = None if min(left,right)<=0 else max(left,right)/min(left,right)
    return dict(single_path_total_helper_cpu=left,trajectory_total_helper_cpu=right,
        total_cpu_ratio=ratio,matched_total_cpu=ratio is not None and ratio<=1.25,
        limit=1.25,includes_prior2=bool(prior_a or prior_b))


def metric_key(target_digest,speech,source_context,blobs):
    if type(speech) is not bool or not target_digest or not source_context:
        raise ValueError('A metric context must be explicit')
    return target_digest,speech,source_context,tuple(bytes(blob) for blob in blobs)
