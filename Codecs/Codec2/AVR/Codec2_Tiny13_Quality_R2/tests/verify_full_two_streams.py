#!/usr/bin/env python3
"""Slow full regression: execute every AVR instruction on the 218+147 Codec2 frames.
Requires only Python stdlib. Expected duration depends on host Python speed.
"""
from pathlib import Path
from test_resonator import AVR,reference_decoder
from codec2_test_common import parse_asm
import time, sys
ROOT=Path(__file__).resolve().parents[1]
inst,labels,sym=parse_asm(ROOT/'src'/'codec2tiny_resonator.S')
lines=[]
for name in ('speech.c2zx','codec2_3200_8byte_frames.bin'):
    if len(sys.argv)>1 and name!=sys.argv[1]:continue
    raw=(ROOT/'tests'/name).read_bytes()
    frames=[raw[i:i+8] for i in range(0,len(raw),8)]
    assert all(len(f)==8 for f in frames)
    expected=reference_decoder(frames)
    cpu=AVR(inst,labels,sym)
    cpu.run('codec2tiny_init')
    start=time.monotonic()
    peak=0
    for i,f in enumerate(frames):
        cpu.mem[0x60:0x68]=f
        cpu.run('codec2tiny_decode_frame')
        for j in range(160):
            cycles=cpu.run('codec2tiny_sample')
            if cycles>peak:peak=cycles
            assert cpu.r[16]==expected[i*160+j],(name,i,j,cpu.r[16],expected[i*160+j])
    msg=f'{name}: {len(frames)} frames; {len(expected)} PCM samples; ZERO mismatches; sample worst {peak} cycles; runtime {time.monotonic()-start:.1f}s'
    print(msg,flush=True)
    lines.append(msg)
with (ROOT/'reports'/'full_asm_verification.txt').open('a') as fp:
    fp.write('\n'.join(lines)+'\n')
