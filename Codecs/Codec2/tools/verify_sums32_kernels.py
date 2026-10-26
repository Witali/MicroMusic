#!/usr/bin/env python3
"""Compare narrow sums to frozen native C and measure both kernels on AVR."""
import argparse,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import verify_frontend as front
from audit_decoder_memory import device_memory
ROOT=front.ROOT
BUILD=ROOT.parents[1]/'build/codec2/sums32-kernels'

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--record',action='store_true');a=p.parse_args();BUILD.mkdir(parents=True,exist_ok=True)
    baseline=json.loads((ROOT/'reports/canonical-decoder.json').read_text())
    for name,h in baseline['sources'].items():assert front.digest(ROOT/name)==h,name
    flags=['-DCODEC2_WEIGHT_BITS=24','-DCODEC2_WEIGHT_TWIDDLE_Q=22','-DCODEC2_WEIGHT_DIRECT_PAIR=1','-DCODEC2_WEIGHT_SPLIT24=0','-DCODEC2_WEIGHT_AVR_INT24=0','-DCODEC2_WEIGHT_ROUND_LEGACY=0','-DCODEC2_ANALYSIS_BITS=32','-DCODEC2_ANALYSIS_TWIDDLE_Q=30','-DCODEC2_ANALYSIS_DIRECT_PAIR=1','-DCODEC2_ANALYSIS_GUARD_BITS=18','-DCODEC2_FAITHFUL_BITS=40']
    includes=['-I'+str(ROOT/'include'),'-I'+str(ROOT/'src')];suffix='.exe' if os.name=='nt' else '';libm=[] if os.name=='nt' else ['-lm'];memory=device_memory('avr-gcc','atmega64a');images={}
    for name,reference,candidate,vectors,harness,prefix,count,bytes_out,report in [
        ('weight',['src/fixed_weight.c'],['src/fixed_weight_sums32.c'],'weight_vectors.c','avr_weight.c','codec2_weight',512,2048,'weight-kernel'),
        ('adaptive',['src/adaptive_analysis.c','src/fast_analysis.c'],['src/adaptive_analysis.c','src/fast_analysis_sums32.c'],'analysis_vectors.c','avr_analysis.c','codec2_analysis',64,2056,'adaptive-kernel')]:
        folder=BUILD/name;folder.mkdir(exist_ok=True);old=json.loads((ROOT/'reports'/f'{report}.json').read_text())
        for file,h in old['sources'].items():assert front.digest(ROOT/file)==h,file
        common=['clang','-O2','-fno-strict-aliasing','-ffp-contract=off','-D_CRT_SECURE_NO_WARNINGS','-DCODEC2_WEIGHT_CHECKS=1','-DCODEC2_ANALYSIS_CHECKS=1',*flags,*includes]
        for tag,sources in [('reference',reference),('candidate',candidate)]:
            program=folder/(tag+suffix);front.run([*common,*[ROOT/x for x in sources],ROOT/'tests'/vectors,'-o',program,*libm]);front.run([program,folder/(tag+'.inputs'),folder/(tag+'.expected')])
        assert (folder/'reference.inputs').read_bytes()==(folder/'candidate.inputs').read_bytes()
        assert (folder/'reference.expected').read_bytes()==(folder/'candidate.expected').read_bytes()
        assert front.digest(folder/'reference.expected')==old['expected_sha256']
        front.run(['avr-gcc','-mmcu=atmega64a','-Os','-std=c99','-fno-strict-aliasing','-ffunction-sections','-fdata-sections','-DCODEC2_WEIGHT_CHECKS=0','-DCODEC2_ANALYSIS_CHECKS=0',*flags,*includes,*[ROOT/x for x in candidate],ROOT/'tests'/harness,'-Wl,--gc-sections','-Wl,--defsym=__DATA_REGION_ORIGIN__='+str(0x800000+memory['RAMSTART']),'-Wl,--defsym=__DATA_REGION_LENGTH__='+str(memory['RAMEND']-memory['RAMSTART']+1),'-Wl,--defsym=__TEXT_REGION_LENGTH__='+str(memory['FLASHEND']+1),'-o',folder/'kernel.elf','-lm'])
        front.run(['avr-objcopy','-O','binary',folder/'kernel.elf',folder/'kernel.bin'])
        with (folder/'symbols.txt').open('wb') as f:front.run(['avr-nm','-n',folder/'kernel.elf'],stdout=f)
        images[name]={'prefix':prefix,'vectors':count,'output_bytes':bytes_out,'binary_sha256':front.digest(folder/'kernel.bin'),'inputs_sha256':front.digest(folder/'reference.inputs'),'expected_sha256':front.digest(folder/'reference.expected'),'reference_report_sha256':front.digest(ROOT/'reports'/f'{report}.json'),'reference_execution':old['execution']}
    result={'defines':flags,'memory':memory,'images':images,'compiler':front.run(['avr-gcc','--version'],capture_output=True,text=True).stdout.splitlines()[0]};front.dump(BUILD/'build.json',result)
    front.run(['node',ROOT/'tests/verify_sums32_kernels_avr.mjs']);result['execution']=json.loads((BUILD/'execution.json').read_text())
    names=['src/fixed_weight_sums32.c','src/fast_analysis_sums32.c','src/weight_sum32.h','tools/generate_narrow_spectrum.py','tests/weight_sum32.c','tests/weight_vectors.c','tests/analysis_vectors.c','tests/avr_weight.c','tests/avr_analysis.c','tests/verify_sums32_kernels_avr.mjs','tools/verify_sums32_kernels.py']
    result['sources']={**baseline['sources'],**{n:front.digest(ROOT/n) for n in names}}
    front.dump(ROOT/'reports/sums32-kernels.json' if a.record else BUILD/'verification.json',result)
if __name__=='__main__':main()
