#!/usr/bin/env python3
"""Build quartered NB1 excitation, IRQ/SPI gates and matched controls."""
import argparse
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import build,build_wb


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--avr-gcc',required=True)
    p.add_argument('--baseline-root',type=Path,required=True);p.add_argument('--spi-stream',type=Path,required=True)
    args=p.parse_args();out=ROOT/'build/nb1-refill-final'

    def run(script,*options):
        subprocess.run([sys.executable,ROOT/script,'--avr-gcc',args.avr_gcc,*map(str,options)],check=True)

    build_wb.avr(args.avr_gcc,'asm',packet_bytes=10,enable_nb4=True,low_rates=7,destination=out/'wb395')
    build.avr(args.avr_gcc,backend='asm',packet_bytes=6,enable_nb4=True,low_rates=7,destination=out/'nb215')
    for label,load in [('irq8',25600),('irq11',35200)]:
        run('tools/build_wb_stream_test.py','--packet-bytes',10,'--low-rates',7,'--enable-nb4',
            '--frame-load-cycles',load,'--out',out/label)
    run('tools/build_spi_player.py','--backend','asm','--wideband','--enable-nb4','--capture-pcm',
        '--stream',args.spi_stream,'--out',out/'spi')
    run('tests/build_low_api.py','--out',out/'api')
    for script in ['build_noise_cache.py','build_nb1_vocoder.py','build_low_mean.py']:
        run('tests/'+script)
    for label,width in [('nb8',20),('nb11',28),('wb98',25),('wb128',32)]:
        for epoch,source in [('before',args.baseline_root),('after',ROOT)]:
            script=source/'tools'/('build_wb.py' if label.startswith('wb') else 'build.py')
            command=[sys.executable,script,'--avr-gcc',args.avr_gcc,'--backend','asm',
                '--packet-bytes',str(width),'--low-rates','0','--out',ROOT/'build/nb1-refill-identities'/epoch/label]
            if label=='nb11':command.append('--enable-nb4')
            subprocess.run(command,check=True)
    for label in ['nb11','wb395']:
        options=['--backend','c','--enable-nb4','--stream',args.spi_stream.parent.parent/label/'long.spxraw',
            '--out',ROOT/'build/nb1-refill-c'/label]
        if label=='wb395':options.append('--wideband')
        run('tools/build_spi_player.py',*options)
    print('Built refill admission and compile/link-only C controls')


if __name__=='__main__':main()
