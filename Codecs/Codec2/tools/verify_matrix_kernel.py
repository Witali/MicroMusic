#!/usr/bin/env python3
"""Compare shared matrix FFT to the frozen radix C graph on native and AVR."""
import argparse,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import verify_frontend as front
from audit_decoder_memory import device_memory
ROOT=front.ROOT
BUILD=ROOT.parents[1]/'build/codec2/matrix-kernel'
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--record',action='store_true');a=p.parse_args();study=json.loads((ROOT/'reports/matrix-precision.json').read_text())
    for name,h in study['sources'].items():assert front.digest(ROOT/name)==h,name
    config=study['selection'];assert config['graph']=='radix256';BUILD.mkdir(parents=True,exist_ok=True)
    paired=json.loads((ROOT/'reports/sums32-kernels.json').read_text());paired_execution=next(x for x in paired['execution']['results'] if x['name']=='adaptive')
    memory=device_memory('avr-gcc','atmega64a');suffix='.exe' if os.name=='nt' else '';includes=['-I'+str(ROOT/'include'),'-I'+str(ROOT/'src')];images={}
    common_flags=['-DCODEC2_WEIGHT_BITS=24','-DCODEC2_WEIGHT_TWIDDLE_Q=22','-DCODEC2_WEIGHT_DIRECT_PAIR=1','-DCODEC2_WEIGHT_SPLIT24=0','-DCODEC2_WEIGHT_AVR_INT24=0','-DCODEC2_WEIGHT_ROUND_LEGACY=0','-DCODEC2_ANALYSIS_BITS=32','-DCODEC2_ANALYSIS_TWIDDLE_Q=30','-DCODEC2_ANALYSIS_DIRECT_PAIR=0','-DCODEC2_ANALYSIS_GUARD_BITS='+str(config['guard_bits']),'-DCODEC2_FAITHFUL_BITS=40']
    for name,sources,raw,comparison in [
        ('matrix-reference',['src/fixed_analysis.c'],True,None),('matrix',['src/matrix_analysis.c'],True,'matrix-reference'),
        ('adaptive-reference',['src/adaptive_analysis.c','src/fast_analysis.c'],False,None),('adaptive',['src/adaptive_analysis.c','src/matrix_analysis.c'],False,'adaptive-reference')]:
        folder=BUILD/name;folder.mkdir(exist_ok=True);flags=common_flags+(['-Dcodec2_analysis_forward=codec2_analysis_fast_forward'] if raw else [])
        program=folder/('vectors'+suffix)
        front.run(['clang','-O2','-fno-strict-aliasing','-ffp-contract=off','-D_CRT_SECURE_NO_WARNINGS','-DCODEC2_ANALYSIS_CHECKS=1','-DCODEC2_WEIGHT_CHECKS=1',*flags,*includes,*[ROOT/x for x in sources],ROOT/'tests/analysis_vectors.c','-o',program,*([] if os.name=='nt' else ['-lm'])]);front.run([program,folder/'inputs.bin',folder/'expected.bin'])
        if comparison:
            other=BUILD/comparison;assert (folder/'inputs.bin').read_bytes()==(other/'inputs.bin').read_bytes();assert (folder/'expected.bin').read_bytes()==(other/'expected.bin').read_bytes()
        front.run(['avr-gcc','-mmcu=atmega64a','-Os','-std=c99','-fno-strict-aliasing','-ffunction-sections','-fdata-sections','-DCODEC2_ANALYSIS_CHECKS=0','-DCODEC2_WEIGHT_CHECKS=0',*flags,*includes,*[ROOT/x for x in sources],ROOT/'tests/avr_analysis.c','-Wl,--gc-sections','-Wl,--defsym=__DATA_REGION_ORIGIN__='+str(0x800000+memory['RAMSTART']),'-Wl,--defsym=__DATA_REGION_LENGTH__='+str(memory['RAMEND']-memory['RAMSTART']+1),'-Wl,--defsym=__TEXT_REGION_LENGTH__='+str(memory['FLASHEND']+1),'-o',folder/'kernel.elf','-lm'])
        front.run(['avr-objcopy','-O','binary',folder/'kernel.elf',folder/'kernel.bin'])
        with (folder/'symbols.txt').open('wb') as f:front.run(['avr-nm','-n',folder/'kernel.elf'],stdout=f)
        images[name]={'prefix':'codec2_analysis','comparison':comparison,'paired_comparison':paired_execution if name=='adaptive' else None,'vectors':64,'output_bytes':2056,'binary_sha256':front.digest(folder/'kernel.bin'),'inputs_sha256':front.digest(folder/'inputs.bin'),'expected_sha256':front.digest(folder/'expected.bin')}
    report={'precision':config,'precision_study_sha256':front.digest(ROOT/'reports/matrix-precision.json'),'memory':memory,'defines':common_flags,'images':images,'compiler':front.run(['avr-gcc','--version'],capture_output=True,text=True).stdout.splitlines()[0]};front.dump(BUILD/'build.json',report)
    front.run(['node',ROOT/'tests/verify_matrix_kernel_avr.mjs']);report['execution']=json.loads((BUILD/'execution.json').read_text())
    names=['tests/analysis_vectors.c','tests/avr_analysis.c','tests/verify_matrix_kernel_avr.mjs','tools/verify_matrix_kernel.py']
    report['sources']={**study['sources'],**{n:front.digest(ROOT/n) for n in names}}
    front.dump(ROOT/'reports/matrix-kernel.json' if a.record else BUILD/'verification.json',report)
if __name__=='__main__':main()
