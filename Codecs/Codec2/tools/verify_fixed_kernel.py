#!/usr/bin/env python3
"""Compare fixed/native IFFT output and float/fixed cycles on the same AVR inputs."""
import argparse
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import verify_frontend as front
from audit_decoder_memory import device_memory
ROOT=front.ROOT
BUILD=ROOT.parents[1]/'build/codec2/fixed-kernel'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc',default='clang');parser.add_argument('--avr-gcc',default='avr-gcc');parser.add_argument('--node',default='node')
    parser.add_argument('--record',action='store_true');args=parser.parse_args()
    BUILD.mkdir(parents=True,exist_ok=True);source=front.VENDOR/'src'
    flags=['-DCODEC2_FIXED_BITS=16','-DCODEC2_FIXED_TWIDDLE_Q=9','-DCODEC2_FIXED_WIDE_LAST=0']
    program=BUILD/('vectors.exe' if os.name=='nt' else 'vectors')
    front.run([args.cc,'-O2','-fno-strict-aliasing','-ffp-contract=off','-D_CRT_SECURE_NO_WARNINGS','-DCODEC2_FIXED_CHECKS=1',*flags,
        '-I'+str(ROOT/'src'),'-I'+str(source),ROOT/'src/fixed_inverse.c',ROOT/'tests/fixed_kernel_vectors.c',
        source/'kiss_fft.c',source/'kiss_fftr.c','-o',program,*([] if os.name=='nt' else ['-lm'])])
    front.run([program,BUILD/'inputs.bin',BUILD/'fixed.expected.bin',BUILD/'float.expected.bin'])
    memory=device_memory(args.avr_gcc,'atmega64a')
    report={'memory':memory,'inputs_sha256':front.digest(BUILD/'inputs.bin'),'images':{},'precision':{'bits':16,'q':9,'wide_last':0}}
    prefix=args.avr_gcc[:-3] if args.avr_gcc.endswith('gcc') else args.avr_gcc.replace('gcc.exe','')
    for name in ['float','fixed']:
        front.run([args.avr_gcc,'-mmcu=atmega64a','-Os','-std=c99','-fno-strict-aliasing','-ffunction-sections','-fdata-sections',
            '-DCODEC2_FIXED_CHECKS=0','-DCODEC2_BENCH_FLOAT='+str(int(name=='float')),*flags,
            '-I'+str(ROOT/'src'),ROOT/('src/compact_fft.c' if name=='float' else 'src/fixed_inverse.c'),ROOT/'tests/avr_fixed_kernel.c',
            '-Wl,--gc-sections','-Wl,--defsym=__DATA_REGION_ORIGIN__='+str(0x800000+memory['RAMSTART']),
            '-Wl,--defsym=__DATA_REGION_LENGTH__='+str(memory['RAMEND']-memory['RAMSTART']+1),
            '-Wl,--defsym=__TEXT_REGION_LENGTH__='+str(memory['FLASHEND']+1),'-o',BUILD/(name+'.elf'),'-lm'])
        front.run([prefix+'objcopy','-O','binary',BUILD/(name+'.elf'),BUILD/(name+'.bin')])
        with (BUILD/(name+'.symbols')).open('wb') as f:front.run([prefix+'nm','-n',BUILD/(name+'.elf')],stdout=f)
        report['images'][name]={'binary_sha256':front.digest(BUILD/(name+'.bin')),'expected_sha256':front.digest(BUILD/(name+'.expected.bin'))}
    front.dump(BUILD/'build.json',report)
    front.run([args.node,ROOT/'tests/verify_fixed_kernel_avr.mjs'])
    report['execution']=json.loads((BUILD/'execution.json').read_text())
    names=['src/fixed_inverse.c','src/fixed_inverse.h','src/fixed_inverse_tables.inc','src/fixed_table_access.h','src/compact_fft.c',
           'src/compact_fft.h','src/compact_tables.inc','src/float_table_access.h','src/table_access.h',
           'tests/fixed_kernel_vectors.c','tests/avr_fixed_kernel.c','tests/verify_fixed_kernel_avr.mjs','tools/verify_fixed_kernel.py',
           'tools/generate_fixed_tables.py','vendor/codec2-1.2.0/UPSTREAM.json']
    report['sources']={n:front.digest(ROOT/n) for n in names}
    report['compiler']=front.run([args.avr_gcc,'--version'],capture_output=True,text=True).stdout.splitlines()[0]
    report['host_compiler']=front.run([args.cc,'--version'],capture_output=True,text=True).stdout.splitlines()[0]
    front.dump(ROOT/'reports/fixed-kernel.json' if args.record else BUILD/'verification.json',report)
if __name__=='__main__':main()
