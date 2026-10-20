#!/usr/bin/env python3
"""Check that quiet voices render exact PWM=128; summarize music DC bias."""
from pathlib import Path
from verify import CPU
code=(Path(__file__).parent/'synth.bin').read_bytes()
cpu=CPU(code)
while cpu.irq_count<4: cpu.step()
for r in (4,5):cpu.r[r]=0  # no lead DDS step
for r in (19,20,21):cpu.r[r]=4  # piano/guitar/percussion released
cpu.r[22]=255                  # no note events during quiet test
cpu.r[25]=0
old=len(cpu.samples)
while len(cpu.samples)<old+220:cpu.step()
steady=cpu.samples[old+2:]
assert set(steady)=={128},(min(steady),max(steady))
print('PASS: silence = OCR0B 128 for all',len(steady),'PWM periods')

cpu=CPU(code)
while cpu.cyc<9600000:cpu.step()
vals=cpu.samples
avg=sum(vals)/len(vals)
assert abs(avg-128)<3.0,avg
assert max(cpu.irq_cycles)<256
assert cpu.timer_lost==0
print(f'PASS: 1s music mean PWM {avg:.3f}; range [{min(vals)}, {max(vals)}]; max ISR {max(cpu.irq_cycles)} cycles; lost IRQ 0')
