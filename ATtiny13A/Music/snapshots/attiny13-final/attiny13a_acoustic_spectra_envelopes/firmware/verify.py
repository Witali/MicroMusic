#!/usr/bin/env python3
"""Instruction/timing checks for the actual ATtiny13A binary (not a JS synth).

Models instruction cycle counts, Timer0 overflows/IRQ latency, I/O writes,
and the instructions used by synth.S. Intended as regression verification,
not as a complete ATtiny13A hardware specification.
"""
from pathlib import Path
import json


def signed(v, n):return v-(1<<n) if v&(1<<(n-1)) else v


class CPU:
    def __init__(self, binary):
        self.rom=bytearray(binary)+bytearray(1024-len(binary))
        self.r=[0]*32
        self.pc=0
        self.cyc=0
        self.z=0;self.c=0;self.i=0
        self.io=[0]*64
        self.spl=0
        self.stack=[]
        self.timer=False;self.next_overflow=10**20;self.pending=False
        self.last_irq=None
        self.irq_cycles=[]
        self.samples=[];self.oob=[]
        self.irq_count=0;self.tick_count=0;self.events=[]
        self.read_event_addr=json.loads((Path(__file__).parent/'symbols.json').read_text())['read_event']
        self.last_section=0
        self.timer_lost=0

    def step(self):
        p=self.pc*2
        if p+1>=len(self.rom):raise RuntimeError(f'PC OOB 0x{p:x}')
        w=self.rom[p]|self.rom[p+1]<<8
        self.pc+=1
        rr=self.r
        cycles=1
        if w == 0:pass
        elif w == 0x94f8:self.i=0
        elif w == 0x9478:self.i=1
        elif w == 0x9518:
            if not self.stack:raise RuntimeError('RETI without PC on stack')
            self.pc=self.stack.pop();self.i=1;cycles=4
            if self.last_irq is not None:
                self.irq_cycles.append(self.cyc+cycles-self.last_irq)
                self.last_irq=None
        elif w == 0x9508: # RET
            if not self.stack:raise RuntimeError('RET without RCALL')
            self.pc=self.stack.pop();cycles=4
        elif w&0xf000==0xd000: # RCALL
            self.stack.append(self.pc);self.pc+=signed(w&0xfff,12);cycles=3
        elif w&0xf000==0xc000: # RJMP
            self.pc+=signed(w&0xfff,12);cycles=2
        elif w&0xfc00 in (0xf000, 0xf400): # BRBS, BRBC
            flag=w&7
            if flag not in (0,1):raise RuntimeError(f'Unknown branch flag {flag} @ {p:x}')
            bit=self.c if flag==0 else self.z
            if bit==int((w&0xfc00)==0xf000):
                self.pc+=signed((w>>3)&0x7f,7);cycles=2
        elif w&0xfe08 in (0xfc00, 0xfe00): # SBRC/SBRS
            reg=(w>>4)&31;bit=w&7
            if ((rr[reg]>>bit)&1)==int((w&0xfe08)==0xfe00):
                skip=self.rom[self.pc*2]|self.rom[self.pc*2+1]<<8
                # All next instructions in this firmware are 1 word.
                if skip&0xfe0e in (0x940c,0x940e,0x9000,0x9200):raise RuntimeError('2-word skipped not supported')
                self.pc+=1;cycles=2
        elif w&0xf000==0xe000: # LDI
            rr[16+((w>>4)&15)]=(w&15)|((w>>4)&0xf0)
        elif w&0xf000 in (0x3000,0x5000,0x7000):
            reg=16+((w>>4)&15);k=(w&15)|((w>>4)&0xf0);x=rr[reg]
            if w&0xf000==0x7000:rr[reg]=x&k;self.z=int(rr[reg]==0)
            else:
                v=(x-k)&255
                if w&0xf000==0x5000:rr[reg]=v
                self.c=int(x<k);self.z=int(v==0)
        elif w&0xff00==0x0100: # MOVW
            d=2*((w>>4)&15);r=2*(w&15);rr[d]=rr[r];rr[d+1]=rr[r+1]
        elif w&0xfc00 in (0x0c00,0x1c00,0x1800,0x2000,0x2400,0x2c00):
            d=(w>>4)&31;r=(w&15)|((w>>5)&16);x=rr[d];y=rr[r]
            mode=w&0xfc00
            if mode in (0x0c00,0x1c00):
                summ=x+y+(self.c if mode==0x1c00 else 0)
                rr[d]=summ&255;self.c=int(summ>255)
                self.z=int(rr[d]==0) and (self.z if mode==0x1c00 else 1)
                self.z=int(self.z)
            elif mode==0x1800:rr[d]=(x-y)&255;self.c=int(x<y);self.z=int(rr[d]==0)
            elif mode==0x2000:rr[d]=x&y;self.z=int(rr[d]==0)
            elif mode==0x2400:rr[d]=x^y;self.z=int(rr[d]==0)
            else:rr[d]=y
        elif w&0xfe0f in (0x9403,0x940a,0x9400,0x9406,0x9405,0x9402):
            d=(w>>4)&31;mode=w&0xfe0f;x=rr[d]
            if mode==0x9403:rr[d]=(x+1)&255;self.z=int(rr[d]==0)
            elif mode==0x940a:rr[d]=(x-1)&255;self.z=int(rr[d]==0)
            elif mode==0x9400:rr[d]=x^255;self.z=int(rr[d]==0);self.c=1
            elif mode==0x9402:rr[d]=((x&15)<<4)|(x>>4) # SWAP does not alter flags
            elif mode==0x9405:rr[d]=((x>>1)|(x&128))&255;self.z=int(rr[d]==0);self.c=x&1
            else:rr[d]=x>>1;self.z=int(rr[d]==0);self.c=x&1
        elif w&0xf800==0xb800: # OUT
            reg=(w>>4)&31;address=((w>>5)&0x30)|(w&15);value=rr[reg]
            self.io[address]=value
            if address==0x3d:self.spl=value
            if address==0x33 and value==1 and not self.timer:
                self.timer=True;self.next_overflow=self.cyc+256
            if address==0x29:
                self.samples.append(value)
        elif w&0xff00==0x9a00: # SBI
            a=(w>>3)&31;b=w&7;self.io[a]|=1<<b;cycles=2
        elif w&0xfe0f==0x9201: # ST Z+,r
            reg=(w>>4)&31;z=(rr[31]<<8)|rr[30]
            if 0<=z<32:rr[z]=rr[reg]
            else:raise RuntimeError(f'ST wrote outside register file {z}')
            z=(z+1)&0xffff;rr[30]=z&255;rr[31]=z>>8;cycles=2
        elif w&0xfe0f in (0x9004,0x9005): # LPM Rd,Z / Rd,Z+
            reg=(w>>4)&31;z=(rr[31]<<8)|rr[30]
            if z>=len(self.rom):raise RuntimeError(f'LPM out of Flash: {z}')
            rr[reg]=self.rom[z]
            if w&1:z+=1;rr[30]=z&255;rr[31]=z>>8
            cycles=3
            if p==self.read_event_addr:self.events.append((rr[reg],z-(1 if w&1 else 0),rr[28]))
        else:
            raise RuntimeError(f'Unknown AVR instruction 0x{w:04x} at byte PC 0x{p:04x}')
        self.cyc+=cycles
        if self.timer:
            while self.next_overflow<=self.cyc:
                if self.pending:self.timer_lost+=1
                self.pending=True
                self.next_overflow+=256
            if self.i and self.io[0x39]&2 and self.pending:
                self.pending=False;self.stack.append(self.pc);self.pc=3;self.i=0
                self.last_irq=self.cyc
                self.cyc+=4;self.irq_count+=1
        return p


