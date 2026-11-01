#!/usr/bin/env python3
"""Build real-ABI old/new ASM and explicit C scalar noise-table paths."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import build_wb


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--avr-gcc',required=True)
    p.add_argument('--baseline-root',type=Path,required=True)
    args=p.parse_args()
    data=(args.baseline_root/'src/lowrate_noise.c').read_bytes().replace(b'\r\n',b'\n')
    admission=json.loads((ROOT/'reports/mean-product-admission.json').read_text())
    assert hashlib.sha256(data).hexdigest()==admission['sourceSha256']['src/lowrate_noise.c']
    source=build_wb.prepare();out=ROOT/'build/noise-values-unit';out.mkdir(parents=True,exist_ok=True)
    options=['-mmcu=atmega328p','-Os','-flto','-mcall-prologues','-mrelax','-ffunction-sections','-fdata-sections']
    objects=[]
    for label,backend,root,suffix in [('asm','asm',ROOT,None),('c','c',ROOT,'c'),
                                    ('before','asm',args.baseline_root,'before')]:
        obj=out/(label+'.o');flags=build_wb.flags(source,backend,True,7)
        if suffix:
            flags+=['-Dspeex_low_noise_'+name+'=noise_'+name+'_'+suffix
                    for name in ['values5','indices40','cached40']]
        subprocess.run([args.avr_gcc,*flags,*options,'-c',root/'src/lowrate_noise.c','-o',obj],check=True)
        objects.append(obj)
    subprocess.run([args.avr_gcc,*build_wb.flags(source,'asm',True,7),*options,
        ROOT/'tests/avr_noise_values.c',*objects,ROOT/'src/q14.S',
        '-Wl,--gc-sections','-o',out/'unit.elf'],check=True)
    prefix=str(Path(args.avr_gcc).with_name('avr-'));ext='.exe' if args.avr_gcc.endswith('.exe') else ''
    subprocess.run([prefix+'objcopy'+ext,'-O','binary',out/'unit.elf',out/'unit.bin'],check=True)
    (out/'symbols.txt').write_text(subprocess.check_output([prefix+'nm'+ext,'-n',out/'unit.elf'],text=True))
    (out/'input.json').write_bytes((json.dumps(dict(binarySha256=hashlib.sha256((out/'unit.bin').read_bytes()).hexdigest(),
        baselineNoiseSourceSha256=hashlib.sha256(data).hexdigest(),scope='Isolated scalar paths only'),indent=2)+'\n').encode())


if __name__=='__main__':main()
