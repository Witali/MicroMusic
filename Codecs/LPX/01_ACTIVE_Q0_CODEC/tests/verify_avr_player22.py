"""Replay the public 22-case corpus through both complete AVR players.

Requires Python stdlib, AVR-GCC, g++, simavr1.6 and libelf. Higher-rate
fixtures change only nominal Fs in the header: these are timing probes,
not newly encoded audio or a sound-quality evaluation. Unsupported Tiny
cases retain accepted=false and their actual underrun counts.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path

from verify_attiny88_universal import ROOT,REPO,streams
from verify_attiny88_player import verify
from speech_v9 import repack
from test_speech_v9 import sparse_fixture,all_pairs

def sha(data):return hashlib.sha256(data).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8'))

def inputs(folder):
    originals=streams(folder/'original')
    originals.extend((
        ('bread-low15',REPO/'web-player/audio/lpx-bread/low15.lpx'),
        ('chego-2k',ROOT/'tests/fixtures/chego-2k-v8.lpx')))
    for style,lag,pre,bright in (
        ('changing',145,0,0),('clusters',18,16384,11469),
        ('changing',145,8192,11469),('changing',18,16383,11468),('clusters',145,1,1)):
        name=f's80-{style}-lag{lag}-pre{pre}-bright{bright}'
        path=folder/(name+'-v8.lpx')
        path.write_bytes(sparse_fixture(12800,style,pre,bright,lag)[0])
        originals.append((name,path))
    pair=folder/'all-pairs-v5.lpx';pair.write_bytes(bytes(all_pairs()))
    originals.append(('all-pairs',pair))
    result=[]
    for name,path in originals:
        destination=folder/(name+'.lpx')
        destination.write_bytes(repack(path.read_bytes())[0])
        result.append((name,destination))
    assert len(result)==22 and len({name for name,_ in result})==22
    return sorted(result)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--baseline',type=Path,help='Previous 8 kHz target/case output directories')
    parser.add_argument('--rates',type=int,nargs='+',choices=(8000,12000,16000),default=[8000])
    parser.add_argument('--jobs',type=int,default=3)
    parser.add_argument('--wsl')
    parser.add_argument('--nano-program-limit',type=int,default=3072)
    args=parser.parse_args();out=args.output.resolve()
    if REPO/'build' not in out.parents:raise ValueError('Use ignored build storage')
    if args.jobs<1:raise ValueError('Jobs must be positive')
    out.mkdir(parents=True,exist_ok=True)
    source=out/'inputs';source.mkdir(exist_ok=True)
    cases=inputs(source)
    paths=[*sorted((ROOT/'src').glob('Lpx4*')),ROOT/'profiles/Lpx4Sram512.h',
        ROOT/'examples/ATTINY88_V5_PLAYER/player.cpp',ROOT/'examples/ATTINY88_V5_PLAYER/irq_registers.inc',
        ROOT/'tools/build_attiny88_player.py',ROOT/'tools/build_atmega328p_player.py',
        ROOT/'tools/verify_attiny88_player.py',ROOT.parent/'validation/attiny88/sim_player.c',Path(__file__)]
    binding={p.relative_to(REPO).as_posix():sha(p.read_bytes().replace(b'\r\n',b'\n')) for p in paths}
    jobs=[]
    for rate in sorted(set(args.rates)):
        folder=source/str(rate);folder.mkdir(exist_ok=True)
        for name,path in cases:
            data=bytearray(path.read_bytes());data[3:5]=rate.to_bytes(2,'little')
            stream=folder/(name+'.lpx');stream.write_bytes(data)
            for target in ('atmega328p','attiny88'):jobs.append((target,rate,name,stream))

    def run(job):
        target,rate,name,stream=job;folder=out/str(rate)/target/name
        result=verify(stream,folder,assembly=True,asm_isr=True,queue=32,wsl=args.wsl,
            normalize_output=True,rom_output_gain=True,target=target,nano_pwm=target=='atmega328p',
            flash_limit=30720 if target=='atmega328p' else 8192)
        cost=read(folder/'build.json')
        assert result['producer_calls']==result['decode_calls']==cost['samples']
        assert result['producer_unpublished_decode_calls']==0
        assert result['samples']==cost['samples']+result['underruns']
        if rate==8000 or target=='atmega328p':assert result['accepted'],(target,rate,name,result)
        if target=='atmega328p':assert result['program_excluding_audio_bytes']<=args.nano_program_limit
        if args.baseline and rate==8000:
            before=args.baseline.resolve()/target/name
            old=read(before/'verification.json')
            assert (before/'actual.pwm').read_bytes()==(folder/'actual.pwm').read_bytes()
            for field in ('static_ram_bytes','stack_bytes'):
                assert result[field]<=old[field],(target,name,field)
            for field in ('producer_cpu_mean','producer_cpu_max','producer_active_cpu_mean','producer_active_cpu_max'):
                assert result[field]+result['irq_max']<=old[field]+old['irq_max'],(target,name,field)
        assert not any(f.startswith('-DLPX4_FIXED_') for f in cost['compiler_options'])
        print(target,rate,name,result['program_excluding_audio_bytes'],result['accepted'],flush=True)
        return dict(target=target,rate=rate,case=name,input_sha256=sha(stream.read_bytes()),
            pwm_sha256=sha((folder/'actual.pwm').read_bytes()),
            binary_sha256=sha((folder/'player.bin').read_bytes()),**result)

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:rows=list(pool.map(run,jobs))
    for name,digest in binding.items():assert sha((REPO/name).read_bytes().replace(b'\r\n',b'\n'))==digest,name
    result=dict(schema='lpx-avr-player22-v1',physical_board_measured=False,
        higher_rate_fixtures='header-retagged timing probes',source_lf_sha256=binding,cases=rows)
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
    for rate in sorted(set(args.rates)):
        for target in ('atmega328p','attiny88'):
            selected=[r for r in rows if r['target']==target and r['rate']==rate]
            print(target,rate,sum(r['accepted'] for r in selected),'of',len(selected),'admitted')

if __name__=='__main__':main()
