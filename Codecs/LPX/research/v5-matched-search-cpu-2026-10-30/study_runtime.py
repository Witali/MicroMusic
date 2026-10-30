"""Explicit production origins, immutable files, and new-study whole metrics."""
from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
PREFIX = 'Codecs/LPX/01_ACTIVE_Q0_CODEC/'
VALUE_KEYS = ('metrics','voice','pwm_voice','noise','pwm_noise','domain_scores','score',
    'clipped_samples','voice_components','pwm_voice_components')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path,value):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_symlink() or path.exists() and path.stat().st_nlink>1:
        raise ValueError('Output aliases are forbidden')
    tmp = path.with_name(path.name+'.tmp')
    tmp.write_bytes((json.dumps(value,indent=2,allow_nan=False)+'\n').encode())
    for index in range(6):
        try:
            os.replace(tmp,path)
            return
        except PermissionError:
            if index==5:
                raise
            time.sleep(.01*(index+1))


def source_snapshot():
    return {p.name:sha(p.read_bytes()) for p in HERE.iterdir() if p.suffix in ('.py','.md')}


def production_snapshot(root):
    active = root/PREFIX
    paths = [*(active/'tools').glob('*.py'),*(active/'tests').glob('test_*.py'),
        *(p for p in (active/'src').rglob('*') if p.is_file())]
    return {p.relative_to(root).as_posix():sha(p.read_bytes()) for p in paths}


def bind_production(root,commit):
    raw = subprocess.check_output(['git','-C',str(root),'archive','--format=tar',commit,
        '--',PREFIX+'tools',PREFIX+'tests',PREFIX+'src'])
    expected = {}
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for member in archive:
            name = member.name
            if member.isfile() and (name.startswith(PREFIX+'src/') or
                    name.startswith(PREFIX+'tools/') and name.endswith('.py') and '/' not in name[len(PREFIX+'tools/'):] or
                    name.startswith(PREFIX+'tests/test_') and name.endswith('.py') and '/' not in name[len(PREFIX+'tests/'):]):
                expected[name] = sha(archive.extractfile(member).read())
    actual = production_snapshot(root)
    if actual!=expected:
        raise ValueError('Production source differs from the explicit committed epoch')
    return actual


def load_production(root):
    sys.path.insert(0,str(root/PREFIX/'tools'))
    import numpy as np
    import soundfile as sf
    import speech_compact as compact
    import adaptive_speech_chain as chain
    import refine_speech_lpc as single
    import refine_speech_trajectory as trajectory
    from batch_decoder import BatchSession
    from voice_input import plan_level,quantize_target
    from voice_character import track_pitch
    from speech_noise_objective import NoiseObjective
    from standard_metrics import pwm_duties
    check_origins(root)
    return SimpleNamespace(**locals())


def check_origins(root):
    tools = (root/PREFIX/'tools').resolve()
    result = {}
    for name,module in list(sys.modules.items()):
        path = getattr(module,'__file__',None)
        if path and '/'+PREFIX+'tools/' in Path(path).as_posix():
            if Path(path).resolve().parent!=tools:
                raise ValueError('A production module was loaded from another worktree')
            result[name] = Path(path).resolve().relative_to(root).as_posix()
    return result


def no_initial_fits(attempt,out):
    stack = ExitStack()
    def forbidden(*args,**kwargs):
        attempt['forbidden_fit_or_build_attempts'] += 1
        save(out/'attempt-private.json',attempt)
        raise AssertionError('Initial fitting and native builds are forbidden in this study')
    names = {'speech_v4':('encode','search'),'encode_speech_voice':('encode',),
        'adaptive_speech_voice':('encode',),'adaptive_speech_chain':('encode',),
        'batch_decoder':('build_library',)}
    for name,attributes in names.items():
        module = sys.modules.get(name)
        if module is not None:
            for attribute in attributes:
                if hasattr(module,attribute):
                    stack.enter_context(patch.object(module,attribute,forbidden))
    return stack


