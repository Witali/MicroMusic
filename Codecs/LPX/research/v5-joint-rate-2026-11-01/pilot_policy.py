"""Fixed five-arm mappings and bounded endpoint decisions; no codec imports."""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
SHARED = HERE.parent/'v5-matched-search-cpu-2026-10-30'
spec = importlib.util.spec_from_file_location('study_policy',SHARED/'study_policy.py')
shared = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = shared
spec.loader.exec_module(shared)
local_frontier,whole_views,distinct_whole = shared.local_frontier,shared.whole_views,shared.distinct_whole

ARMS = ('T-local-0','T-full-0','G-full-0','G-full-.1','G-full-1')


def settings(job,sse,whole_bytes,*,synthetic=False):
    if job['arm'] not in ARMS or whole_bytes<22 or sse<0 or not math.isfinite(sse):
        raise ValueError('Invalid fixed arm or whole-record price context')
    position = ARMS.index(job['arm'])
    alpha = (0.,0.,0.,.1,1.)[position]
    new = position>=2
    if (job['alpha'],job['new_generation'],job['screening'])!=(alpha,new,'local' if position==0 else 'full'):
        raise ValueError('The arm mapping changed')
    return dict(frame_limit=1 if synthetic else 64,window_frames=2,beam_width=1 if synthetic else 3,
        spectral_candidates=1 if synthetic else 4,excitation_candidates=1 if synthetic else 2,
        excitation_horizon=160,max_evaluations=32 if synthetic else 4096,objective=None,
        objective_name='sse',selection='conservative',capacity_policy='amplitude',
        allocation_evaluations=256 if new else 0,rate_lambda=alpha*sse/(8*whole_bytes),
        screening=job['screening'],screening_horizon=1280,rate_search=new)


def validate_scope(manifest):
    jobs = manifest['pilot_jobs']
    bases = {b['id']:b for b in manifest['baselines']}
    if len(bases)!=104 or len(manifest['pilot_baseline_ids'])!=12 or len(jobs)!=60:
        raise ValueError('The predeclared pilot context count changed')
    calls = 0
    for identifier in manifest['pilot_baseline_ids']:
        base = bases[identifier]
        group = [j for j in jobs if j['baseline_id']==identifier]
        if len(group)!=5 or set(j['arm'] for j in group)!=set(ARMS):
            raise ValueError('Every full context needs every fixed arm exactly once')
        for job in group:
            if (job['reset_indices']!=list(range(len(base['segments']))) or
                    job['local_byte_cap']!=min(base['stream_bytes'],65535) or
                    job['whole_caps']!={str(p):base['stream_bytes']*p//100 for p in (100,95,90)} or
                    job['cpu_seconds_per_reset']!=2.):
                raise ValueError('Full reset coverage, actual B caps or quota changed')
            settings(job,1,base['stream_bytes'])
            calls += len(job['reset_indices'])
    if calls!=100 or len(jobs)*3!=180:
        raise ValueError('The fixed helper or cap count changed')
    return bases


def frontier_summary(rows):
    """Only fully gated whole outputs count toward preserved-quality bytes."""
    eligible = [r for r in rows if r['automatic_quality_eligible']]
    ordered = sorted(eligible,key=lambda r:(r['stream_bytes'],r['score'],r['id']))
    frontier,best = [],None
    for row in ordered:
        if best is None or row['score']<best:
            frontier.append(row['id']);best=row['score']
    minimum = min(eligible,key=lambda r:(r['stream_bytes'],r['score'],r['id'])) if eligible else None
    return dict(minimum_preserved_quality_id=None if minimum is None else minimum['id'],
        minimum_preserved_quality_bytes=None if minimum is None else minimum['stream_bytes'],
        bounded_preserved_quality_frontier_ids=frontier)
