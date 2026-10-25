"""Measure isolated, lossless UM88 candidates without editing release sources.

Candidates are research examples, not production firmware. Every image is
compiled from a private source copy and checked by the independent PWM oracle.
No MIDI binaries are created. GNU AVR 7.3 and Node are required.
"""
from pathlib import Path
import argparse
import hashlib
import json
import runpy
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'ATtiny88/Music/universal'
EXAMPLES=ROOT/'docs/avr-asm-cookbook/examples'

def save(path,value):path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
def run(*args):
    result=subprocess.run([str(x) for x in args],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
    if result.returncode:raise RuntimeError(result.stderr or result.stdout)

def measure(variant,score,cpu,output):
    with tempfile.TemporaryDirectory(dir=output,prefix='source-') as work:
        sandbox=Path(work);source=sandbox/'ATtiny88/Music/universal';source.mkdir(parents=True)
        for file in SOURCE.iterdir():
            if file.is_file() and file.suffix in ('.c','.h','.S','.inc'):shutil.copyfile(file,source/file.name)
        shutil.copytree(SOURCE/'vendor',source/'vendor')
        platform=(source/'platform.c').read_text(encoding='utf-8')
        if variant!='baseline':
            shutil.copyfile(SOURCE/'rational-clocks.h',source/'rational-clocks.h')
            platform=platform.replace('#include "clock.h"','#include "clock.h"\n#include "rational-clocks.h"')
            platform=platform.replace('uint32_t fraction=0,musicClock=0;', 'UMFraction fraction=0;UMMusicClock musicClock=0;')
            platform=platform.replace('fraction+=VIRTUAL_NUMERATOR%F_CPU;', 'fraction+=UM_DRUM_FRACTION_INCREMENT;')
            platform=platform.replace('fraction>=F_CPU){fraction-=F_CPU;', 'fraction>=UM_DRUM_FRACTION_PERIOD){fraction-=UM_DRUM_FRACTION_PERIOD;')
            platform=platform.replace('musicClock+=75000UL;', 'musicClock+=UM_CONTROL_INCREMENT;')
            platform=platform.replace('musicClock>=F_CPU){musicClock-=F_CPU;', 'musicClock>=UM_CONTROL_PERIOD){musicClock-=UM_CONTROL_PERIOD;')
        if variant in ('clocks-tick','clocks-tick-alignment'):
            file=source/'engine.c';engine=file.read_text(encoding='utf-8')
            start=engine.index('void um_tick(void) {');end=engine.index('\n#if !defined(__AVR_ATtiny88__)',start)
            engine=engine[:start]+(EXAMPLES/'um88-tick-pointer.c.inc').read_text(encoding='utf-8')+engine[end:]
            file.write_text(engine,encoding='utf-8',newline='\n')
        if variant=='clocks-tick-alignment':platform=platform.replace('aligned(64)','aligned(1)')
        (source/'platform.c').write_text(platform,encoding='utf-8',newline='\n')
        destination=output/(score['name']+'-'+str(cpu)+'-'+variant);destination.mkdir(exist_ok=True)
        score_file=destination/'input-score.json';save(score_file,score)
        builder=runpy.run_path(str(ROOT/'tools/build-universal-music.py'))['main']
        builder.__globals__['ROOT']=sandbox
        saved_argv=sys.argv
        try:
            sys.argv=['build-universal-music.py','--backend','avr-asm','--cpu-hz',str(cpu),'--score',str(score_file),'--output-dir',str(destination)]
            builder()
        finally:sys.argv=saved_argv
        folder=destination/score['name']
        run('node',ROOT/'tools/audit-universal-music.mjs','--directory='+str(destination),score['name'])
        run('node',ROOT/'tools/profile-universal-music.mjs',folder,folder/'profile.json')
        audit=json.loads((folder/'verification.json').read_text(encoding='utf-8'))
        profile=json.loads((folder/'profile.json').read_text(encoding='utf-8'))
        assert audit['passed'] and audit['fifoUnderruns']==0 and profile['fifoUnderruns']==0
        print(variant,score['name'],cpu,'busy',round(profile['busyCyclesPerSample'],3),'code',profile['engineBytes'],flush=True)
        return dict(candidate=variant,verification=audit,profile=profile)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'build/universal/algorithm-review')
    parser.add_argument('--report',type=Path)
    args=parser.parse_args();output=args.output_dir.resolve();output.mkdir(parents=True,exist_ok=True)
    fixture=runpy.run_path(str(ROOT/'tools/test-universal-admission.py'))['fixture']
    dense=fixture('dense-eight-review',8,True)
    study=json.loads((SOURCE/'examples/polyphony-study/generated/score.json').read_text(encoding='utf-8'))
    cases=[]
    for score in (dense,study):
        for variant in ('baseline','clocks','clocks-tick','clocks-tick-alignment'):
            cases.append(measure(variant,score,8000000,output))
    for cpu in (12000000,8388608):
        for variant in ('baseline','clocks-tick-alignment'):cases.append(measure(variant,study,cpu,output))
    report=dict(schema='micromusic-um88-algorithm-review',version=1,baselineCommit='0c306b1',
                hardwareTested=False,productionFirmwareChanged=False,cases=cases,
                sourceHashes={name:hashlib.sha256((SOURCE/name).read_bytes()).hexdigest() for name in ('engine.c','platform.c','render-avr.S','irq-avr.S')},
                constraints='ATtiny88, AVR25, GNU AVR 7.3.0 -Os; explicit ASM backend; C-only clock/control candidates; complete specified loops plus restart with IRQ active')
    save(args.report or output/'review.json',report)

if __name__=='__main__':main()
