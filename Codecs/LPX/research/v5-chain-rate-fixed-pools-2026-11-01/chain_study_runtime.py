"""Source/receipt closure, forbidden-work guards and private study utilities."""
from __future__ import annotations

from contextlib import ExitStack,contextmanager
import hashlib
import importlib
import importlib.util
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

from chain_study_policy import HERE,PRODUCER,V1_PRODUCER

ROOT=HERE.parents[3]
PREFIX='Codecs/LPX/01_ACTIVE_Q0_CODEC/'
PILOT=HERE.parent/'v5-joint-rate-2026-11-01'
SHARED=HERE.parent/'v5-matched-search-cpu-2026-10-30'
sys.path.insert(0,str(PILOT))
spec=importlib.util.spec_from_file_location('chain_study_pilot_support',PILOT/'pilot_runtime.py')
SUPPORT=importlib.util.module_from_spec(spec);sys.modules[spec.name]=SUPPORT;spec.loader.exec_module(SUPPORT)
Inputs,VALUE_KEYS=SUPPORT.Inputs,SUPPORT.VALUE_KEYS


def sha(raw):return hashlib.sha256(raw).hexdigest()
def timed():return time.perf_counter(),time.process_time()
def elapsed(start):return dict(wall_seconds=time.perf_counter()-start[0],cpu_seconds=time.process_time()-start[1])


