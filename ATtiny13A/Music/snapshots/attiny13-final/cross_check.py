#!/usr/bin/env python3
"""Compare 5000 PWM updates from independent Python and JS AVR instruction interpreters."""
from pathlib import Path
import subprocess
from python_emulator import CPU

root=Path(__file__).resolve().parent
b=(root/'synth.bin').read_bytes(); ep=(root/'eeprom.bin').read_bytes()
c=CPU(b,ep)
assert len(b)==1024 and len(ep)==64
values=bytes(c.next_duty() for _ in range(5000))
js=subprocess.check_output(['node','-e', '''
const fs=require('fs'); const {AVRCore}=require('./avr_core.js');
const c=AVRCore.fromHex(fs.readFileSync('synth.hex','utf8'),fs.readFileSync('eeprom.hex','utf8'));
const b=Buffer.alloc(5000);for(let i=0;i<b.length;i++)b[i]=c.nextDuty(); process.stdout.write(b);
'''],cwd=root)
if values !=js:
    i=next(i for i,(a,b) in enumerate(zip(values,js)) if a!=b)
    raise RuntimeError(f'MISMATCH at PWM sample {i}: Python={values[i]} JS={js[i]}')
print(f'PASS: 5000 PWM duty samples match exactly, independent Python and JS AVR interpreters. Max ISR Python: {max(c.irq_cycles)} cycles; lost overflows: {c.timer_lost}')