def test_seconds(cpu, seconds):
    goal=round(seconds*9600000)
    while cpu.cyc<goal:cpu.step()
    values=cpu.samples
    expected=round(seconds*37500)
    print(f'Normal {seconds:.2f}s: {cpu.cyc} cycles, {cpu.irq_count} IRQ, OCR writes {len(values)}, expected ~{expected}')
    print(f'  PWM values: [{min(values)}, {max(values)}], distinct={len(set(values))}; ISR worst {max(cpu.irq_cycles)} cycles, lost overflows={cpu.timer_lost}')
    print(f'  melodic events observed: {len(cpu.events)}; music note indices (first 16): {[hex(e[0]) for e in cpu.events[:16]]}')
    assert cpu.irq_count>expected-4
    assert max(cpu.irq_cycles) < 256
    assert cpu.timer_lost == 0
    assert len(set(values))>30
    assert max(values)<256


def stress_every_event(binary):
    cpu=CPU(binary)
    while cpu.irq_count<2:cpu.step()
    start_len=len(cpu.events)
    observed_sections=set()
    worst_by_section={}
    # Force a sequencer tick and event after each IRQ to cover the entire
    # compressed score without waiting for minutes of natural playback.
    # The instruction stream and its cycles are still executed normally.
    for k in range(1500):
        cpu.r[15]=255;cpu.r[23]=1;cpu.r[22]=1
        count=cpu.irq_count
        while cpu.irq_count<=count or cpu.last_irq is not None:
            pc=cpu.step()
        observed_sections.add(cpu.r[28])
        worst_by_section[cpu.r[28]]=max(worst_by_section.get(cpu.r[28],0),cpu.irq_cycles[-1])
    print(f'Stress 1500 forced music events: processed {len(cpu.events)-start_len}, playlist indices={sorted(observed_sections)}')
    print(f'  ISR worst {max(cpu.irq_cycles)} cycles, lost overflows={cpu.timer_lost}, worst at playlist {worst_by_section}')
    assert max(cpu.irq_cycles)<256
    assert cpu.timer_lost==0
    assert len(cpu.events)-start_len>=1500, 'Event decoder did not traverse requested score'
    meta=json.loads((Path(__file__).parent/"score.meta.json").read_text())
    expected=set(range(1,len(meta["playlist"])+1))
    assert expected.issubset(observed_sections),(expected,observed_sections)
    return cpu


def main():
    data=(Path(__file__).parent/'synth.bin').read_bytes()
    assert len(data)<=1024
    normal=CPU(data)
    test_seconds(normal,0.80)
    stress_every_event(data)
    print('PASS: 1KB Flash, executable opcodes, sequencer, PWM, 256-cycle ISR budget')


if __name__=='__main__':main()
