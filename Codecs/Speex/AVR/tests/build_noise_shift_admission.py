#!/usr/bin/env python3
"""Build NB1/WB3.95 exact noise-shift admission and unchanged disabled-mode controls."""
import argparse
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import build,build_wb


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--avr-gcc',required=True)
    p.add_argument('--baseline-root',type=Path,required=True)
    p.add_argument('--spi-stream',type=Path,required=True)
    args=p.parse_args()
    build.avr(args.avr_gcc,backend='asm',packet_bytes=6,enable_nb4=True,low_rates=7,
              destination=ROOT/'build/noise-shift-final/nb215')
    build_wb.avr(args.avr_gcc,'asm',packet_bytes=10,enable_nb4=True,low_rates=7,
                 destination=ROOT/'build/noise-shift-final/wb395')
    subprocess.run([sys.executable,ROOT/'tools/build_wb_stream_test.py','--avr-gcc',args.avr_gcc,
        '--packet-bytes','10','--low-rates','7','--enable-nb4','--frame-load-cycles','25600',
        '--out',ROOT/'build/noise-shift-final/irq'],check=True)
    subprocess.run([sys.executable,ROOT/'tools/build_spi_player.py','--avr-gcc',args.avr_gcc,
        '--backend','asm','--wideband','--enable-nb4','--capture-pcm','--stream',args.spi_stream,
        '--out',ROOT/'build/noise-shift-final/spi'],check=True)
    subprocess.run([sys.executable,ROOT/'tests/build_low_api.py','--avr-gcc',args.avr_gcc,
                    '--out',ROOT/'build/noise-shift-final/api'],check=True)
    for label,width in [('nb8',20),('nb11',28),('wb98',25),('wb128',32)]:
        for epoch,source in [('before',args.baseline_root),('after',ROOT)]:
            script=source/'tools'/('build_wb.py' if label.startswith('wb') else 'build.py')
            command=[sys.executable,script,'--avr-gcc',args.avr_gcc,'--backend','asm',
                     '--packet-bytes',str(width),'--out',ROOT/'build/noise-shift-disabled'/epoch/label]
            if label=='nb11':command.append('--enable-nb4')
            subprocess.run(command,check=True)
    for label in ['nb11','wb395']:
        stream=args.spi_stream.parent.parent/label/'long.spxraw'
        command=[sys.executable,ROOT/'tools/build_spi_player.py','--avr-gcc',args.avr_gcc,
                 '--backend','c','--enable-nb4','--stream',stream,'--out',ROOT/'build/noise-shift-c'/label]
        if label=='wb395':command.append('--wideband')
        subprocess.run(command,check=True)
    print('Built noise-shift admission; no C decoder execution')


if __name__=='__main__':main()
