"""Compile one shared active-IRQ arithmetic probe for three real AVR25 backends."""
from pathlib import Path
import argparse
import subprocess

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[2]
def build(output):
    output=Path(output).resolve()
    if REPO/'build' not in output.parents:raise ValueError('Use ignored repository build storage')
    output.mkdir(parents=True,exist_ok=True)
    for name,flags in [('c',['-DLPX4_ENABLE_ASM=0']),('asm',['-DLPX4_ENABLE_ASM=1']),
                       ('generic',['-DLPX4_ENABLE_ASM=1','-DLPX4_ARCH=LPX4_ARCH_GENERIC'])]:
        stem=output/name
        subprocess.run(['avr-g++','-mmcu=attiny88','-DF_CPU=16000000UL','-Os','-std=gnu++11',
            '-ffunction-sections','-fdata-sections','-I'+str(REPO/'ATtiny88/Music/universal/vendor/ATtiny_DFP/3.4.278/include'),
            '-I'+str(ROOT/'src'),*flags,str(ROOT/'tests/avr25_math.cpp'),'-Wl,--gc-sections',
            '-Wl,--undefined=math_case','-o',str(stem.with_suffix('.elf'))],check=True,capture_output=True)
        subprocess.run(['avr-objcopy','-O','binary',str(stem.with_suffix('.elf')),str(stem.with_suffix('.bin'))],check=True)
        stem.with_suffix('.nm').write_bytes(subprocess.check_output(['avr-nm','-S',str(stem.with_suffix('.elf'))]))
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('output',type=Path)
    build(ap.parse_args().output)
