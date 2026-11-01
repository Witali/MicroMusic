"""Reuse immutable V1 audit operators with explicit current source origins."""
from __future__ import annotations

from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
V1=HERE.parent/'v5-joint-rate-2026-11-01'
sys.path.insert(0,str(V1))
from baselines import Inputs,sha
from pilot_policy import local_frontier,whole_views,distinct_whole,frontier_summary
from pilot_runtime import (VALUE_KEYS,WholeEvaluator,bind_production,production_snapshot,load_production,
    check_origins,equal,save,no_initial_fits,bridge_native,target_for,load_manifest as load_original_manifest)


def source_snapshot():
    paths=[p for p in HERE.iterdir() if p.suffix in ('.py','.md')]
    paths += [V1/name for name in ('baselines.py','pilot_policy.py','pilot_runtime.py')]
    shared=HERE.parent/'v5-matched-search-cpu-2026-10-30'
    paths += [shared/name for name in ('study_policy.py','study_runtime.py')]
    return {p.relative_to(HERE.parent).as_posix():sha(p.read_bytes()) for p in paths}


def load_manifest(path,inputs):
    raw=inputs.read(path);manifest=__import__('json').loads(raw)
    marker=inputs.json(path.parent/'complete-private.json')
    if (manifest['schema']!='lpx-anchor-order-baselines-private-v1' or manifest['status']!='prepared-no-search' or
            marker['status']!='complete' or marker['binding_sha256']!=sha(raw)):
        raise ValueError('The no-search anchor preparation is not closed')
    for name,digest in manifest['input_files_sha256'].items():inputs.read(name,digest)
    for name,digest in manifest['preparation_sources'].items():inputs.read(HERE.parent/name,digest)
    return manifest
