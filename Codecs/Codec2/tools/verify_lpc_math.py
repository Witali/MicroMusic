#!/usr/bin/env python3
"""Qualify deterministic integer LPC boundary functions on ATmega64A."""
import argparse,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import verify_frontend as front
from audit_decoder_memory import device_memory
ROOT=front.ROOT
BUILD=ROOT.parents[1]/'build/codec2/lpc-math'
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--record',action='store_true');a=p.parse_args();BUILD.mkdir(parents=True,exist_ok=True)
    compat=json.loads((ROOT/'reports/lpc-math-compat.json').read_text())
    for name,h in compat['sources'].items():assert front.digest(ROOT/name)==h,name
    flags=['-DCODEC2_LPC_NATIVE_COMPAT=1'];includes=['-I'+str(ROOT/'src')];exe=BUILD/('vectors.exe' if os.name=='nt' else 'vectors')
    front.run(['clang','-O2','-fno-strict-aliasing','-ffp-contract=off','-D_CRT_SECURE_NO_WARNINGS','-DCODEC2_LPC_MATH_CHECKS=1',*flags,*includes,ROOT/'src/lpc_math.c',ROOT/'tests/lpc_math_vectors.c','-o',exe,*([] if os.name=='nt' else ['-lm'])]);front.run([exe,BUILD/'inputs.bin',BUILD/'expected.bin'])
    memory=device_memory('avr-gcc','atmega64a')
    front.run(['avr-gcc','-mmcu=atmega64a','-Os','-std=c99','-fno-strict-aliasing','-ffunction-sections','-fdata-sections','-DCODEC2_LPC_MATH_CHECKS=0',*flags,*includes,ROOT/'src/lpc_math.c',ROOT/'tests/avr_lpc_math.c','-Wl,--gc-sections','-Wl,--defsym=__DATA_REGION_ORIGIN__='+str(0x800000+memory['RAMSTART']),'-Wl,--defsym=__DATA_REGION_LENGTH__='+str(memory['RAMEND']-memory['RAMSTART']+1),'-Wl,--defsym=__TEXT_REGION_LENGTH__='+str(memory['FLASHEND']+1),'-o',BUILD/'kernel.elf'])
    front.run(['avr-objcopy','-O','binary',BUILD/'kernel.elf',BUILD/'kernel.bin'])
    with (BUILD/'symbols.txt').open('wb') as f:front.run(['avr-nm','-n',BUILD/'kernel.elf'],stdout=f)
    report={'compatibility_report_sha256':front.digest(ROOT/'reports/lpc-math-compat.json'),'defines':flags,'memory':memory,'binary_sha256':front.digest(BUILD/'kernel.bin'),'inputs_sha256':front.digest(BUILD/'inputs.bin'),'expected_sha256':front.digest(BUILD/'expected.bin')}
    front.dump(BUILD/'build.json',report);front.run(['node',ROOT/'tests/verify_lpc_math_avr.mjs']);report['execution']=json.loads((BUILD/'execution.json').read_text())
    names=['src/table_access.h','tests/lpc_math_vectors.c','tests/avr_lpc_math.c','tests/verify_lpc_math_avr.mjs','tools/verify_lpc_math.py']
    report['sources']={**compat['sources'],**{n:front.digest(ROOT/n) for n in names}};report['compiler']=front.run(['avr-gcc','--version'],capture_output=True,text=True).stdout.splitlines()[0]
    front.dump(ROOT/'reports/lpc-math-kernel.json' if a.record else BUILD/'verification.json',report)
if __name__=='__main__':main()
