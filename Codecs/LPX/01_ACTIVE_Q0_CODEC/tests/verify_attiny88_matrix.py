"""Reproduce bounded real-time admission, heavy streams and rejection controls.

Run with Linux AVR-GCC/g++/simavr1.6. All streams, media and target artifacts
stay in ignored repository build storage. No NumPy or private corpus needed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
from test_sram512_profile import fixture

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from verify_attiny88_player import verify

def prefix_v5(blob,frames):
    """Copy an initial whole-packet prefix, preserving every retained bit."""
    if blob[:5]!=b'L4HY\x05' or not 0<frames*320<=int.from_bytes(blob[8:12],'little'):
        raise ValueError('Invalid v5 prefix')
    at=0;bits=5 if blob[5]&127==4 else 6
    def read(n):
        nonlocal at
        value=0
        for i in range(n):value|=((blob[22+at//8]>>(at%8))&1)<<i;at+=1
        return value
    def rice(k,width):
        q=0
        while q<8 and not read(1):q+=1
        read(width if q==8 else k)
    for _ in range(frames):
        if read(1):
            delta=read(1);k=(0 if bits==5 else 1) if delta else (1 if bits==5 else 2)
            for _ in range(10):rice(k,bits+delta)
        for _ in range(2):
            read(15)
            for _ in range(4):
                read(10 if bits==5 else 17)
                if blob[5]&128 and read(1):read(10)
    payload=bytearray(blob[22:22+(at+7)//8])
    if at%8:payload[-1]&=(1<<(at%8))-1
    header=bytearray(blob[:22]);struct.pack_into('<I',header,8,frames*320)
    struct.pack_into('<H',header,20,len(payload))
    return bytes(header)+payload

def run(output,controls=True):
    output=Path(output).resolve()
    if REPO/'build' not in output.parents:raise ValueError('Use ignored build storage')
    output.mkdir(parents=True,exist_ok=True)
    cases=[]
    def check(name,source,expected=True,**kw):
        result=verify(source,output/name,**kw)
        if result['accepted']!=expected:raise AssertionError((name,result))
        cases.append(dict(case=name,**result));print(json.dumps(cases[-1]),flush=True)
    for name,style,lag in [('p6-extras','changing',145),('p6-clusters','clusters',18)]:
        stream=output/(name+'.l4hy');stream.write_bytes(fixture(6,6400,lag,style,True))
        check(name,stream,repeat=8)
    compact=REPO/'web-player/audio/lpx-bread/compact.lpx'
    quality=REPO/'web-player/audio/lpx-bread/quality.lpx'
    check('rom-p4',compact,repeat=4)
    prefix=output/'p6-prefix.l4hy';prefix.write_bytes(prefix_v5(quality.read_bytes(),30))
    check('rom-p6-prefix',prefix,repeat=8)
    # This larger timing control is explicitly outside the bootloader budget.
    check('rom-p6-full-timing-only',quality,repeat=2,flash_limit=8192)
    full=(output/'rom-p6-full-timing-only/expected.pwm').read_bytes()
    first=(output/'rom-p6-prefix/expected.pwm').read_bytes()[:9600]
    if first!=full[:9600]:raise AssertionError('The prefix changed retained decoded output')
    for count in (1,19,20,39,40,159,160,319,320,321):
        stream=output/'tail.l4hy';stream.write_bytes(fixture(6,count,145,'changing',True))
        check('tail-'+str(count),stream)
    if controls:
        check('c-isr',compact,asm_isr=False)
        check('c-arithmetic-reject',compact,expected=False,assembly=False,queue=16)
        small=verify(compact,output/'queue16-control',queue=16)
        cases.append(dict(case='queue16-control',**small));print(json.dumps(cases[-1]),flush=True)
        # The larger timing-only image must be rejected at the default cap.
        try:verify(quality,output/'size-reject')
        except ValueError as exc:
            if 'Complete image' not in str(exc):raise
        else:raise AssertionError('The bootloader Flash cap was not enforced')
    sources=[ROOT/'src/Lpx4Math.h',ROOT/'src/Lpx4HybridCore.cpp',ROOT/'src/Lpx4HybridCore.h',
             ROOT/'examples/ATTINY88_V5_PLAYER/player.cpp',ROOT/'tools/build_attiny88_player.py',
             ROOT/'tools/verify_attiny88_player.py',ROOT.parent/'validation/attiny88/sim_player.c',Path(__file__)]
    receipt=dict(schema='lpx-avr25-realtime-v1',cpu='ATtiny88 / AVR25',clock_hz=16000000,
        sample_hz=8000,default_flash_limit=6656,physical_board_measured=False,
        source_sha256={str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},cases=cases)
    (output/'matrix.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('output',type=Path)
    ap.add_argument('--no-controls',action='store_true')
    args=ap.parse_args();run(args.output,not args.no_controls)
