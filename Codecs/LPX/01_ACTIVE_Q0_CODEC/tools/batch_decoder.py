"""Host-only batched C++ LPX4 decoder; no changes to AVR ROM or firmware.

Calls the portable C Lpx4HybridCore for each stream inside ONE native
library invocation. Keeps all PCM in RAM and eliminates fork/exec/file I/O.
The reference subprocess decoder remains available for regression tests.
"""
from __future__ import annotations
import ctypes as ct
import hashlib
import platform
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import numpy as np

ROOT = Path(__file__).resolve().parent.parent


def build_library(output: Path, compiler: str = 'g++', v3_features=0, speech=False) -> Path:
    if v3_features<0 or v3_features&~124:raise ValueError('Unknown v3 feature bits')
    compiler_path = shutil.which(compiler)
    if not compiler_path:
        raise FileNotFoundError(f'Native batch build requires {compiler}')
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [compiler_path, '-O3', '-fPIC', '-shared', '-std=c++11',
           '-I'+str(ROOT/'src'), str(ROOT/'src'/'Lpx4HybridCore.cpp'),
           str(ROOT/'src'/'native_batch_decoder.cpp'), '-o', str(output)]
    if v3_features:cmd.insert(1,'-DLPX4_V3_FEATURES='+str(v3_features))
    if speech:cmd.insert(1,'-DLPX4_ENABLE_SPEECH=1')
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return output


class BatchDecoder:
    def __init__(self, library_path: Path):
        self.library_path = Path(library_path)
        self.dll = ct.CDLL(str(self.library_path.resolve()))
        self.fn = self.dll.lpx4_batch_decode
        p8 = ct.POINTER(ct.c_uint8)
        p32 = ct.POINTER(ct.c_uint32)
        self.fn.argtypes = [p8, p32, p32, ct.c_uint32, p8, ct.c_uint32,
                            ct.c_uint32, ct.POINTER(ct.c_int32)]
        self.fn.restype = ct.c_int
        self.fn_s16 = self.dll.lpx4_batch_decode_s16
        self.fn_s16.argtypes = [p8, p32, p32, ct.c_uint32,
                                ct.POINTER(ct.c_int16), ct.c_uint32,
                                ct.c_uint32, ct.POINTER(ct.c_int32)]
        self.fn_s16.restype = ct.c_int
        self.calls = 0
        self.streams = 0

    def decode_many(self, blobs: list[bytes], expected_samples: int):
        if not blobs:
            return []
        if not (0 <= expected_samples <= 1000000):
            raise ValueError('Invalid PCM length')
        if len(blobs) > 512:
            return [z for i in range(0, len(blobs), 512)
                    for z in self.decode_many(blobs[i:i+512], expected_samples)]
        sizes = np.asarray([len(x) for x in blobs], dtype=np.uint32)
        offsets = np.empty(len(blobs), dtype=np.uint32)
        offsets[0] = 0
        if len(blobs) > 1:
            offsets[1:] = np.cumsum(sizes[:-1], dtype=np.uint32)
        raw = np.frombuffer(b''.join(blobs), dtype=np.uint8)
        if not len(raw):
            return [None]*len(blobs)
        pcm = np.empty((len(blobs), expected_samples), dtype=np.uint8)
        status = np.empty(len(blobs), dtype=np.int32)
        pu8 = ct.POINTER(ct.c_uint8)
        pu32 = ct.POINTER(ct.c_uint32)
        rc = self.fn(raw.ctypes.data_as(pu8), offsets.ctypes.data_as(pu32),
                     sizes.ctypes.data_as(pu32), len(blobs),
                     pcm.ctypes.data_as(pu8), expected_samples, expected_samples,
                     status.ctypes.data_as(ct.POINTER(ct.c_int32)))
        if rc:
            raise RuntimeError(f'batch C++ API call failed: {rc}')
        self.calls += 1
        self.streams += len(blobs)
        # Retain the PCM backing memory via each row view's .base.
        return [pcm[i] if status[i] == 0 else None for i in range(len(blobs))]

    def decode_many_s16(self, blobs: list[bytes], expected_samples: int):
        """Return signed PCM16 samples *before PWM*, one array per stream.

        PCM16 is saturated(2*post-filter signed Q14), nominal full-scale mapping.
        The return values do not depend on the 8-bit PWM gain constant.
        """
        if not blobs:
            return []
        if not (0 <= expected_samples <= 1000000):
            raise ValueError('Invalid PCM16 length')
        if len(blobs)>512:
            return [z for i in range(0,len(blobs),512)
                    for z in self.decode_many_s16(blobs[i:i+512],expected_samples)]
        sizes=np.asarray([len(x) for x in blobs],dtype=np.uint32)
        offsets=np.empty(len(blobs),dtype=np.uint32)
        offsets[0]=0
        if len(blobs)>1:
            offsets[1:]=np.cumsum(sizes[:-1],dtype=np.uint32)
        raw=np.frombuffer(b''.join(blobs),dtype=np.uint8)
        if not len(raw):return [None]*len(blobs)
        pcm=np.empty((len(blobs),expected_samples),dtype=np.int16)
        status=np.empty(len(blobs),dtype=np.int32)
        pu8=ct.POINTER(ct.c_uint8);pu32=ct.POINTER(ct.c_uint32)
        rc=self.fn_s16(raw.ctypes.data_as(pu8),offsets.ctypes.data_as(pu32),
                        sizes.ctypes.data_as(pu32),len(blobs),
                        pcm.ctypes.data_as(ct.POINTER(ct.c_int16)),
                        expected_samples,expected_samples,
                        status.ctypes.data_as(ct.POINTER(ct.c_int32)))
        if rc:raise RuntimeError(f'PCM16 C++ batch failed: {rc}')
        self.calls+=1;self.streams+=len(blobs)
        return [pcm[i] if status[i]==0 else None for i in range(len(blobs))]

    def decode_one_s16(self,blob:bytes,expected_samples:int):
        return self.decode_many_s16([blob],expected_samples)[0]

    def decode_one(self, blob: bytes, expected_samples: int):
        return self.decode_many([blob], expected_samples)[0]


