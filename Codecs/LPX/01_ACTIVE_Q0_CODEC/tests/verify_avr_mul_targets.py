"""Check LPX arithmetic selection in real AVR compiler/linker outputs.

This is an ISA/selection check, not an audio throughput measurement. It never
defines compiler CPU macros or changes the decoder's arithmetic implementation.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parents[2]
PROBE = '''#include <avr/io.h>
#include "Lpx4Math.h"
volatile int16_t operand_x=-32768,operand_y=32767;
volatile int32_t product;
volatile uint8_t selected_backend=LPX4_USE_AVR_ASM || LPX4_USE_AVR_NOMUL_ASM;
__attribute__((noinline)) int32_t multiply(int16_t x,int16_t y){return lpx4Mul16(x,y);}
int main(){product=multiply(operand_x,operand_y);for(;;){}}
'''


def run(avr_bin, output):
    avr_bin, output = avr_bin.resolve(), output.resolve()
    if output.exists() or REPOSITORY / 'build' not in output.parents:
        raise ValueError('Use a fresh output directory below repository build/')
    output.mkdir(parents=True)
    suffix = '.exe' if os.name == 'nt' else ''
    tool = lambda name: str(avr_bin / ('avr-' + name + suffix))
    source = output / 'multiply.cpp'
    source.write_text(PROBE, encoding='utf-8', newline='\n')
    header = ROOT / 'src/Lpx4Math.h'
    headers = [header,ROOT/'src/Lpx4MultiplyC.h',ROOT/'src/Lpx4MultiplyAvr.h']
    hashes = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in headers}
    rows = []
    matrix = [('atmega328p', 0, 0, 0, True), ('atmega328p', 1, 1, 0, True),
              ('attiny88', 0, 0, 0, False), ('attiny88', 1, 0, 1, False),
              ('attiny13a', 1, 0, 1, False)]
    for target, enabled, selected, nomul, has_mul in matrix:
        stem = output / (target + '-asm' + str(enabled))
        flags = ['-mmcu=' + target, '-Os', '-std=gnu++11',
                 '-DLPX4_ENABLE_ASM=' + str(enabled), '-I' + str(ROOT / 'src')]
        if target=='attiny88':
            flags+=['-I'+str(REPOSITORY/'ATtiny88/Music/universal/vendor/ATtiny_DFP/3.4.278/include')]
        command = [tool('g++'), *flags, '-dM', '-E', '-x', 'c++', str(source)]
        macros_text = subprocess.check_output(command, text=True)
        macros = dict(re.findall(r'^#define (\w+)[ \t]*(.*?)$', macros_text, re.M))
        assert (macros.get('__AVR_HAVE_MUL__') == '1') == has_mul
        assert int(macros['LPX4_USE_AVR_ASM']) == selected
        assert int(macros['LPX4_USE_AVR_NOMUL_ASM']) == nomul
        result = subprocess.run([tool('g++'), *flags, str(source), '-o', str(stem) + '.elf'],
                                capture_output=True)
        Path(str(stem) + '-build-private.log').write_bytes(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError('Compile/link failed; inspect the ignored build log')
        disassembly = subprocess.check_output([tool('objdump'), '-d', str(stem) + '.elf'], text=True)
        Path(str(stem) + '-disassembly-private.txt').write_text(disassembly, encoding='utf-8')
        instructions = re.findall(r'\t(?:mul|muls|mulsu|fmul|fmuls|fmulsu)\s', disassembly)
        symbols = subprocess.check_output([tool('nm'), '--defined-only', str(stem) + '.elf'], text=True)
        helpers = sorted(set(re.findall(r'\b(__[A-Za-z0-9_]*mul[A-Za-z0-9_]*)$', symbols, re.M)))
        assert bool(instructions) == has_mul
        if not has_mul and not nomul:
            assert helpers, 'Expected the compiler-linked software multiply helper'
        if nomul:assert not helpers, 'Expected the explicit software ASM product'
        rows.append(dict(target=target, assembly_requested=bool(enabled),
                         assembly_selected=bool(selected or nomul),
                         assembly_backend='avr5-mul' if selected else 'avr25-nomul' if nomul else 'c',
                         hardware_mul_available=has_mul,
                         linked_mul_instructions=len(instructions), software_or_runtime_helpers=helpers))
    assert {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in headers} == hashes
    receipt = dict(status='PASS', kind='real-target-compile-and-disassembly',
                   compiler=subprocess.check_output([tool('g++'), '--version'], text=True).splitlines()[0],
                   arithmetic_source_sha256=hashes, rows=rows, runtime_or_audio_timing_claim=False)
    (output / 'verification-private.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(status='PASS', rows=rows)))
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--avr-bin', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    run(arguments.avr_bin, arguments.output)