def runtime_identity():
    return dict(python=sys.version,packages={name:importlib.metadata.version(name)
        for name in ('numpy','numba','scipy','pystoi','soundfile')},
        threads={name:os.environ.get(name) for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','NUMBA_NUM_THREADS')})


def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_symlink() or path.exists() and path.stat().st_nlink>1:
        raise ValueError('An output aliases another file')
    temporary=path.with_name(path.name+'.writing')
    if temporary.exists():raise ValueError('Preserve the previous incomplete write')
    temporary.write_bytes((json.dumps(value,indent=2,allow_nan=False)+'\n').encode())
    for attempt in range(6):
        try:temporary.replace(path);return
        except OSError as exc:
            if getattr(exc,'winerror',None) not in (5,32) or attempt==5:raise
            time.sleep(.01*2**attempt)


def sources():
    files=[p for p in HERE.iterdir() if p.suffix in ('.py','.md')]
    files += [PILOT/name for name in ('pilot_runtime.py','pilot_policy.py','baselines.py')]
    files += [SHARED/name for name in ('study_runtime.py','study_policy.py')]
    return {p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in files}


def fresh_output(path):
    path=Path(path).resolve()
    if path.exists() or not path.is_relative_to((ROOT/'build').resolve()):
        raise ValueError('Use a fresh ignored build output in this worktree')
    path.mkdir(parents=True)
    return path


def verify_v1_bridge(bindings,root,inventory,inputs):
    if len(bindings)!=2 or {b['profile'] for b in bindings}!={4,6}:
        raise ValueError('Both original V1 workers are required')
    first=bindings[0]
    for binding in bindings:
        if (binding['source_commit']!=V1_PRODUCER or binding['production_sources']!=first['production_sources']
                or binding['source_context']!=first['source_context'] or binding['research_sources']!=first['research_sources']):
            raise ValueError('The immutable V1 producer closure changed')
        for name,digest in binding['production_sources'].items():
            inputs.read(Path(binding['source_root'])/name,digest)
        if binding['runtime']!=runtime_identity():
            raise ValueError('The V1 model/metric runtime differs from the new declared runtime')
    allowed={PREFIX+'tools/refine_speech_trajectory.py'}
    changed=[]
    for name,digest in first['production_sources'].items():
        if name not in inventory:raise ValueError('A prior production source disappeared')
        if inventory[name]!=digest:
            if name not in allowed:raise ValueError('A DSP/model/metric/native source changed since V1')
            changed.append(name)
    return dict(old_producer=V1_PRODUCER,new_producer=PRODUCER,
        unchanged_old_production_files=len(first['production_sources'])-len(changed),
        changed_host_search_files=changed,
        added_production_files=sorted(set(inventory)-set(first['production_sources'])),
        unchanged_dsp_model_metrics_and_native_sources=True)


def open_manifest(path):
    inputs=Inputs();raw=inputs.read(path);manifest=json.loads(raw)
    marker=inputs.json(Path(path).parent/'complete-private.json')
    if (manifest['status']!='prepared-no-dp' or marker['status']!='complete'
            or marker['manifest_sha256']!=sha(raw) or manifest['producer_commit']!=PRODUCER):
        raise ValueError('The exact preparation is not terminal and bound')
    for name,digest in manifest['input_files_sha256'].items():inputs.read(name,digest)
    if manifest['study_sources']!=sources():raise ValueError('The frozen study recipe changed')
    if manifest['runtime']!=runtime_identity():raise ValueError('The frozen package/thread runtime changed')
    root=Path(manifest['producer_root'])
    inventory=SUPPORT.bind_production(root,PRODUCER)
    if inventory!=manifest['production_sources']:raise ValueError('The new producer epoch changed')
    natives,bridge=SUPPORT.bridge_native(root,Path(manifest['native_cases']),inputs)
    if bridge!=manifest['native_bridge']:raise ValueError('The old/native new/model bridge changed')
    return inputs,manifest,natives


def check_allocator_origin(C,root,inventory):
    name=PREFIX+'tools/speech_chain_rate.py';expected=(Path(root)/name).resolve()
    if (Path(C.chain_rate.__file__).resolve()!=expected or name not in inventory
            or sha(expected.read_bytes())!=inventory[name]):
        raise ValueError('Exact allocator origin or bound source bytes differ')


def load_current(root,inventory):
    C=SUPPORT.load_production(Path(root))
    C.chain_rate=importlib.import_module('speech_chain_rate')
    SUPPORT.check_origins(Path(root))
    check_allocator_origin(C,root,inventory)
    return C


@contextmanager
def forbid_search_and_build(C,attempt,out):
    """Permit decoding/measurement only, never encoding or coefficient search."""
    names={
        'speech_v4':('encode','search','pack'),
        'speech_compact':('pack','repack'),
        'encode_speech_voice':('encode',),
        'adaptive_speech_voice':('encode','refine_candidates'),
        'adaptive_speech_chain':('encode','refine_candidates','select_candidates'),
        'refine_speech_lpc':('refine','adapt_excitation','coefficient_patch'),
        'refine_speech_trajectory':('refine','_expand','_rate_children','adapt_excitation','coefficient_patch'),
        'speech_chain_frontier':('assemble',),
        'batch_decoder':('build_library',),
    }
    def forbidden(*args,**kwargs):
        attempt['forbidden_work_attempts']+=1
        save(out/'forbidden-work-private.json',dict(status='rejected',count=attempt['forbidden_work_attempts']))
        raise AssertionError('Encoding/refinement/packing/build/target work is forbidden')
    with ExitStack() as stack:
        for name,attributes in names.items():
            module=importlib.import_module(name)
            for attribute in attributes:
                if hasattr(module,attribute):stack.enter_context(patch.object(module,attribute,forbidden))
        for attribute in ('run','Popen','check_output','check_call'):
            stack.enter_context(patch.object(subprocess,attribute,forbidden))
        yield


def final_guard(manifest,inputs,C):
    root=Path(manifest['producer_root'])
    if manifest['study_sources']!=sources() or manifest['production_sources']!=SUPPORT.production_snapshot(root):
        raise ValueError('A frozen study/production source changed')
    check_allocator_origin(C,root,manifest['production_sources'])
    SUPPORT.check_origins(root);inputs.verify()


def check_integer_sse(C,evaluator,parts,base,target,expected):
    start=0;total=0
    for blob,meta in zip(parts,base['segments']):
        pcm=evaluator.decode(blob,meta['samples'],base['profile'])
        delta=target[start:start+len(pcm)].astype(C.np.int64)-pcm.astype(C.np.int64)
        total+=int(C.np.sum(delta*delta));start+=len(pcm)
    if start!=len(target) or total!=expected:
        raise AssertionError('Fresh complete integer SSE differs from the saved additive sum')
    return total
