#!/usr/bin/env python3
"""Regenerate music and assemble ATtiny13A image; ELF/HEX built locally.

Requires Python 3 and either GNU AVR binutils/GCC or Clang AVR integrated
assembler plus llvm-objcopy and readelf. The fallback resolves the only AVR
relocation classes in this particular single-section firmware (LO8/HI8 LDI).
It is intentionally NOT a general-purpose AVR linker.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def call(*args):
    subprocess.run(args, cwd=ROOT, check=True)


def make_hex(raw):
    out = []
    for a in range(0, len(raw), 16):
        data = bytes(raw[a:a+16]); rec = bytes([len(data), (a >> 8) & 255, a & 255, 0]) + data
        out.append(':' + (rec + bytes([-sum(rec) & 255])).hex().upper())
    out.append(':00000001FF')
    return '\n'.join(out) + '\n'


def assemble_llvm():
    if not all(shutil.which(x) for x in ('clang', 'llvm-objcopy', 'readelf')):
        raise RuntimeError('Install GNU AVR GCC/binutils or LLVM clang/llvm-objcopy + readelf')
    call('clang', '-target', 'avr', '-mmcu=attiny13a', '-x', 'assembler-with-cpp', '-c',
         '-I.', 'synth.S', '-o', 'synth.o')
    call('llvm-objcopy', '-O', 'binary', '-j', '.text', 'synth.o', 'synth.bin.tmp')
    b = bytearray((ROOT/'synth.bin.tmp').read_bytes())
    text = subprocess.check_output(['readelf', '-r', str(ROOT/'synth.o')], text=True)
    matches = list(re.finditer(
        r'^([0-9a-fA-F]{8})\s+[0-9a-fA-F]+\s+R_AVR_(LO8|HI8)_LDI\s+[0-9a-fA-F]+\s+\.text\s+\+\s+([0-9a-fA-F]+)\s*$',
        text, re.MULTILINE))
    reloc_count = len(re.findall(r'R_AVR_', text))
    if reloc_count != len(matches):
        raise RuntimeError(f'Unsupported AVR relocations ({reloc_count} vs {len(matches)}). Refusing HEX.')
    for m in matches:
        offset = int(m[1], 16)
        target = int(m[3], 16)     # absolute byte address, .text linked at 0
        value = target & 255 if m[2] == 'LO8' else (target >> 8) & 255
        word = b[offset] | (b[offset+1] << 8)
        if word & 0xf000 != 0xe000:
            raise RuntimeError(f'LDI relocation points to non-LDI at 0x{offset:x}')
        word = (word & 0xf0f0) | ((value & 0xf0) << 4) | (value & 0x0f)
        b[offset], b[offset+1] = word & 255, word >> 8
    (ROOT/'synth.bin.tmp').unlink()
    return b, 'Clang AVR IAS + single-section relocation fixups'


def assemble_gnu():
    # Compiler driver links & resolves all relocations. No C runtime.
    call('avr-gcc', '-mmcu=attiny13a', '-nostdlib', '-nostartfiles',
         '-Wl,-Ttext=0', '-x', 'assembler-with-cpp', '-I.',
         'synth.S', '-o', 'synth.elf')
    call('avr-objcopy', '-O', 'binary', '-j', '.text', 'synth.elf', 'synth.bin')
    return bytearray((ROOT/'synth.bin').read_bytes()), 'GNU AVR assembler + linker'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--lead',choices=['violin','flute'],default='violin')
    p.add_argument('--keys',choices=['piano','organ'],default='piano')
    p.add_argument('--pluck',choices=['guitar','bass'],default='guitar')
    p.add_argument('--drums',choices=['off','hat','snare'],default='snare')
    args=p.parse_args()
    call(sys.executable, 'generate.py', 'score.json', '--lead', args.lead,
         '--keys', args.keys, '--pluck', args.pluck, '--drums', args.drums)
    b,assembler = assemble_gnu() if shutil.which('avr-gcc') and shutil.which('avr-objcopy') else assemble_llvm()
    if len(b) > 1024: raise RuntimeError(f'ATtiny13A Flash overflow: {len(b)} bytes (limit 1024)')
    (ROOT/'synth.bin').write_bytes(b)
    (ROOT/'synth.hex').write_text(make_hex(b))
    # Resolve debug symbol locations from the object instead of assuming
    # hard-coded PCs (which change as synthesis algorithms are improved).
    obj = ROOT/('synth.elf' if (ROOT/'synth.elf').exists() and assembler.startswith('GNU') else 'synth.o')
    symtext = subprocess.check_output(['readelf','-s',str(obj)],text=True)
    syms = {}
    for line in symtext.splitlines():
        parts=line.split()
        if len(parts)>=8 and parts[-1] in ('read_event','audio_irq','render_sample'):
            syms[parts[-1]]=int(parts[1],16)
    if 'read_event' not in syms: raise RuntimeError('Assembler symbol read_event missing')
    (ROOT/'symbols.json').write_text(json.dumps(syms,indent=2)+'\n')
    print(f'{assembler}\nFlash: {len(b)}/1024 bytes ({len(b)/1024:.1%}), remaining {1024-len(b)} bytes')
    template=(ROOT/'player_template.html').read_text()
    html=template.replace('/*AVR_CORE*/',(ROOT/'avr_core.js').read_text()).replace('/*FIRMWARE_HEX*/',(ROOT/'synth.hex').read_text())
    (ROOT/'player.html').write_text(html)
    print('Output: synth.hex synth.bin player.html')


if __name__ == '__main__':main()
