"""Pinned host-native ROM/callback references; never builds AVR images."""
from __future__ import annotations

from collections import Counter
import ctypes as ct
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

PREFIX = 'Codecs/LPX/01_ACTIVE_Q0_CODEC/'
REPRO = 'Codecs/LPX/research/v5-external-spi-player-2026-11-01/reproduction/'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save_new(path,value):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:
        stream.write((json.dumps(value,indent=2,allow_nan=False)+'\n').encode())


class Inputs:
    def __init__(self):
        self.pins = {}

    def read(self,path,digest=None):
        path = Path(path).resolve()
        raw = path.read_bytes()
        actual = sha(raw)
        if digest is not None and actual!=digest or str(path) in self.pins and self.pins[str(path)]!=actual:
            raise ValueError('A bound preparation input changed')
        self.pins[str(path)] = actual
        return raw

    def stream(self,meta):
        raw = self.read(meta['path'],meta['stream_sha256'])
        if len(raw)!=meta['file_bytes']:
            raise ValueError('Stored stream length differs')
        return raw

    def verify(self):
        for path,digest in self.pins.items():
            if sha(Path(path).read_bytes())!=digest:
                raise ValueError('A pinned source, reference or stream changed')


def source_inventory(root):
    active = root/PREFIX
    paths = [*(active/'src').rglob('*'),*(active/'tools').glob('*.py'),
        active/'tests/input_callback_native.cpp',active/'tests/test_input_callback.py',active/'tests/test_speech_v4.py',
        *(root/REPRO/name for name in ('prepare_cases.py','native_inputs.py','test_cases.py','.gitattributes'))]
    return {p.relative_to(root).as_posix():sha(p.read_bytes()) for p in paths if p.is_file()}


def bind_source(root,commit,inputs):
    raw = subprocess.check_output(['git','-C',str(root),'archive','--format=tar',commit,'--',
        PREFIX+'src',PREFIX+'tools',PREFIX+'tests/input_callback_native.cpp',
        PREFIX+'tests/test_input_callback.py',PREFIX+'tests/test_speech_v4.py',
        *(REPRO+name for name in ('prepare_cases.py','native_inputs.py','test_cases.py','.gitattributes'))])
    current = source_inventory(root)
    expected = {}
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for member in archive:
            if member.isfile() and member.name in current:
                expected[member.name] = sha(archive.extractfile(member).read())
    if current!=expected:
        raise ValueError('Native reference sources differ from the explicit committed epoch')
    for name,digest in current.items():
        inputs.read(root/name,digest)
    return current


def load_tools(root):
    sys.path[:0] = [str(root/PREFIX/'tools'),str(root/PREFIX/'tests')]
    import numpy as np
    import speech_compact as compact
    from standard_metrics import pwm_duties
    from test_speech_v4 import fixture
    origins = {}
    for name,module in list(sys.modules.items()):
        path = getattr(module,'__file__',None)
        if path and ('/'+PREFIX+'tools/').casefold() in Path(path).as_posix().casefold():
            if Path(path).resolve().parent!=(root/PREFIX/'tools').resolve():
                raise ValueError('A codec module was loaded from another worktree')
            origins[name] = Path(path).resolve().relative_to(root).as_posix()
    if Path(sys.modules['test_speech_v4'].__file__).resolve()!=(root/PREFIX/'tests/test_speech_v4.py').resolve():
        raise ValueError('The deterministic fixture belongs to another source epoch')
    origins['test_speech_v4'] = PREFIX+'tests/test_speech_v4.py'
    from types import SimpleNamespace
    return SimpleNamespace(np=np,compact=compact,pwm_duties=pwm_duties,fixture=fixture,origins=origins)


def verify_meta(meta,n,mode,stored):
    if tuple(map(int,meta[:5]))!=(1,0,n,n,1):
        raise AssertionError('Native reference did not produce the exact complete reset')
    calls,used = int(meta[5]),int(meta[6])
    if mode==0:
        if calls or used:
            raise AssertionError('ROM input unexpectedly requested callback bytes')
        return 0
    if not 22<=used<=stored or calls!=used:
        raise AssertionError('Callback requested-byte count or stored span differs')
    return used


