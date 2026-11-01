#!/usr/bin/env python3
"""Build the five-value WB fold, matched identity controls and IRQ gates."""
import argparse
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
    p.add_argument('--spi-stream',type=Path,required=True)
    args=p.parse_args()
    build_wb.avr(args.avr_gcc,'asm',packet_bytes=10,enable_nb4=True,low_rates=7,
                 destination=ROOT/'build/noise-fold-final/wb395')
    for label,load in [('irq8',25600),('irq11',35200)]:
        subprocess.run([sys.executable,ROOT/'tools/build_wb_stream_test.py','--avr-gcc',args.avr_gcc,
            '--packet-bytes','10','--low-rates','7','--enable-nb4','--frame-load-cycles',str(load),
            '--out',ROOT/'build/noise-fold-final'/label],check=True)
    subprocess.run([sys.executable,ROOT/'tools/build_spi_player.py','--avr-gcc',args.avr_gcc,
        '--backend','asm','--wideband','--enable-nb4','--capture-pcm','--stream',args.spi_stream,
        '--out',ROOT/'build/noise-fold-final/spi'],check=True)
    subprocess.run([sys.executable,ROOT/'tests/build_low_api.py','--avr-gcc',args.avr_gcc,
                    '--out',ROOT/'build/noise-fold-final/api'],check=True)
    subprocess.run([sys.executable,ROOT/'tests/build_noise_cache.py','--avr-gcc',args.avr_gcc],check=True)
    for label,width,mask in [('nb215',6,7),('nb8',20,0),('nb11',28,0),('wb98',25,0),('wb128',32,0)]:
        for epoch,source in [('before',args.baseline_root),('after',ROOT)]:
            script=source/'tools'/('build_wb.py' if label.startswith('wb') else 'build.py')
            command=[sys.executable,script,'--avr-gcc',args.avr_gcc,'--backend','asm',
                     '--packet-bytes',str(width),'--low-rates',str(mask),
                     '--out',ROOT/'build/noise-fold-identities'/epoch/label]
            if label in ['nb11','nb215']:command.append('--enable-nb4')
            subprocess.run(command,check=True)
    for label in ['nb11','wb395']:
        command=[sys.executable,ROOT/'tools/build_spi_player.py','--avr-gcc',args.avr_gcc,
                 '--backend','c','--enable-nb4','--stream',args.spi_stream.parent.parent/label/'long.spxraw',
                 '--out',ROOT/'build/noise-fold-c'/label]
        if label=='wb395':command.append('--wideband')
        subprocess.run(command,check=True)
    print('Built exact five-value fold admission; C images compile/link only')


if __name__=='__main__':main()
