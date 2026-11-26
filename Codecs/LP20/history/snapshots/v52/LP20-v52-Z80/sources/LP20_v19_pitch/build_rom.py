#!/usr/bin/env python3
"""Build/check a ROM-only 20 MHz Z80 image from the encoder's training.npz.
Fails rather than exceeding 16 KiB of static decoder data or 64 KiB ROM."""
import argparse,json,subprocess
from pathlib import Path
from study_pitch import ROOT,V18,np
from build_context_fast import build
from pack_context import pack,unpack

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('model');p.add_argument('--out',required=True);a=p.parse_args()
 src=Path(a.model).resolve();out=Path(a.out).resolve();out.parent.mkdir(parents=True,exist_ok=True)
 d=dict(np.load(src));meta=json.loads((V18/'release/compact/decoder.json').read_text());m=build(src,out,period=320,grid=meta['grid'],alpha=.001)
 core=m['used']-m['stream_bytes'];assert core<=16384 and m['used']<=65536
 cpu=ROOT.parent/'LP20_v17_gain'/'test_fast';cpp=cpu.with_suffix('.cpp')
 if not cpu.exists():subprocess.run(['g++','-std=c++17','-O3',str(cpp),'-o',str(cpu)],check=True)
 test=json.loads(subprocess.check_output([str(cpu),str(out.with_suffix('.bin')),str(out.with_suffix('.map')),str(out.with_suffix('.expected')),'320','8','0','16',str(out.with_suffix('.threads'))],text=True));assert test['memory_writes']==0
 sz=pack(d,m,out.with_suffix('.lp10g'));dd,_=unpack(out.with_suffix('.lp10g'));assert np.array_equal(dd['y'],d['y']) and np.array_equal(dd['idx'],d['idx']);test.update(core_bytes=core,occupied_rom=m['used'],container_bytes=sz,stream_bytes=m['stream_bytes']);out.with_suffix('.test.json').write_text(json.dumps(test,indent=2));print(json.dumps(test,indent=2))
if __name__=='__main__':main()
