"""Portable C batch ABI, format selection and reference-cache freshness.

The build/configuration layer needs no NumPy. Exercise the C ABI directly
with ctypes so these reader contracts also run on a minimal g++ host.
"""
import ctypes as ct
import hashlib
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_sram512_profile import fixture
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import batch_decoder as batch
from speech_v9 import repack

CONFIG=dict(speech=True,speech_compact=True,compact_only=True)


def decode(lib,blobs,n,domain):
    raw=b''.join(blobs);data=(ct.c_uint8*len(raw))(*raw)
    sizes=(ct.c_uint32*len(blobs))(*map(len,blobs));offsets=[];at=0
    for blob in blobs:offsets.append(at);at+=len(blob)
    offsets=(ct.c_uint32*len(blobs))(*offsets);status=(ct.c_int32*len(blobs))()
    element=ct.c_int16 if domain else ct.c_uint8
    output=(element*(len(blobs)*n+8))()
    for i in range(len(blobs)*n,len(output)):output[i]=63
    fn=lib.fn_s16 if domain else lib.fn
    rc=fn(data,offsets,sizes,len(blobs),output,n,n,status)
    if rc:raise AssertionError(rc)
    assert list(output)[len(blobs)*n:]==[63]*8,'C batch wrote outside output rows'
    return [(s,hashlib.sha256(bytes(output)[i*n*ct.sizeof(element):(i+1)*n*ct.sizeof(element)]).hexdigest() if not s else None)
            for i,s in enumerate(status)]


class BatchV9Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.folder=Path(cls.temp.name);cls.paths={};cls.libs={}
        for version in (5,9):
            path=batch.build_library(cls.folder/f'v{version}.so',compact_version=version,**CONFIG)
            cls.paths[version]=path;cls.libs[version]=batch.BatchDecoder(path)

    @classmethod
    def tearDownClass(cls):
        cls.libs.clear();cls.temp.cleanup()

    def test_same_c_reference_decodes_both_domains_and_short_v9(self):
        for n in (1,19,20,21,39,40,159,160,161,319,320,321,641):
            old=[fixture(p,n,145,'changing',extra) for p in (4,6) for extra in (False,True)]
            new=[repack(b)[0] for b in old]
            if n==1:self.assertLess(len(new[0]),20)
            for domain in (0,1):
                expected=decode(self.libs[5],old,n,domain)
                self.assertTrue(all(status==0 for status,digest in expected))
                self.assertEqual(decode(self.libs[9],new,n,domain),expected)

    def test_v9_batch_drains_eof_and_isolates_bad_rows(self):
        for n in (1,21,321):
            good,_=repack(fixture(6,n,18,'clusters',True))
            trailing=bytearray(good+b'\0');struct.pack_into('<H',trailing,11,len(trailing)-13)
            for domain in (0,1):
                results=decode(self.libs[9],[good,bytes(trailing),b'bad',good],n,domain)
                self.assertEqual([status for status,digest in results],[0,-4,-2,0])
                self.assertEqual(results[0],results[3])

    def test_format_is_explicit_and_prebuilt_mismatches_are_reported(self):
        self.assertEqual([self.libs[v].compact_version for v in (5,9)],[5,9])
        with batch.BatchSession('batch',prebuilt=self.paths[9],compact_version=9,**CONFIG) as decoder:
            self.assertEqual(decoder.compact_version,9)
        with self.assertRaises(ValueError):
            with batch.BatchSession('batch',prebuilt=self.paths[5],compact_version=9,**CONFIG):pass
        with self.assertRaises(ValueError):batch.BatchSession('batch',compact_version=9)

    def test_arithmetic_header_changes_invalidate_reference_cache(self):
        copied=self.folder/'copied';shutil.copytree(ROOT/'src',copied/'src')
        with patch.object(batch,'ROOT',copied),patch.object(batch.tempfile,'gettempdir',return_value=str(self.folder)):
            before=batch.cached_library(compact_version=9,**CONFIG)
            source=copied/'src/Lpx4MultiplyC.h';source.write_bytes(source.read_bytes()+b'\n// Cache freshness probe.\n')
            after=batch.cached_library(compact_version=9,**CONFIG)
            v5=batch.cached_library(compact_version=5,**CONFIG)
            self.assertNotEqual(before,after);self.assertNotEqual(after,v5)
            a,b=batch.BatchDecoder(before),batch.BatchDecoder(after)
            blob,_=repack(fixture(4,321,18,'changing',False))
            self.assertEqual(decode(a,[blob],321,1),decode(b,[blob],321,1))

    def test_default_legacy_reference_keeps_pcm_and_pwm(self):
        source=ROOT/'examples/SYNTHETIC_CELP_BUDGET/synthetic_celp_budget.l4hy'
        blob=source.read_bytes();n=int.from_bytes(blob[8:12],'little')
        path=batch.build_library(self.folder/'legacy.so');decoder=batch.BatchDecoder(path)
        for domain,probe in ((0,'decode_host.cpp'),(1,'decode_s16_host.cpp')):
            executable=self.folder/f'legacy-reference-{domain}'
            subprocess.run(['g++','-O3','-std=c++11','-DLPX4_ENABLE_ASM=0','-I'+str(ROOT/'src'),
                str(ROOT/'src/Lpx4HybridCore.cpp'),str(ROOT/'tests'/probe),'-o',str(executable)],
                check=True,capture_output=True)
            output=self.folder/f'legacy-{domain}.pcm'
            subprocess.run([str(executable),str(source),str(output)],check=True,capture_output=True)
            expected=hashlib.sha256(output.read_bytes()).hexdigest()
            self.assertEqual(decode(decoder,[blob,b'bad',blob],n,domain),[(0,expected),(-2,None),(0,expected)])


if __name__=='__main__':unittest.main()
