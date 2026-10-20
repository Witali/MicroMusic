#!/usr/bin/env python3
"""Rebuild ATtiny13A Flash and EEPROM, verify timings and generate standalone player.

Uses GNU avr-gcc/avr-objcopy if present, otherwise LLVM clang/llvm-objcopy.
For LLVM only: relocations for LO8/HI8 to symbols inside this single .text
section are resolved here (build fails closed if a new class appears).
"""
from pathlib import Path
import hashlib, json, re, shutil, subprocess, sys

ROOT=Path(__file__).resolve().parent

def run(*args):
    return subprocess.run(args,cwd=ROOT,check=True)

def ihex(data):
    o=[]
    for i in range(0,len(data),16):
        v=bytes([len(data[i:i+16]),i>>8,i&255,0])+data[i:i+16]
        o.append(':'+(v+bytes([(-sum(v))&255])).hex().upper())
    return '\n'.join(o+[':00000001FF',''])

def assemble_clang():
    if not all(shutil.which(t) for t in ('clang','llvm-objcopy','readelf')):
        raise RuntimeError('Requires GNU AVR GCC/objcopy or clang + llvm-objcopy + readelf')
    run('clang','-target','avr','-mmcu=attiny13a','-x','assembler-with-cpp','-c','-I.', 'synth.S','-o','synth.o')
    run('llvm-objcopy','-O','binary','-j','.text','synth.o','synth.raw')
    raw=bytearray((ROOT/'synth.raw').read_bytes())
    relocs=subprocess.check_output(['readelf','-r',str(ROOT/'synth.o')],text=True)
    matches=list(re.finditer(r'^([0-9a-fA-F]{8})\s+[0-9a-fA-F]+\s+R_AVR_(LO8|HI8)_LDI\s+[0-9a-fA-F]+\s+\.text\s+\+\s+([0-9a-fA-F]+)\s*$',relocs,re.M))
    count=relocs.count('R_AVR_')
    if len(matches)!=count: raise RuntimeError(f'Unsupported relocations: {relocs}')
    for m in matches:
        at=int(m[1],16);target=int(m[3],16)
        val=target&255 if m[2]=='LO8' else (target>>8)&255
        w=raw[at]|raw[at+1]<<8
        if w&0xf000!=0xe000:raise RuntimeError(f'Bad LDI relocation at {at:x}')
        w=(w&0xf0f0)|((val&0xf0)<<4)|(val&15)
        raw[at]=w&255;raw[at+1]=w>>8
    (ROOT/'synth.raw').unlink()
    return bytes(raw),'LLVM AVR integrated assembler'

def assemble_gnu():
    run('avr-gcc','-mmcu=attiny13a','-nostdlib','-nostartfiles','-Wl,-Ttext=0','-x','assembler-with-cpp','-I.','synth.S','-o','synth.elf')
    run('avr-objcopy','-O','binary','-j','.text','synth.elf','synth.bin')
    return (ROOT/'synth.bin').read_bytes(),'GNU AVR assembler'

def write_eeprom():
    waves=json.loads((ROOT/'waveforms.json').read_text())
    if len(waves)!=8:raise RuntimeError('Exactly eight 8-byte waveforms required')
    allbytes=[]
    for name,values in waves.items():
        if len(values)!=16 or min(values)<-8 or max(values)>7 or sum(values)!=0:
            raise RuntimeError(f'{name}: requires 16 signed 4-bit samples with zero DC')
        for i in range(0,16,2): allbytes.append(((values[i]+8)<<4)|(values[i+1]+8))
    raw=bytes(allbytes)
    if len(raw)!=64:raise RuntimeError('EEPROM budget exceeded')
    (ROOT/'eeprom.bin').write_bytes(raw)
    (ROOT/'eeprom.hex').write_text(ihex(raw))
    return raw

def main():
    run(sys.executable,'score_compiler.py','score.json','-o','score.inc')
    rom,tool=assemble_gnu() if shutil.which('avr-gcc') and shutil.which('avr-objcopy') else assemble_clang()
    if len(rom)%2:rom+=b'\xff'  # AVR flash is word-addressed; pad odd score data
    if len(rom)>1024:raise RuntimeError(f'Flash over budget: {len(rom)} > 1024 bytes')
    ep=write_eeprom()
    (ROOT/'synth.bin').write_bytes(rom)
    (ROOT/'synth.hex').write_text(ihex(rom))
    core=(ROOT/'avr_core.js').read_text()
    template=(ROOT/'player_template.html').read_text()
    html=template.replace('/*AVR_CORE*/',core).replace('/*FIRMWARE_HEX*/',ihex(rom)).replace('/*EEPROM_HEX*/',ihex(ep))
    if '/*AVR_CORE*/' in html or '/*FIRMWARE_HEX*/' in html or '/*EEPROM_HEX*/' in html:raise RuntimeError('Unfilled HTML template placeholder')
    (ROOT/'player.html').write_text(html)
    info={'flash_bytes':len(rom),'eeprom_bytes':len(ep),'flash_sha256':hashlib.sha256(rom).hexdigest(),
          'eeprom_sha256':hashlib.sha256(ep).hexdigest(),'toolchain':tool,'source':'score.json'}
    (ROOT/'build-report.json').write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n')
    print(f'{tool} | Flash {len(rom)}/1024 | EEPROM {len(ep)}/64 | {info["flash_sha256"]}')

if __name__=='__main__':main()
