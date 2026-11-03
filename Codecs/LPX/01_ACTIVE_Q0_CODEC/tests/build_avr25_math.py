"""Compile one shared active-IRQ arithmetic probe for three real AVR25 backends."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[2]
MUL16_UNROLLS=(1,2,4,8,16)

def build(output,mul16_unroll=16,saturated_products=False):
    if mul16_unroll not in MUL16_UNROLLS:raise ValueError('Invalid AVR25 multiply unroll factor')
    output=Path(output).resolve()
    if REPO/'build' not in output.parents:raise ValueError('Use ignored repository build storage')
    output.mkdir(parents=True,exist_ok=True)
    metadata={'target':'attiny88','clock_hz':16000000,'mul16_unroll':mul16_unroll,'saturated_products':saturated_products,'backends':{}}
    for name,flags in [('c',['-DLPX4_ENABLE_ASM=0']),('asm',['-DLPX4_ENABLE_ASM=1']),
                       ('generic',['-DLPX4_ENABLE_ASM=1','-DLPX4_ARCH=LPX4_ARCH_GENERIC'])]:
        stem=output/name
        flags=[*flags,f'-DLPX4_AVR25_MUL16_UNROLL={mul16_unroll}',f'-DLPX4_AVR25_SATURATED_PRODUCTS={int(saturated_products)}']
        subprocess.run(['avr-g++','-mmcu=attiny88','-DF_CPU=16000000UL','-Os','-std=gnu++11',
            '-ffunction-sections','-fdata-sections','-I'+str(REPO/'ATtiny88/Music/universal/vendor/ATtiny_DFP/3.4.278/include'),
            '-I'+str(ROOT/'src'),*flags,str(ROOT/'tests/avr25_math.cpp'),'-Wl,--gc-sections',
            '-Wl,--undefined=math_case','-o',str(stem.with_suffix('.elf'))],check=True,capture_output=True)
        subprocess.run(['avr-objcopy','-O','binary',str(stem.with_suffix('.elf')),str(stem.with_suffix('.bin'))],check=True)
        stem.with_suffix('.nm').write_bytes(subprocess.check_output(['avr-nm','-S',str(stem.with_suffix('.elf'))]))
        binary=stem.with_suffix('.bin').read_bytes()
        metadata['backends'][name]={'defines':flags,'binary_bytes':len(binary),
            'binary_sha256':hashlib.sha256(binary).hexdigest()}
    (output/'build.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf8')
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('output',type=Path)
    ap.add_argument('--mul16-unroll',type=int,choices=MUL16_UNROLLS,default=16,
                    help='AVR25 signed16 multiply rounds per loop group (default: 16)')
    ap.add_argument('--saturated-products',action='store_true')
    args=ap.parse_args();build(args.output,args.mul16_unroll,args.saturated_products)
