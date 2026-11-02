"""ROM specialization is exact and rejects a mismatched valid header."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_sram512_profile import fixture

ROOT=Path(__file__).resolve().parents[1]
HARNESS=r'''
#include <stdio.h>
#include <fstream>
#include <iterator>
#include <vector>
#include "Lpx4HybridCore.h"
int main(int argc,char**argv){
 if(argc!=2)return 1;
 std::ifstream f(argv[1],std::ios::binary);
 std::vector<unsigned char>b((std::istreambuf_iterator<char>(f)),{});
 Lpx4HybridCore d;unsigned n=0;uint32_t hash=2166136261u;unsigned char p;
 if(d.begin(b.data(),b.size()))while(d.next(p)){hash=(hash^p)*16777619u;++n;}
 printf("{\"samples\":%u,\"hash\":%u,\"error\":%u}\n",n,hash,(unsigned)d.error());
}
'''
class FixedHeaderTests(unittest.TestCase):
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
