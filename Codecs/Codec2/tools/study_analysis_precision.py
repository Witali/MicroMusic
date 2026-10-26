#!/usr/bin/env python3
"""Measure main-LPC spectral minima, whole PCM and RNG for integer precision."""
import argparse,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import verify_frontend as front
from verify_decoder import metrics
from study_fixed_precision import admissible
ROOT=front.ROOT
BUILD=ROOT.parents[1]/'build/codec2/analysis-study'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cc',default='clang');p.add_argument('--record',action='store_true');p.add_argument('--radix',action='store_true')
    a=p.parse_args();BUILD.mkdir(parents=True,exist_ok=True)
    baseline=json.loads((ROOT/'reports/spectral-decoder.json').read_text())
    for name,wanted in baseline['sources'].items():assert front.digest(ROOT/name)==wanted,name
    source=front.VENDOR/'src';legacy=ROOT/'AVR/Codec2_Tiny13_Quality_R2/tests'
    corpus=[('speech.c2zx',legacy/'speech.c2zx'),('codec2_3200_8byte_frames.bin',legacy/'codec2_3200_8byte_frames.bin'),('all-11333',front.BUILD/'frames.bin')]
    expected={}
    for name,path in corpus:
        old=next(s for s in baseline['streams'] if s['name']==name);oracle=ROOT.parents[1]/'build/codec2/spectral'/(name+'.upstream.pcm')
        assert front.digest(path)==old['packet_sha256'] and front.digest(oracle)==old['oracle_sha256'];expected[name]=oracle.read_bytes()
    flags=['-DCODEC2_FIXED_BITS=16','-DCODEC2_FIXED_TWIDDLE_Q=10','-DCODEC2_FIXED_WIDE_LAST=0','-DCODEC2_ROOT_Q=11','-DCODEC2_ROOT_TABLE_BITS=6','-DCODEC2_WEIGHT_BITS=24','-DCODEC2_WEIGHT_TWIDDLE_Q=22','-DCODEC2_WEIGHT_DIRECT_PAIR=1','-DCODEC2_WEIGHT_CHECKS=1','-DCODEC2_FIXED_CHECKS=1','-DCODEC2_ANALYSIS_CHECKS=1']
    shared=[ROOT/'src/spectral_decoder.c',ROOT/'tests/analysis_variant.c',ROOT/'tests/analysis_compare.c',ROOT/'src/fixed_analysis.c',ROOT/'src/fixed_weight.c',ROOT/'src/fixed_inverse.c',ROOT/'src/fixed_fifth.c',ROOT/'src/compact_fft.c',ROOT/'src/parameters.c',source/'lsp.c']
    results=[]
    for bits in [16,24,32]:
        for q in [14,22,30]:
            tag=f'i{bits}-q{q}-d{int(not a.radix)}';program=BUILD/(tag+('.exe' if os.name=='nt' else ''))
            common=[a.cc,'-O2','-fno-strict-aliasing','-ffp-contract=off','-D_CRT_SECURE_NO_WARNINGS',*flags,'-DCODEC2_ANALYSIS_BITS='+str(bits),'-DCODEC2_ANALYSIS_TWIDDLE_Q='+str(q),'-DCODEC2_ANALYSIS_DIRECT_PAIR='+str(int(not a.radix)),'-I'+str(ROOT/'include'),'-I'+str(ROOT/'src'),'-I'+str(source)]
            front.run([*common,*shared,'-o',program,*([] if os.name=='nt' else ['-lm'])]);streams=[]
            for name,path in corpus:
                output=BUILD/(tag+'-'+name+'.pcm');control=json.loads(front.run([program,path,output],capture_output=True,text=True).stdout)
                result={'name':name,**metrics(output.read_bytes(),expected[name]),**control,'output_sha256':front.digest(output)}
                result['passes']=admissible(result);streams.append(result)
            record={'component_bits':bits,'twiddle_q':q,'direct_pair':not a.radix,'streams':streams,'passes':all(s['passes'] for s in streams)}
            results.append(record);print(json.dumps(record),flush=True)
    passing=[r for r in results if r['passes']]
    chosen=min(passing,key=lambda r:(r['component_bits'],r['twiddle_q'])) if passing else None
    names=['src/fixed_analysis.c','src/fixed_analysis.h','src/analysis_decoder.c','tests/analysis_variant.c','tests/analysis_compare.c','tools/study_analysis_precision.py']
    report={'baseline_report_sha256':front.digest(ROOT/'reports/spectral-decoder.json'),'selection':{k:chosen[k] for k in ['component_bits','twiddle_q','direct_pair']} if chosen else None,'results':results,'sources':{**baseline['sources'],**{n:front.digest(ROOT/n) for n in names}},'compiler':front.run([a.cc,'--version'],capture_output=True,text=True).stdout.splitlines()[0],'scope':'Native main LPC spectrum precision and minima in the whole decoder. IFFT16/Q10, weighting24/Q22, rootQ11/64 retained. No AVR/IRQ admission.'}
    front.dump(ROOT/('reports/analysis-radix-precision.json' if a.radix else 'reports/analysis-precision.json') if a.record else BUILD/'verification.json',report)
if __name__=='__main__':main()
