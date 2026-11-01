#!/usr/bin/env python3
"""Build matched pre/post gain-divider images and per-profile IRQ players."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import build_wb
PROFILES={'wb395':10,'wb575':15,'wb775':20,'wb98':25,'wb128':32}
LOADS={'wb395':25600,'wb575':9600,'wb775':9600,'wb98':25600,'wb128':25600}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--avr-gcc',required=True)
    p.add_argument('--baseline-root',type=Path,required=True,help='Unmodified codec root at 3a0462fb')
    p.add_argument('--spi-corpus',type=Path,required=True)
    args=p.parse_args()
    baseline=json.loads((ROOT/'reports/noise-cache-admission.json').read_text())
    for name,value in baseline['sourceSha256'].items():
        actual=hashlib.sha256((args.baseline_root/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
        assert actual==value,'Baseline source '+name
    for label,width in PROFILES.items():
        before=ROOT/'build/gain-before'/label
        subprocess.run([sys.executable,args.baseline_root/'tools/build_wb.py','--avr-gcc',args.avr_gcc,
            '--backend','asm','--packet-bytes',str(width),'--low-rates','7','--enable-nb4','--out',before],check=True)
        if label=='wb395':
            expected=json.loads((ROOT/'reports/noise-cache-wb395.json').read_text())['binarySha256']
            assert hashlib.sha256((before/'wb.bin').read_bytes()).hexdigest()==expected
        build_wb.avr(args.avr_gcc,'asm',packet_bytes=width,enable_nb4=True,low_rates=7,
                     destination=ROOT/'build/gain-after'/label)
        subprocess.run([sys.executable,ROOT/'tools/build_wb_stream_test.py','--avr-gcc',args.avr_gcc,
            '--packet-bytes',str(width),'--low-rates','7','--enable-nb4',
            '--frame-load-cycles',str(LOADS[label]),'--out',ROOT/'build/gain-irq'/label],check=True)
    for label in ['wb395','wb128']:
        subprocess.run([sys.executable,ROOT/'tools/build_spi_player.py','--avr-gcc',args.avr_gcc,
            '--backend','asm','--wideband','--enable-nb4','--stream',args.spi_corpus/label/'long.spxraw',
            '--capture-pcm','--out',ROOT/'build/gain-spi'/label],check=True)
    subprocess.run([sys.executable,ROOT/'tests/build_low_api.py','--avr-gcc',args.avr_gcc,
                    '--out',ROOT/'build/gain-api'],check=True)
    for label in ['wb395','nb11']:
        before_command=[sys.executable,args.baseline_root/'tools/build_spi_player.py',
            '--avr-gcc',args.avr_gcc,'--backend','c','--enable-nb4',
            '--stream',args.spi_corpus/label/'long.spxraw','--out',ROOT/'build/gain-c-before'/label]
        if label.startswith('wb'):before_command.append('--wideband')
        subprocess.run(before_command,check=True)
        command=[sys.executable,ROOT/'tools/build_spi_player.py','--avr-gcc',args.avr_gcc,
            '--backend','c','--enable-nb4','--stream',args.spi_corpus/label/'long.spxraw',
            '--out',ROOT/'build/gain-c'/label]
        if label.startswith('wb'):command.append('--wideband')
        subprocess.run(command,check=True)
    print('Built matched five-profile gain admission; C images compile/link only')


if __name__=='__main__':main()
