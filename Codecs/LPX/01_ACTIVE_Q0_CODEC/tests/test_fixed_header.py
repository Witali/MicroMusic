"""ROM specialization is exact and rejects a mismatched valid header."""
import json
import struct
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_sram512_profile import fixture

ROOT=Path(__file__).resolve().parents[1]
HARNESS=r'''
#include <stdio.h>
#include <string.h>
#include <fstream>
#include <iterator>
#include <vector>
#include "Lpx4HybridCore.h"
int main(int argc,char**argv){
 if(argc!=2)return 1;
 if(!strcmp(argv[1],"--size")){printf("%zu\n",sizeof(Lpx4HybridCore));return 0;}
 std::ifstream f(argv[1],std::ios::binary);
 std::vector<unsigned char>b((std::istreambuf_iterator<char>(f)),{});
 Lpx4HybridCore d;unsigned n=0;uint32_t hash=2166136261u;unsigned char p;
 if(d.begin(b.data(),b.size()))while(d.next(p)){hash=(hash^p)*16777619u;++n;}
 printf("{\"samples\":%u,\"hash\":%u,\"error\":%u,\"declared\":%u,\"produced\":%u,\"rate\":%u}\n",n,hash,(unsigned)d.error(),(unsigned)d.samples(),(unsigned)d.produced(),(unsigned)d.sampleRate());
}
'''
class FixedHeaderTests(unittest.TestCase):
    def test_one_dynamic_binary_reads_profiles_and_filter_parameters_from_each_file(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);source=folder/'main.cpp';source.write_text(HARNESS)
            binaries=[]
            for memory in (0,1):
                exe=folder/f'universal-{memory}'
                subprocess.run(['g++','-O2','-std=c++11','-DLPX4_ENABLE_ASM=0',
                    '-DLPX4_ENABLE_SPEECH=1','-DLPX4_ENABLE_SPEECH_COMPACT=1',
                    '-DLPX4_COMPACT_ONLY=1',f'-DLPX4_MEMORY_PROFILE={memory}',
                    '-I'+str(ROOT/'src'),str(source),str(ROOT/'src/Lpx4HybridCore.cpp'),'-o',str(exe)],
                    check=True,capture_output=True)
                binaries.append(exe)
            stream=folder/'input.lpx';hashes=set()
            for profile in (4,6):
                for extras in (False,True):
                    for pre in (0,1,8192,16383,16384):
                        for bright in (0,64,11469):
                            blob=bytearray(fixture(profile,641,145,'changing',extras))
                            struct.pack_into('<HH',blob,12,pre,bright);stream.write_bytes(blob)
                            results=[json.loads(subprocess.check_output([str(exe),str(stream)])) for exe in binaries]
                            self.assertEqual(results[0],results[1],(profile,extras,pre,bright))
                            self.assertEqual(results[1]['samples'],641)
                            self.assertEqual(results[1]['error'],0)
                            hashes.add(results[1]['hash'])
            self.assertGreater(len(hashes),10,'The same compiled decoder must use the file-defined parameters')

    def test_exact_generic_and_pinned_header_and_rejections(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);source=folder/'main.cpp';source.write_text(HARNESS)
            binaries=[]
            for name,flags in [('dynamic',[]),('fixed',['-DLPX4_FIXED_SPEECH_FLAGS=134',
                    '-DLPX4_FIXED_PRE_Q14=8192','-DLPX4_FIXED_BRIGHT_Q14=11469'])]:
                exe=folder/name
                subprocess.run(['g++','-O2','-std=c++11','-include',str(ROOT/'profiles/Lpx4Sram512.h'),
                    '-I'+str(ROOT/'src'),*flags,str(source),str(ROOT/'src/Lpx4HybridCore.cpp'),'-o',str(exe)],
                    check=True,capture_output=True)
                binaries.append(exe)
            stream=folder/'stream.l4hy'
            blob=fixture(6,641,145,'changing',True);stream.write_bytes(blob)
            run=lambda exe:json.loads(subprocess.check_output([str(exe),str(stream)]))
            expected=run(binaries[0]);self.assertEqual(expected['samples'],641);self.assertEqual(expected['error'],0)
            self.assertEqual(run(binaries[1]),expected)
            bad=[fixture(4,641,18,'static',True)]
            for at,value in [(12,8193),(14,11468)]:
                b=bytearray(blob);b[at:at+2]=value.to_bytes(2,'little');bad.append(bytes(b))
            for b in bad:
                stream.write_bytes(b)
                self.assertEqual(run(binaries[0])['error'],0)
                self.assertEqual(run(binaries[1])['error'],2)
                self.assertEqual(run(binaries[1])['samples'],0)

    def test_each_pinned_field_keeps_portable_output_and_its_own_rejection(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);source=folder/'main.cpp';source.write_text(HARNESS)
            stream=folder/'stream.lpx';blob=fixture(6,641,145,'clusters',True)
            pins=['-DLPX4_FIXED_PRE_Q14=8192','-DLPX4_FIXED_BRIGHT_Q14=11469','-DLPX4_FIXED_SPEECH_FLAGS=134']
            reference=None
            for memory in (0,1):
                sizes=[]
                for mask in range(8):
                    exe=folder/f'decode-{memory}-{mask}'
                    flags=[pin for bit,pin in enumerate(pins) if mask&(1<<bit)]
                    subprocess.run(['g++','-O2','-std=c++11','-DLPX4_ENABLE_SPEECH=1',
                        '-DLPX4_ENABLE_SPEECH_COMPACT=1','-DLPX4_COMPACT_ONLY=1',f'-DLPX4_MEMORY_PROFILE={memory}',
                        '-I'+str(ROOT/'src'),*flags,str(source),str(ROOT/'src/Lpx4HybridCore.cpp'),'-o',str(exe)],
                        check=True,capture_output=True)
                    sizes.append(int(subprocess.check_output([str(exe),'--size'])))
                    run=lambda:json.loads(subprocess.check_output([str(exe),str(stream)]))
                    stream.write_bytes(blob);actual=run()
                    if reference is None:reference=actual
                    self.assertEqual(actual,reference,(memory,mask))
                    self.assertEqual(actual['declared'],641);self.assertEqual(actual['produced'],641);self.assertEqual(actual['rate'],8000)
                    for bit,at,value in [(0,12,8193),(1,14,11468),(2,5,6)]:
                        altered=bytearray(blob)
                        if bit==2:altered[at]=value
                        else:altered[at:at+2]=value.to_bytes(2,'little')
                        # Flags without extras need a different legal payload.
                        if bit==2:altered=fixture(6,641,145,'clusters',False)
                        stream.write_bytes(altered);result=run()
                        self.assertEqual(result['error'],2 if mask&(1<<bit) else 0,(memory,mask,bit))
                        self.assertEqual(result['samples'],0 if mask&(1<<bit) else 641)
                if memory==0:self.assertEqual(len(set(sizes)),1)
                else:self.assertLessEqual(sizes[7],sizes[0])
