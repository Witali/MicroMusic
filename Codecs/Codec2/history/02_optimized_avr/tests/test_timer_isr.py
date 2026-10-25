#!/usr/bin/env python3
"""Instruction-level Timer0 overflow ISR code path, not hardware peripherals."""
from pathlib import Path
import sys,tempfile
sys.path.insert(0,str(Path(__file__).parent))
from test_codec2tiny import parse_asm,AVR
root=Path(__file__).resolve().parents[1]
demo=(root/'src/tiny13_pwm_oneframe_demo.S').read_text()
core=(root/'src/codec2tiny3200.S').read_text()
source=demo.replace('#include "codec2tiny3200.S"',core)
# Parser ignores .byte data at end and comments: sufficient for ISR verification.
with tempfile.NamedTemporaryFile(mode='w+',suffix='.S',delete=False) as f:
    f.write(source);file=f.name
inst,labels,sym=parse_asm(Path(file));Path(file).unlink()
assert labels['pwm_ovf_irq'] < labels['codec2tiny_sample']
sim=AVR(inst,labels,sym)
sim.run('codec2tiny_init')
sim.mem[0x60:0x68]=bytes.fromhex('cdf142268194b782')
sim.run('codec2tiny_decode_frame')
assert sim.mem[0x7b]==0
assert sim.mem[0x7c]==0
sim.mem[0x49]=128
r=sim.r;r[16]=0x63;r[17]=0x27;r[18]=0x92;r[19]=0x1a;r[20]=0x4b;r[21]=0x05
old_regs=r[15:28].copy()
cycle_counts=[];sample_steps=[]
for i in range(750):
    old=sim.mem[0x7b]
    cost=sim.run('pwm_ovf_irq')
    cycle_counts.append(cost)
    assert sim.r[15:28]==old_regs,(i,sim.r[15:28],old_regs)
    assert sim.mem[0x49]<=255
    assert not sim.stkdata
    if old!=sim.mem[0x7b]:sample_steps.append(i)
assert len(sample_steps)==160,(len(sample_steps),sample_steps[:30])
assert sim.mem[0x7b]==0
assert max(cycle_counts)<256, max(cycle_counts)
assert len(set(sample_steps[i+1]-sample_steps[i] for i in range(len(sample_steps)-1)))==2
freq=37500*len(sample_steps)/750
print('PASS: 750 ISR invocations: %d samples @ %.0f Hz, ISR min/max %d/%d cycles, average %.2f'%(len(sample_steps),freq,min(cycle_counts),max(cycle_counts),sum(cycle_counts)/len(cycle_counts)))
print('First samples at timer overflows',sample_steps[:25])
(root/'tests'/'isr_cycles.txt').write_text('interrupts=750\nsamples=160\nfrequency=8000\nisr_min=%d\nisr_max=%d\nisr_average=%.2f\n'%(min(cycle_counts),max(cycle_counts),sum(cycle_counts)/len(cycle_counts)))
