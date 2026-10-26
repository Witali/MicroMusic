#!/usr/bin/env python3
"""Check all integer main-spectrum output bytes on real AVR instructions."""
import argparse,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import verify_frontend as front
from audit_decoder_memory import device_memory
ROOT=front.ROOT
BUILD=ROOT.parents[1]/'build/codec2/adaptive-kernel'

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cc',default='clang');p.add_argument('--avr-gcc',default='avr-gcc');p.add_argument('--node',default='node');p.add_argument('--record',action='store_true');a=p.parse_args()
    study=json.loads((ROOT/'reports/adaptive-precision.json').read_text())
    for name,wanted in study['sources'].items():assert front.digest(ROOT/name)==wanted,name
    config=study['selection'];BUILD.mkdir(parents=True,exist_ok=True)
    flags=['-DCODEC2_FAITHFUL_BITS='+str(config['faithful_bits']),'-DCODEC2_ANALYSIS_BITS='+str(config['component_bits']),'-DCODEC2_ANALYSIS_TWIDDLE_Q='+str(config['twiddle_q']),'-DCODEC2_ANALYSIS_DIRECT_PAIR=1','-DCODEC2_ANALYSIS_GUARD_BITS='+str(config['guard_bits'])];includes=['-I'+str(ROOT/'include'),'-I'+str(ROOT/'src')];exe=BUILD/('vectors.exe' if os.name=='nt' else 'vectors')
    front.run([a.cc,'-O2','-fno-strict-aliasing','-ffp-contract=off','-D_CRT_SECURE_NO_WARNINGS','-DCODEC2_ANALYSIS_CHECKS=1',*flags,*includes,ROOT/'src/adaptive_analysis.c',ROOT/'src/fast_analysis.c',ROOT/'tests/analysis_vectors.c','-o',exe,*([] if os.name=='nt' else ['-lm'])]);front.run([exe,BUILD/'inputs.bin',BUILD/'expected.bin'])
    memory=device_memory(a.avr_gcc,'atmega64a');prefix=a.avr_gcc[:-3] if a.avr_gcc.endswith('gcc') else a.avr_gcc.replace('gcc.exe','')
    front.run([a.avr_gcc,'-mmcu=atmega64a','-Os','-std=c99','-fno-strict-aliasing','-ffunction-sections','-fdata-sections','-DCODEC2_ANALYSIS_CHECKS=0',*flags,*includes,ROOT/'src/adaptive_analysis.c',ROOT/'src/fast_analysis.c',ROOT/'tests/avr_analysis.c','-Wl,--gc-sections','-Wl,--defsym=__DATA_REGION_ORIGIN__='+str(0x800000+memory['RAMSTART']),'-Wl,--defsym=__DATA_REGION_LENGTH__='+str(memory['RAMEND']-memory['RAMSTART']+1),'-Wl,--defsym=__TEXT_REGION_LENGTH__='+str(memory['FLASHEND']+1),'-o',BUILD/'kernel.elf','-lm'])
    front.run([prefix+'objcopy','-O','binary',BUILD/'kernel.elf',BUILD/'kernel.bin'])
    with (BUILD/'symbols.txt').open('wb') as f:front.run([prefix+'nm','-n',BUILD/'kernel.elf'],stdout=f)
    report={'precision':study['selection'],'precision_study_sha256':front.digest(ROOT/'reports/adaptive-precision.json'),'defines':flags,'memory':memory,'inputs_sha256':front.digest(BUILD/'inputs.bin'),'expected_sha256':front.digest(BUILD/'expected.bin'),'binary_sha256':front.digest(BUILD/'kernel.bin')}
    front.dump(BUILD/'build.json',report);front.run([a.node,ROOT/'tests/verify_adaptive_kernel_avr.mjs']);report['execution']=json.loads((BUILD/'execution.json').read_text())
    names=['src/faithful_analysis.c','src/fixed_analysis.h','src/compact_fft.h','src/compact_tables.inc','src/analysis_table_access.h','src/table_access.h','tests/analysis_vectors.c','tests/avr_analysis.c','tests/verify_adaptive_kernel_avr.mjs','tools/verify_adaptive_kernel.py','tools/audit_decoder_memory.py']
    report['sources']={**study['sources'],**{n:front.digest(ROOT/n) for n in names}};report['compiler']=front.run([a.avr_gcc,'--version'],capture_output=True,text=True).stdout.splitlines()[0];report['host_compiler']=front.run([a.cc,'--version'],capture_output=True,text=True).stdout.splitlines()[0]
    front.dump(ROOT/'reports/adaptive-kernel.json' if a.record else BUILD/'verification.json',report)
if __name__=='__main__':main()
