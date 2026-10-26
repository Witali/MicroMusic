#!/usr/bin/env python3
"""Qualify the selected integer fifth-root scalar on AVR against native C."""
import argparse,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import verify_frontend as front
from audit_decoder_memory import device_memory
from generate_fifth_tables import generate
ROOT=front.ROOT
BUILD=ROOT.parents[1]/'build/codec2/fifth-kernel'
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cc',default='clang');p.add_argument('--avr-gcc',default='avr-gcc');p.add_argument('--node',default='node');p.add_argument('--record',action='store_true');a=p.parse_args()
    BUILD.mkdir(parents=True,exist_ok=True);config={'q':11,'table_bits':6};table=BUILD/'fixed_fifth_tables.inc';table.write_bytes(generate(config['q'],config['table_bits']))
    flags=['-DCODEC2_ROOT_Q=11','-DCODEC2_ROOT_TABLE_BITS=6'];includes=['-I'+str(BUILD),'-I'+str(ROOT/'src')]
    exe=BUILD/('vectors.exe' if os.name=='nt' else 'vectors')
    front.run([a.cc,'-O2','-fno-strict-aliasing','-ffp-contract=off','-D_CRT_SECURE_NO_WARNINGS',*flags,*includes,ROOT/'src/fixed_fifth.c',ROOT/'tests/fifth_vectors.c','-o',exe,*([] if os.name=='nt' else ['-lm'])])
    front.run([exe,BUILD/'inputs.bin',BUILD/'fixed.expected.bin',BUILD/'float.expected.bin'])
    memory=device_memory(a.avr_gcc,'atmega64a');report={'precision':config,'table_sha256':front.digest(table),'memory':memory,'inputs_sha256':front.digest(BUILD/'inputs.bin'),'images':{}}
    prefix=a.avr_gcc[:-3] if a.avr_gcc.endswith('gcc') else a.avr_gcc.replace('gcc.exe','')
    for name in ['float','fixed']:
        sources=[ROOT/'tests/avr_fifth.c']+([ROOT/'src/fixed_fifth.c'] if name=='fixed' else [])
        front.run([a.avr_gcc,'-mmcu=atmega64a','-Os','-std=c99','-fno-strict-aliasing','-ffunction-sections','-fdata-sections','-DCODEC2_BENCH_FLOAT='+str(int(name=='float')),*flags,*includes,*sources,
            '-Wl,--gc-sections','-Wl,--defsym=__DATA_REGION_ORIGIN__='+str(0x800000+memory['RAMSTART']),'-Wl,--defsym=__DATA_REGION_LENGTH__='+str(memory['RAMEND']-memory['RAMSTART']+1),'-Wl,--defsym=__TEXT_REGION_LENGTH__='+str(memory['FLASHEND']+1),'-o',BUILD/(name+'.elf'),'-lm'])
        front.run([prefix+'objcopy','-O','binary',BUILD/(name+'.elf'),BUILD/(name+'.bin')])
        with (BUILD/(name+'.symbols')).open('wb') as f:front.run([prefix+'nm','-n',BUILD/(name+'.elf')],stdout=f)
        report['images'][name]={'binary_sha256':front.digest(BUILD/(name+'.bin')),'expected_sha256':front.digest(BUILD/(name+'.expected.bin'))}
    front.dump(BUILD/'build.json',report);front.run([a.node,ROOT/'tests/verify_fifth_avr.mjs']);report['execution']=json.loads((BUILD/'execution.json').read_text())
    names=['src/fixed_fifth.c','src/fixed_fifth.h','src/fixed_table_access.h','src/table_access.h','tests/fifth_vectors.c','tests/avr_fifth.c','tests/verify_fifth_avr.mjs','tools/verify_fifth_kernel.py','tools/generate_fifth_tables.py']
    report['sources']={n:front.digest(ROOT/n) for n in names};report['compiler']=front.run([a.avr_gcc,'--version'],capture_output=True,text=True).stdout.splitlines()[0];report['host_compiler']=front.run([a.cc,'--version'],capture_output=True,text=True).stdout.splitlines()[0]
    front.dump(ROOT/'reports/fifth-kernel.json' if a.record else BUILD/'verification.json',report)
if __name__=='__main__':main()