def cached_library(v3_features=0, speech=False) -> Path:
    """Content-keyed cache: compile once per C++ source revision and platform."""
    srcs = [ROOT/'src'/'Lpx4HybridCore.cpp', ROOT/'src'/'Lpx4HybridCore.h', ROOT/'src'/'Lpx4Math.h',
            ROOT/'src'/'native_batch_decoder.cpp', ROOT/'src'/'cos_half_table.inc', ROOT/'src'/'cos_table.inc',
            ROOT/'src'/'scale_table.inc']
    h = hashlib.sha256()
    h.update(repr((v3_features,bool(speech))).encode())
    for item in srcs:
        h.update(item.name.encode()); h.update(item.read_bytes())
    h.update(platform.machine().encode()); h.update(platform.system().encode())
    compiler = shutil.which('g++')
    if compiler:
        h.update(compiler.encode())
    cache_dir = Path(tempfile.gettempdir())/'micromusic_lpx4_host_cache'
    target = cache_dir/('lpx4batch_'+h.hexdigest()[:24]+'.so')
    if not target.is_file():
        cache_dir.mkdir(exist_ok=True, parents=True)
        intermediate = target.with_suffix('.building.so')
        build_library(intermediate,v3_features=v3_features,speech=speech)
        intermediate.replace(target)
    return target


class BatchSession:
    """One compiled decoder, cached by source fingerprint for future runs."""
    def __init__(self, mode='auto', prebuilt=None, v3_features=0, speech=False):
        if mode not in ('auto','batch','reference'):
            raise ValueError(mode)
        self.mode = mode
        self.prebuilt = prebuilt
        self.v3_features=v3_features
        self.speech=speech
        self.decoder = None

    def __enter__(self):
        if self.mode == 'reference':
            return None
        try:
            path = Path(self.prebuilt) if self.prebuilt else cached_library(self.v3_features,self.speech)
            self.decoder = BatchDecoder(path)
            return self.decoder
        except (OSError, subprocess.CalledProcessError):
            if self.mode == 'batch':
                raise
            return None

    def __exit__(self, *exc):
        self.decoder = None
