#!/usr/bin/env python3
"""Check all weighted-spectrum output bits on AVR against checked native C."""
import argparse,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import verify_frontend as front
from audit_decoder_memory import device_memory
ROOT=front.ROOT
BUILD=ROOT.parents[1]/'build/codec2/weight-kernel'

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cc',default='clang');p.add_argument('--avr-gcc',default='avr-gcc');p.add_argument('--node',default='node');p.add_argument('--record',action='store_true');a=p.parse_args()
    BUILD.mkdir(parents=True,exist_ok=True)
    flags=['-DCODEC2_WEIGHT_BITS=24','-DCODEC2_WEIGHT_TWIDDLE_Q=22','-DCODEC2_WEIGHT_DIRECT_PAIR=1','-DCODEC2_WEIGHT_SPLIT24=0','-DCODEC2_WEIGHT_ROUND_LEGACY=0','-DCODEC2_WEIGHT_AVR_INT24=0']
    includes=['-I'+str(ROOT/'include'),'-I'+str(ROOT/'src')];exe=BUILD/('vectors.exe' if os.name=='nt' else 'vectors')
    front.run([a.cc,'-O2','-fno-strict-aliasing','-ffp-contract=off','-D_CRT_SECURE_NO_WARNINGS','-DCODEC2_WEIGHT_CHECKS=1',*flags,*includes,ROOT/'src/fixed_weight.c',ROOT/'tests/weight_vectors.c','-o',exe,*([] if os.name=='nt' else ['-lm'])])
    front.run([exe,BUILD/'inputs.bin',BUILD/'expected.bin'])
    memory=device_memory(a.avr_gcc,'atmega64a');prefix=a.avr_gcc[:-3] if a.avr_gcc.endswith('gcc') else a.avr_gcc.replace('gcc.exe','')
    front.run([a.avr_gcc,'-mmcu=atmega64a','-Os','-std=c99','-fno-strict-aliasing','-ffunction-sections','-fdata-sections','-DCODEC2_WEIGHT_CHECKS=0',*flags,*includes,ROOT/'src/fixed_weight.c',ROOT/'tests/avr_weight.c',
        '-Wl,--gc-sections','-Wl,--defsym=__DATA_REGION_ORIGIN__='+str(0x800000+memory['RAMSTART']),'-Wl,--defsym=__DATA_REGION_LENGTH__='+str(memory['RAMEND']-memory['RAMSTART']+1),'-Wl,--defsym=__TEXT_REGION_LENGTH__='+str(memory['FLASHEND']+1),'-o',BUILD/'kernel.elf','-lm'])
    front.run([prefix+'objcopy','-O','binary',BUILD/'kernel.elf',BUILD/'kernel.bin'])
    with (BUILD/'symbols.txt').open('wb') as f:front.run([prefix+'nm','-n',BUILD/'kernel.elf'],stdout=f)
    report={'precision':{'component_bits':24,'twiddle_q':22,'direct_pair':True},'defines':flags,'memory':memory,'inputs_sha256':front.digest(BUILD/'inputs.bin'),'expected_sha256':front.digest(BUILD/'expected.bin'),'binary_sha256':front.digest(BUILD/'kernel.bin')}
    front.dump(BUILD/'build.json',report);front.run([a.node,ROOT/'tests/verify_weight_avr.mjs']);report['execution']=json.loads((BUILD/'execution.json').read_text())
    names=['src/fixed_weight.c','src/fixed_weight.h','src/fixed_weight_tables.inc','src/weight_round.h','src/spectral_table_access.h','src/table_access.h','tests/weight_vectors.c','tests/avr_weight.c','tests/verify_weight_avr.mjs','tools/verify_weight_kernel.py','tools/audit_decoder_memory.py']
    report['sources']={n:front.digest(ROOT/n) for n in names};report['compiler']=front.run([a.avr_gcc,'--version'],capture_output=True,text=True).stdout.splitlines()[0];report['host_compiler']=front.run([a.cc,'--version'],capture_output=True,text=True).stdout.splitlines()[0]
    front.dump(ROOT/'reports/weight-kernel.json' if a.record else BUILD/'verification.json',report)
if __name__=='__main__':main()