class NativeInputs:
    def __init__(self,root,output,inputs,tools,compiler='g++'):
        self.tools,self.inputs = tools,inputs
        self.libraries,self.cache = {},{}
        self.counts = Counter()
        selected = shutil.which(compiler)
        if selected is None:
            raise ValueError('The native C++ compiler is unavailable')
        inputs.read(selected)
        version = subprocess.check_output([selected,'--version'],text=True,errors='replace').splitlines()[0]
        self.compiler = dict(path=selected,file_sha256=sha(Path(selected).read_bytes()),version=version)
        for only,name in ((0,'common'),(1,'v5-only')):
            path = output/'native'/(name+'-callback.so')
            path.parent.mkdir(parents=True,exist_ok=True)
            if path.exists():
                raise ValueError('A native output already exists')
            flags = ['-O3','-shared','-fPIC','-std=c++11','-DLPX4_ENABLE_SPEECH=1',
                '-DLPX4_ENABLE_SPEECH_COMPACT=1','-DLPX4_COMPACT_ONLY=%d'%only,
                '-DLPX4_ROM_POINTER=1','-DLPX4_ENABLE_INPUT_CALLBACK=1','-DLPX4_ENABLE_ASM=0']
            command = [selected,*flags,'-I'+str(root/PREFIX/'src'),
                str(root/PREFIX/'src/Lpx4HybridCore.cpp'),str(root/PREFIX/'src/native_batch_decoder.cpp'),
                str(root/PREFIX/'tests/input_callback_native.cpp'),'-o',str(path)]
            result = subprocess.run(command,capture_output=True,text=True,errors='replace')
            save_new(output/'native'/(name+'-build-private.json'),dict(command=command,returncode=result.returncode,
                stdout=result.stdout,stderr=result.stderr,compiler=self.compiler))
            result.check_returncode()
            inputs.read(path)
            library = ct.CDLL(str(path.resolve()))
            library.lpx_input_decode.argtypes = [ct.POINTER(ct.c_uint8),ct.c_uint16,ct.c_uint32,
                ct.c_int16,ct.c_uint8,ct.c_uint8,ct.POINTER(ct.c_int16),ct.POINTER(ct.c_uint8),
                ct.c_uint32,ct.POINTER(ct.c_uint32)]
            library.lpx_input_decode.restype = ct.c_int
            self.libraries[name] = library

    def decode(self,library,blob,n,mode,domain,available=None):
        np = self.tools.np
        data = np.frombuffer(blob,np.uint8)
        pcm,pwm,meta = np.empty(n+1,np.int16),np.empty(n+1,np.uint8),np.zeros(8,np.uint32)
        got = library.lpx_input_decode(data.ctypes.data_as(ct.POINTER(ct.c_uint8)),len(blob),
            len(blob) if available is None else available,-1,mode,domain,
            pcm.ctypes.data_as(ct.POINTER(ct.c_int16)),pwm.ctypes.data_as(ct.POINTER(ct.c_uint8)),n+1,
            meta.ctypes.data_as(ct.POINTER(ct.c_uint32)))
        if got!=n:
            raise AssertionError('Native reference output length differs')
        used = verify_meta(meta,n,mode,len(blob))
        return (pcm if domain==0 else pwm)[:n].copy(),used

    def reference(self,blob,profile,n):
        c = self.tools
        if c.compact.unpack(blob)[:2]!=(n,profile) or not 22<=len(blob)<=65535:
            raise ValueError('Saved native-reference stream geometry differs')
        if blob in self.cache:
            self.counts['exact_reset_cache_hits'] += 1
            return self.cache[blob]
        pcm = c.compact.decode_model(blob)
        pwm = c.pwm_duties(pcm)
        if len(pcm)!=n:
            raise AssertionError('Model reference length differs')
        consumed = None
        for library in self.libraries.values():
            for mode in (0,1):
                for domain,target in ((0,pcm),(1,pwm)):
                    actual,used = self.decode(library,blob,n,mode,domain)
                    if not c.np.array_equal(actual,target):
                        raise AssertionError('Native ROM/callback PCM/PWM differs from the full model')
                    self.counts['rom_domain_comparisons' if mode==0 else 'callback_domain_comparisons'] += 1
                    if mode==1:
                        if consumed is not None and consumed!=used:
                            raise AssertionError('Requested bytes differ across native layouts/output domains')
                        consumed = used
                        if used<len(blob):
                            cutoff,cutoff_used = self.decode(library,blob,n,mode,domain,available=used)
                            if cutoff_used!=used or not c.np.array_equal(cutoff,target):
                                raise AssertionError('An unused stored tail was required to finish')
                            self.counts['unused_tail_cutoff_checks'] += 1
        result = dict(pcm=pcm,pwm=pwm,used=consumed)
        self.cache[blob] = result
        self.counts['unique_reset_streams'] += 1
        self.counts['model_samples'] += n
        self.counts['partial_stored_tail_resets'] += consumed<len(blob)
        return result
