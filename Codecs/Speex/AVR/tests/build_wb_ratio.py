#!/usr/bin/env python3
"""Build isolated LPC-response ratio C/ASM fixtures; no C decoder runtime."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def source_sha(path):
    return hashlib.sha256(path.read_text(encoding='utf-8').replace('\r\n','\n').encode('utf-8')).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--avr-gcc',required=True)
    parser.add_argument('--out',type=Path,default=ROOT/'build/wb-ratio-unit')
    args=parser.parse_args()
    compiler=Path(shutil.which(args.avr_gcc) or args.avr_gcc).resolve()
    prefix=str(compiler.with_name('avr-'))
    ext='.exe' if compiler.suffix.lower()=='.exe' else ''
    version=subprocess.check_output([compiler,'--version'],text=True).splitlines()[0]
    compiler_root=compiler.parents[1]
    headers=next((p for p in [compiler_root/'avr/include/avr',compiler_root/'lib/avr/include/avr']
        if (p/'io.h').is_file()),None)
    if headers is None:raise FileNotFoundError('Cannot locate the pinned AVR device headers')
    device_headers={name:hashlib.sha256((headers/name).read_bytes()).hexdigest()
        for name in ['io.h','iom328p.h','interrupt.h']}
    tools={'compiler':compiler,**{name:Path(prefix+name+ext) for name in ['nm','objcopy','objdump']}}
    for name in ['cc1','as','ld','collect2','lto1','lto-wrapper']:
        path=Path(subprocess.check_output([compiler,'-print-prog-name='+name],text=True).strip())
        if path.is_file():tools[name]=path
    tool_hashes={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in tools.items()}
    for backend in ['asm','c','generic']:
        out=args.out/backend;out.mkdir(parents=True,exist_ok=True)
        options=['-std=c11','-Werror=implicit-function-declaration','-Os','-flto',
            '-fwrapv','-fno-strict-aliasing','-mmcu=atmega328p','-mcall-prologues','-mrelax',
            '-DSPEEX_NB3_ENABLE_ASM='+str(int(backend!='c'))]
        if backend=='generic':options+=['-DSPEEX_NB3_ARCH=SPEEX_NB3_ARCH_GENERIC']
        subprocess.run([compiler,*options,'-I'+str(ROOT/'src'),
            ROOT/'tests/avr_wb_ratio.c',ROOT/'src/wb_gain_div.S','-o',out/'unit.elf'],check=True)
        subprocess.run([prefix+'objcopy'+ext,'-O','binary','-R','.eeprom',out/'unit.elf',out/'unit.bin'],check=True)
        (out/'symbols.txt').write_text(subprocess.check_output([prefix+'nm'+ext,'-n',out/'unit.elf'],text=True),encoding='utf-8')
        (out/'disassembly.txt').write_text(subprocess.check_output([prefix+'objdump'+ext,'-d',out/'unit.elf'],text=True),encoding='utf-8')
        (out/'input.json').write_text(json.dumps(dict(backend=backend,compiler=version,options=options,
            deviceHeadersSha256=device_headers,
            toolSha256=tool_hashes,
            binarySha256=hashlib.sha256((out/'unit.bin').read_bytes()).hexdigest(),
            sourceHashMode='UTF-8 text normalized to LF',
            sourceSha256={str(p.relative_to(ROOT)).replace('\\','/'):source_sha(p)
                for p in [ROOT/'src/wb_gain_div.h',ROOT/'src/wb_gain_div.S',ROOT/'tests/avr_wb_ratio.c']},
            scope='Isolated C/ASM scalar primitive; full C decoder is not executed or timed'),indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
