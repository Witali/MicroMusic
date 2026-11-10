"""Direct binary64 batch synthesis and explicit numeric-mode contracts.

The native checks require g++ and Python's standard library only. NumPy is
needed by the array convenience API, never by these ctypes/ABI controls.
"""
import ctypes as ct
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import batch_decoder as batch
from test_sram512_profile import fixture
from test_speech_v9 import sparse_fixture
from speech_v9 import repack

CONFIG=dict(speech=True,speech_compact=True,compact_only=True)
REFERENCE=r'''
#include <cstdio>
#include <fstream>
#include <iterator>
#include <vector>
#include "Lpx4HybridCore.h"
int main(int argc,char** argv){
 if(argc<2||argc>3)return 1;
 std::ifstream file(argv[1],std::ios::binary);
 std::vector<unsigned char> bytes((std::istreambuf_iterator<char>(file)),{});
 Lpx4HybridCore core;if(!core.begin(bytes.data(),bytes.size()))return 2;
 const char mode=argc==3?argv[2][0]:'f';
 if(mode=='s'){
   int16_t sample=0;
   while(core.nextS16(sample))if(fwrite(&sample,sizeof(sample),1,stdout)!=1)return 3;
 }else if(mode=='p'){
   uint8_t sample=0;
   while(core.next(sample))if(fwrite(&sample,sizeof(sample),1,stdout)!=1)return 3;
 }else{
   double sample=0;
   while(core.nextFloat(sample))if(fwrite(&sample,sizeof(sample),1,stdout)!=1)return 3;
 }
 return core.error()||!core.finished()?4:0;
}
'''

def direct(decoder,blobs,n,stride=None,domain='f64'):
    """Exercise each real ABI with guard samples beyond each output row."""
    if stride is None:stride=n+3
    raw=b''.join(blobs);data=(ct.c_uint8*len(raw))(*raw)
    sizes=(ct.c_uint32*len(blobs))(*map(len,blobs));offsets=[];at=0
    for blob in blobs:offsets.append(at);at+=len(blob)
    offsets=(ct.c_uint32*len(blobs))(*offsets)
    status=(ct.c_int32*len(blobs))()
    element,fn,sentinel={'f64':(ct.c_double,decoder.fn_f64,17.25),
                         's16':(ct.c_int16,decoder.fn_s16,17),
                         'pwm':(ct.c_uint8,decoder.fn,17)}[domain]
    output=(element*(len(blobs)*stride+8))(*([sentinel]*(len(blobs)*stride+8)))
    rc=fn(data,offsets,sizes,len(blobs),output,stride,n,status)
    if rc:raise AssertionError(rc)
    for i in range(len(blobs)):
        assert list(output)[i*stride+n:(i+1)*stride]==[sentinel]*(stride-n)
    assert list(output)[len(blobs)*stride:]==[sentinel]*8
    return list(status),[list(output)[i*stride:i*stride+n] for i in range(len(blobs))]

class FloatingBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.folder=Path(cls.temp.name)
        cls.paths={};cls.libs={};cls.references={}
        for version in (5,9):
            path=batch.build_library(cls.folder/f'float-v{version}.so',compact_version=version,float_synthesis=True,**CONFIG)
            cls.paths[version]=path
            cls.libs[version]=batch.BatchDecoder(path,float_synthesis=True)
            harness=cls.folder/'reference.cpp';harness.write_text(REFERENCE)
            executable=cls.folder/f'reference-{version}'
            subprocess.run(['g++','-O3','-std=c++11','-DLPX4_ENABLE_ASM=0','-DLPX4_FLOAT_SYNTHESIS=1',
                '-DLPX4_ENABLE_SPEECH=1','-DLPX4_ENABLE_SPEECH_COMPACT=1','-DLPX4_COMPACT_ONLY=1',
                f'-DLPX4_COMPACT_VERSION={version}','-I'+str(ROOT/'src'),
                str(ROOT/'src/Lpx4HybridCore.cpp'),str(harness),'-o',str(executable)],check=True,capture_output=True)
            cls.references[version]=executable
        cls.fixed_path=batch.build_library(cls.folder/'fixed-v9.so',compact_version=9,**CONFIG)
        cls.fixed=batch.BatchDecoder(cls.fixed_path)

    @classmethod
    def tearDownClass(cls):
        cls.libs.clear();cls.fixed=None;cls.temp.cleanup()

    def reference(self,blob,version,domain='f64'):
        source=self.folder/'input.lpx';source.write_bytes(blob)
        data=subprocess.run([str(self.references[version]),str(source),domain],check=True,capture_output=True).stdout
        code,size={'f64':('d',8),'s16':('h',2),'pwm':('B',1)}[domain]
        return list(struct.unpack('='+str(len(data)//size)+code,data))

    def test_direct_f64_matches_core_without_pcm16_quantization(self):
        fractional=False
        for n in (1,19,20,21,39,40,79,80,81,159,160,161,319,320,321,641):
            old=[fixture(p,n,18,'changing',True) for p in (4,6)]
            for version in (5,9):
                blobs=old if version==5 else [repack(b)[0] for b in old]+[repack(sparse_fixture(n)[0])[0]]
                for domain in ('f64','s16','pwm'):
                    statuses,rows=direct(self.libs[version],blobs,n,domain=domain)
                    self.assertEqual(statuses,[0]*len(blobs))
                    for blob,row in zip(blobs,rows):
                        self.assertEqual(row,self.reference(blob,version,domain))
                        if domain=='f64':
                            self.assertTrue(all(math.isfinite(s) and -1<=s<=1 for s in row))
                            fractional|=any(abs(s*32768-round(s*32768))>1e-7 for s in row)
        self.assertTrue(fractional,'Floating synthesis was unexpectedly confined to the PCM16 grid')

    def test_invalid_rows_eof_and_sample_stride_are_isolated(self):
        for n in (1,21,321):
            good=repack(fixture(6,n,18,'changing',True))[0]
            trailing=bytearray(good+b'\0');struct.pack_into('<H',trailing,11,len(trailing)-13)
            for domain in ('f64','s16','pwm'):
                statuses,rows=direct(self.libs[9],[good,bytes(trailing),b'bad',good],n,domain=domain)
                self.assertEqual(statuses,[0,-4,-2,0]);self.assertEqual(rows[0],rows[3])
                self.assertEqual(direct(self.libs[9],[good],n+1,domain=domain)[0],[-3])

    def test_numeric_modes_keep_final_integer_adapters_and_require_float_for_f64(self):
        self.assertEqual(self.fixed.numeric_mode,'fixed')
        self.assertEqual(self.libs[9].numeric_mode,'float')
        self.assertEqual(self.fixed.fn_f64(None,None,None,0,None,0,0,None),-5)
        for name in ('fn','fn_s16'):
            self.assertEqual(getattr(self.libs[9],name)(None,None,None,0,None,0,0,None),-1)
        with self.assertRaises(ValueError):self.fixed.decode_many_f64([],0)
        for name in ('decode_many','decode_many_s16'):
            self.assertEqual(getattr(self.libs[9],name)([],0),[])
        self.assertEqual(self.libs[9].decode_many_f64([],0),[])
        with self.assertRaises(ValueError):self.libs[9].decode_many_f64([b'bad'],-1)

    def test_prebuilt_modes_unknown_metadata_and_legacy_libraries(self):
        for path,requested in ((self.fixed_path,True),(self.paths[9],False)):
            with self.assertRaises(ValueError):batch.BatchDecoder(path,float_synthesis=requested)
            with self.assertRaises(ValueError):
                with batch.BatchSession('auto',prebuilt=path,compact_version=9,float_synthesis=requested,**CONFIG):pass
        source=self.folder/'metadata.cpp'
        for name,metadata in (('legacy',''),('unknown','extern "C" unsigned lpx4_batch_numeric_mode(){return 7;}'),
                              ('incomplete','extern "C" unsigned lpx4_batch_numeric_mode(){return 1;}')):
            source.write_text('extern "C" int lpx4_batch_decode(){return 0;}\nextern "C" int lpx4_batch_decode_s16(){return 0;}\n'+metadata)
            output=self.folder/f'{name}.so'
            subprocess.run(['g++','-shared','-fPIC',str(source),'-o',str(output)],check=True,capture_output=True)
            if name=='legacy':
                self.assertEqual(batch.BatchDecoder(output).numeric_mode,'fixed')
                with self.assertRaises(ValueError):batch.BatchDecoder(output,float_synthesis=True)
            else:
                with self.assertRaises(ValueError):batch.BatchDecoder(output,float_synthesis=name=='incomplete')

    def test_float_auto_build_failure_and_reference_mode_never_fall_back(self):
        with self.assertRaises(ValueError):batch.BatchSession('reference',float_synthesis=True)
        for error in (FileNotFoundError('compiler missing'),subprocess.CalledProcessError(1,'g++')):
            with patch.object(batch,'cached_library',side_effect=error):
                with self.assertRaises(type(error)):
                    with batch.BatchSession('auto',float_synthesis=True):pass
                with batch.BatchSession('auto') as decoder:self.assertIsNone(decoder)
        for value in (0,1,'float',None):
            with self.assertRaises(ValueError):batch.BatchSession(float_synthesis=value)
            with self.assertRaises(ValueError):batch.cached_library(float_synthesis=value)
            with self.assertRaises(ValueError):batch.build_library(self.folder/'bad.so',float_synthesis=value)

    def test_numeric_mode_and_float_helper_change_cache_and_build_flag(self):
        def fake_build(path,**kwargs):path.write_bytes(b'cache test');return path
        copied=self.folder/'cache-source';shutil.copytree(ROOT/'src',copied/'src')
        with patch.object(batch,'ROOT',copied),patch.object(batch.tempfile,'gettempdir',return_value=str(self.folder)),\
             patch.object(batch,'build_library',side_effect=fake_build) as builder:
            fixed=batch.cached_library(compact_version=9,**CONFIG)
            floating=batch.cached_library(compact_version=9,float_synthesis=True,**CONFIG)
            self.assertNotEqual(fixed,floating)
            self.assertTrue(builder.call_args.kwargs['float_synthesis'])
            helper=copied/'src/Lpx4FloatCacheProbe.h';helper.write_text('// cache dependency probe\n')
            changed=batch.cached_library(compact_version=9,float_synthesis=True,**CONFIG)
            self.assertNotEqual(floating,changed)
        with patch.object(batch.subprocess,'run') as compiler:
            batch.build_library(self.folder/'flag.so',float_synthesis=True)
            command=compiler.call_args.args[0]
            self.assertIn('-DLPX4_FLOAT_SYNTHESIS=1',command)
            self.assertIn('-DLPX4_ENABLE_ASM=0',command)

    def test_one_f64_delegates_without_conversion(self):
        decoder=self.libs[9];sentinel=object()
        with patch.object(decoder,'decode_many_f64',return_value=[sentinel]) as decode:
            self.assertIs(decoder.decode_one_f64(b'blob',37),sentinel)
            decode.assert_called_once_with([b'blob'],37)

    def test_default_feature_selection_also_supports_direct_float(self):
        source=ROOT/'examples/SYNTHETIC_CELP_BUDGET/synthetic_celp_budget.l4hy'
        blob=source.read_bytes();n=int.from_bytes(blob[8:12],'little')
        path=batch.build_library(self.folder/'legacy-float.so',float_synthesis=True)
        decoder=batch.BatchDecoder(path,float_synthesis=True)
        executable=self.folder/'legacy-float-reference'
        subprocess.run(['g++','-O3','-std=c++11','-DLPX4_ENABLE_ASM=0','-DLPX4_FLOAT_SYNTHESIS=1',
            '-I'+str(ROOT/'src'),str(ROOT/'src/Lpx4HybridCore.cpp'),
            str(self.folder/'reference.cpp'),'-o',str(executable)],check=True,capture_output=True)
        for domain,code in (('f64','d'),('s16','h'),('pwm','B')):
            expected=subprocess.run([str(executable),str(source),domain],check=True,capture_output=True).stdout
            statuses,rows=direct(decoder,[blob,b'bad',blob],n,domain=domain)
            self.assertEqual(statuses,[0,-2,0]);self.assertEqual(rows[0],rows[2])
            self.assertEqual(struct.pack('='+str(n)+code,*rows[0]),expected)


if __name__=='__main__':unittest.main()