def equal(actual,expected):
    if isinstance(expected,dict):
        if not isinstance(actual,dict) or actual.keys()!=expected.keys():
            raise AssertionError('Metric dictionary shape differs')
        for name in expected:
            equal(actual[name],expected[name])
    elif isinstance(expected,list):
        if not isinstance(actual,list) or len(actual)!=len(expected):
            raise AssertionError('Metric list shape differs')
        for a,b in zip(actual,expected):
            equal(a,b)
    elif isinstance(expected,(int,float)) and not isinstance(expected,bool):
        if not isinstance(actual,(int,float)) or not __import__('math').isfinite(actual) or abs(actual-expected)>1e-12:
            raise AssertionError('Fresh metric differs from saved baseline')
    elif actual!=expected or type(actual)!=type(expected):
        raise AssertionError('Fresh baseline value differs')


class WholeEvaluator:
    def __init__(self,C,common,only,context):
        self.C,self.common,self.only,self.context = C,common,only,context
        self.decoded,self.features,self.measures = {},{},{}
        self.counts = Counter()
        self.provenance = []

    def decode(self,blob,n,profile):
        c = self.C
        if c.compact.unpack(blob)[:2]!=(n,profile):
            raise AssertionError('Serialized reset geometry differs')
        if blob not in self.decoded:
            pcm = c.compact.decode_model(blob)
            if len(pcm)!=n:
                raise AssertionError('Model reset length differs')
            for receiver in (self.common,self.only):
                actual = receiver.decode_one_s16(blob,n)
                duty = receiver.decode_one(blob,n)
                if actual is None or duty is None or not c.np.array_equal(actual,pcm) or not c.np.array_equal(duty,c.pwm_duties(pcm)):
                    raise AssertionError('Whole endpoint common/v5/model PCM/PWM mismatch')
                self.counts['native_domain_comparisons'] += 2
            self.decoded[blob] = pcm
            self.counts['unique_verified_reset_streams'] += 1
            self.counts['verified_model_samples'] += n
        else:
            self.counts['verified_reset_cache_hits'] += 1
        return self.decoded[blob]

    def measure(self,blobs,baseline,target,speech,event):
        from study_policy import metric_key
        began = time.perf_counter(),time.process_time()
        c = self.C
        digest = sha(target.astype('<i2').tobytes())
        key = metric_key(digest,speech,self.context,blobs)
        if key in self.measures:
            self.counts['whole_metric_cache_hits'] += 1
            value,origin = self.measures[key]
            self.provenance.append(dict(event=event,reused_from=origin,key_sha256=sha(repr(key).encode()),
                evaluation_body_cost=dict(wall_seconds=time.perf_counter()-began[0],cpu_seconds=time.process_time()-began[1])))
            return value
        parts = [self.decode(blob,meta['samples'],baseline['profile']) for blob,meta in zip(blobs,baseline['segments'])]
        pcm = c.np.concatenate(parts)
        if len(blobs)!=len(baseline['segments']) or len(pcm)!=len(target) or len(pcm)!=baseline['samples']:
            raise AssertionError('Full source/reset coverage differs')
        if digest not in self.features:
            track = c.track_pitch(target)
            self.features[digest] = (track,c.NoiseObjective(target,track.period))
            self.counts['target_feature_rows'] += 1
        track,noise = self.features[digest]
        self.counts['fresh_whole_metric_rows_started'] += 1
        value = c.chain._measure(target,pcm,speech,track,noise)
        self.counts['fresh_whole_metric_rows_completed'] += 1
        self.measures[key] = value,event
        self.provenance.append(dict(event=event,reused_from=None,key_sha256=sha(repr(key).encode()),
            evaluation_body_cost=dict(wall_seconds=time.perf_counter()-began[0],cpu_seconds=time.process_time()-began[1])))
        return value
