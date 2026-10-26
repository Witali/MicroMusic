#!/usr/bin/env python3
"""Qualify the shared radix FFT and reselect its faithful conditioning guard."""
import argparse,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import verify_frontend as front
from verify_decoder import metrics
from study_fixed_precision import admissible
from generate_narrow_spectrum import generate_weight,generate_fast
ROOT=front.ROOT
BUILD=ROOT.parents[1]/'build/codec2/matrix-study'
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--record',action='store_true');a=p.parse_args();BUILD.mkdir(parents=True,exist_ok=True)
    baseline=json.loads((ROOT/'reports/canonical-decoder.json').read_text())
    for name,h in baseline['sources'].items():assert front.digest(ROOT/name)==h,name
    assert generate_weight()==(ROOT/'src/fixed_weight_sums32.c').read_bytes();assert generate_fast()==(ROOT/'src/fast_analysis_sums32.c').read_bytes()
    source=front.VENDOR/'src';legacy=ROOT/'AVR/Codec2_Tiny13_Quality_R2/tests';corpus=[('speech.c2zx',legacy/'speech.c2zx'),('codec2_3200_8byte_frames.bin',legacy/'codec2_3200_8byte_frames.bin'),('all-11333',front.BUILD/'frames.bin')];expected={}
    for name,path in corpus:
        previous=next(x for x in baseline['streams'] if x['name']==name);oracle=ROOT.parents[1]/'build/codec2/canonical'/(name+'.upstream.pcm');assert front.digest(path)==previous['packet_sha256'] and front.digest(oracle)==previous['oracle_sha256'];expected[name]=oracle.read_bytes()
    flags=['-DCODEC2_FIXED_BITS=16','-DCODEC2_FIXED_TWIDDLE_Q=10','-DCODEC2_FIXED_WIDE_LAST=0','-DCODEC2_ROOT_Q=11','-DCODEC2_ROOT_TABLE_BITS=6','-DCODEC2_WEIGHT_BITS=24','-DCODEC2_WEIGHT_TWIDDLE_Q=22','-DCODEC2_WEIGHT_DIRECT_PAIR=1','-DCODEC2_WEIGHT_SPLIT24=0','-DCODEC2_WEIGHT_AVR_INT24=0','-DCODEC2_WEIGHT_ROUND_LEGACY=0','-DCODEC2_WEIGHT_CHECKS=1','-DCODEC2_FIXED_CHECKS=1','-DCODEC2_ANALYSIS_CHECKS=1','-DCODEC2_ANALYSIS_BITS=32','-DCODEC2_ANALYSIS_TWIDDLE_Q=30','-DCODEC2_FAITHFUL_BITS=40','-DCODEC2_ADAPTIVE_STATS=1']
    sources=[ROOT/'src/spectral_decoder.c',ROOT/'tests/analysis_variant.c',ROOT/'tests/adaptive_compare.c',ROOT/'src/adaptive_analysis.c',ROOT/'src/matrix_analysis.c',ROOT/'src/fixed_weight_sums32.c',ROOT/'src/fixed_inverse.c',ROOT/'src/fixed_fifth.c',ROOT/'src/compact_fft.c',ROOT/'src/parameters.c',source/'lsp.c'];results=[]
    for guard in range(14,23):
        tag='g'+str(guard);program=BUILD/(tag+('.exe' if os.name=='nt' else ''));streams=[]
        front.run(['clang','-O2','-fno-strict-aliasing','-ffp-contract=off','-D_CRT_SECURE_NO_WARNINGS',*flags,'-DCODEC2_ANALYSIS_GUARD_BITS='+str(guard),'-I'+str(ROOT/'include'),'-I'+str(ROOT/'src'),'-I'+str(source),*sources,'-o',program,*([] if os.name=='nt' else ['-lm'])])
        for name,path in corpus:
            output=BUILD/(tag+'-'+name+'.pcm');run=front.run([program,path,output],capture_output=True,text=True);control=json.loads(run.stdout);cost=json.loads(run.stderr)
            result={'name':name,**metrics(output.read_bytes(),expected[name]),**control,'refinement':cost,'output_sha256':front.digest(output)};result['passes']=admissible(result) and result['frames_with_rng_mismatch']==0;streams.append(result)
        record={'component_bits':32,'twiddle_q':30,'faithful_bits':40,'guard_bits':guard,'graph':'radix256','streams':streams,'passes':all(s['passes'] for s in streams)};results.append(record);print(json.dumps({'guard':guard,'passes':record['passes'],'stress':streams[-1]}),flush=True)
    passing=[r for r in results if r['passes']];chosen=min(passing,key=lambda r:sum(s['refinement']['refined_bins'] for s in r['streams'])) if passing else None
    names=['src/matrix_analysis.c','src/fixed_weight_sums32.c','src/weight_sum32.h','tools/generate_narrow_spectrum.py','tools/study_matrix_precision.py','tests/adaptive_compare.c']
    report={'baseline_report_sha256':front.digest(ROOT/'reports/spectral-decoder.json'),'paired_baseline_report_sha256':front.digest(ROOT/'reports/canonical-decoder.json'),'selection':{k:chosen[k] for k in ['component_bits','twiddle_q','faithful_bits','guard_bits','graph']} if chosen else None,'results':results,'sources':{**baseline['sources'],**{n:front.digest(ROOT/n) for n in names}},'compiler':front.run(['clang','--version'],capture_output=True,text=True).stdout.splitlines()[0],'scope':'Native whole PCM and per-frame RNG; in-place full sparse radix FFT, 32/Q30, existing wide40 refinement. Guard search 14..22, not a universal minimum. No AVR/IRQ admission.'}
    front.dump(ROOT/'reports/matrix-precision.json' if a.record else BUILD/'verification.json',report)
if __name__=='__main__':main()
