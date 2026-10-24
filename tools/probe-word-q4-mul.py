"""Assemble a real bounded word multiplier and verify it in three AVR engines."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def run(avr_bin,node,output,quick=False,profile='compact'):
    if profile not in ('compact','factored','adaptive','unrolled'):raise ValueError('Unknown word multiply profile')
    output=output.resolve();output.mkdir(parents=True,exist_ok=True)
    source=ROOT/'ATtiny13A/Sound/codec/word-q4'/('multiply.S' if profile in ('compact','unrolled') else 'multiply-factored.S')
    fixture='''.section .text
.global __vectors
__vectors:
 rjmp halt
.org 6
 rjmp irq
halt:
 rjmp halt
'''+('.equ WORD_MUL_ADAPTIVE,1\n' if profile=='adaptive' else '.equ WORD_MUL_UNROLLED,1\n' if profile=='unrolled' else '')+'.include '+json.dumps(source.as_posix())+'''
irq:
 push r16
 in r16,0x3f
 push r16
 ldi r16,0xa5
 eor r16,r16
 sec
 clt
 pop r16
 out 0x3f,r16
 pop r16
 reti
'''
    (output/'fixture.S').write_text(fixture,encoding='utf-8',newline='\n')
    suffix='.exe' if sys.platform=='win32' else ''
    execute=lambda command:subprocess.run(list(map(str,command)),cwd=output,capture_output=True,text=True,check=True,timeout=300).stdout
    execute([avr_bin/('avr-gcc'+suffix),'-mmcu=attiny13a','-nostdlib','-Wl,--defsym=__TEXT_REGION_LENGTH__=1024',
        '-x','assembler','fixture.S','-o','fixture.elf'])
    execute([avr_bin/('avr-objcopy'+suffix),'-O','binary','fixture.elf','fixture.bin'])
    binary=(output/'fixture.bin').read_bytes()
    if len(binary)>1024:raise AssertionError('Fixture exceeds ATtiny13A')
    symbols={}
    for line in execute([avr_bin/('avr-nm'+suffix),'-n','fixture.elf']).splitlines():
        fields=line.split()
        if len(fields)==3:symbols[fields[2]]=int(fields[0],16)
    spec=dict(image=str(output/'fixture.bin'),symbols=symbols,quick=quick,
        kernelBytes=symbols['word_mul_end']-symbols['mul_word_q4'])
    (output/'spec.json').write_text(json.dumps(spec),encoding='utf-8')
    execute([node,ROOT/'tools/verify-word-q4-mul.mjs',output/'spec.json',output/'verification.json'])
    report=json.loads((output/'verification.json').read_text())
    report.update(profile=profile,fixture_bytes=len(binary),fixture_sha256=hashlib.sha256(binary).hexdigest(),
        source_sha256_normalized_lf={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_text(encoding='utf-8').encode()).hexdigest()
            for p in (Path(__file__),source,ROOT/'tools/verify-word-q4-mul.mjs')})
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(report));return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('avr-bin','node','output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--quick',action='store_true');p.add_argument('--profile',choices=('compact','factored','adaptive','unrolled'),default='compact')
    a=p.parse_args();run(a.avr_bin,a.node,a.output,a.quick,a.profile)
