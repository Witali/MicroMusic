"""Pinned shared whole auditor and explicit old-native/new-model source bridge."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from pilot_policy import HERE,SHARED
from baselines import Inputs,sha

spec = importlib.util.spec_from_file_location('joint_rate_shared_runtime',SHARED/'study_runtime.py')
shared = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = shared
spec.loader.exec_module(shared)
VALUE_KEYS,WholeEvaluator = shared.VALUE_KEYS,shared.WholeEvaluator
bind_production,production_snapshot = shared.bind_production,shared.production_snapshot
load_production,check_origins = shared.load_production,shared.check_origins
equal,save,no_initial_fits = shared.equal,shared.save,shared.no_initial_fits
PREFIX = shared.PREFIX


def source_snapshot():
    paths = [p for p in HERE.iterdir() if p.suffix in ('.py','.md')]
    paths += [SHARED/name for name in ('study_policy.py','study_runtime.py')]
    return {p.relative_to(HERE.parent).as_posix():sha(p.read_bytes()) for p in paths}


def bridge_native(root,cases_path,inputs):
    """Reuse exact callback-enabled ROM libraries, not a renamed current build."""
    raw = inputs.read(cases_path)
    cases = json.loads(raw)
    marker = inputs.json(cases_path.parent/'complete-private.json')
    if cases['status']!='prepared' or marker['status']!='complete' or marker['handoff_sha256']!=sha(raw):
        raise ValueError('The original native preparation is not closed')
    closure = {k:v for k,v in cases['reference_source_sha256'].items()
        if k.startswith(PREFIX+'src/') or k==PREFIX+'tests/input_callback_native.cpp'}
    if not closure or PREFIX+'src/native_batch_decoder.cpp' not in closure:
        raise ValueError('The old native source closure is incomplete')
    for name,digest in closure.items():
        inputs.read(Path(cases['source_root'])/name,digest)
        inputs.read(root/name,digest)
    # Require every current C/header/source file, including tables, to be in it.
    actual = {p.relative_to(root).as_posix() for p in (root/PREFIX/'src').rglob('*') if p.is_file()}
    if actual!={k for k in closure if k.startswith(PREFIX+'src/')}:
        raise ValueError('The current native include closure differs')
    native,receipts = {},{}
    for only,name in ((0,'common'),(1,'v5-only')):
        library = cases_path.parent/'native'/(name+'-callback.so')
        build = cases_path.parent/'native'/(name+'-build-private.json')
        digest = cases['input_files_sha256'].get(str(library.resolve()))
        if digest is None:raise ValueError('The native library is not pinned by its original receipt')
        inputs.read(library,digest)
        inputs.read(build)
        receipt = json.loads(build.read_bytes())
        command = receipt['command']
        required = ['-DLPX4_ENABLE_SPEECH=1','-DLPX4_ENABLE_SPEECH_COMPACT=1',
            '-DLPX4_COMPACT_ONLY=%d'%only,'-DLPX4_ROM_POINTER=1',
            '-DLPX4_ENABLE_INPUT_CALLBACK=1','-DLPX4_ENABLE_ASM=0']
        expected = [receipt['compiler']['path'],'-O3','-shared','-fPIC','-std=c++11',
            *required,'-I'+str(Path(cases['source_root'])/PREFIX/'src'),
            str(Path(cases['source_root'])/PREFIX/'src/Lpx4HybridCore.cpp'),
            str(Path(cases['source_root'])/PREFIX/'src/native_batch_decoder.cpp'),
            str(Path(cases['source_root'])/PREFIX/'tests/input_callback_native.cpp'),'-o',str(library)]
        if (receipt['returncode'] or command!=expected or receipt['compiler']!=cases['compiler']):
            raise ValueError('Native recipe differs')
        inputs.read(receipt['compiler']['path'],receipt['compiler']['file_sha256'])
        native[name] = library
        receipts[name] = receipt
    return native,dict(old_source_commit=cases['source_commit'],old_source_root=cases['source_root'],
        old_native_cases_sha256=sha(raw),unchanged_native_source_closure=closure,build_receipts=receipts,
        library_sha256={name:sha(path.read_bytes()) for name,path in native.items()},
        build_receipts_reopened_and_pinned_now=True,old_build_receipts_were_not_in_old_input_index=True,
        callback_enabled=True,rom_pointer=True,assembly=False,new_native_builds=0,
        new_model_epoch_bound_separately=True)


def load_manifest(path,inputs):
    raw = inputs.read(path)
    manifest = json.loads(raw)
    marker = inputs.json(path.parent/'complete-private.json')
    if (manifest['status']!='prepared-no-search' or marker['status']!='complete' or
            marker['binding_sha256']!=sha(raw)):
        raise ValueError('The no-search baseline preparation is not closed')
    for name,digest in manifest['input_files_sha256'].items():inputs.read(name,digest)
    for name,digest in manifest['preparation_sources_sha256'].items():inputs.read(HERE/name,digest)
    return manifest


def target_for(base,C,inputs):
    meta=base['prepared_target']
    target=C.np.frombuffer(inputs.read(meta['path'],meta['pcm16_sha256']),dtype='<i2').copy()
    if len(target)!=base['samples'] or meta['sample_rate']!=8000:
        raise ValueError('The exact full prepared target differs')
    return target
