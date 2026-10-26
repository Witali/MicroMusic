#!/usr/bin/env python3
"""Select weighted-spectrum precision from whole PCM and actual RNG histories."""
import argparse,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import verify_frontend as front
from verify_decoder import metrics
from study_fixed_precision import admissible
from generate_weight_tables import generate
ROOT=front.ROOT
BUILD=ROOT.parents[1]/'build/codec2/weight-study'
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cc',default='clang');p.add_argument('--record',action='store_true');p.add_argument('--radix',action='store_true');a=p.parse_args();BUILD.mkdir(parents=True,exist_ok=True)
    baseline=json.loads((ROOT/'reports/postfilter-decoder.json').read_text())
    for name,wanted in baseline['sources'].items():assert front.digest(ROOT/name)==wanted,name
    assert generate()==(ROOT/'src/fixed_weight_tables.inc').read_bytes()
    source=front.VENDOR/'src';legacy=ROOT/'AVR/Codec2_Tiny13_Quality_R2/tests';expected={}
    corpus=[('speech.c2zx',legacy/'speech.c2zx'),('codec2_3200_8byte_frames.bin',legacy/'codec2_3200_8byte_frames.bin'),('all-11333',front.BUILD/'frames.bin')]
    for name,path in corpus:
        old=next(s for s in baseline['streams'] if s['name']==name);oracle=ROOT.parents[1]/'build/codec2/postfilter'/(name+'.upstream.pcm')
        assert front.digest(path)==old['packet_sha256'] and front.digest(oracle)==old['oracle_sha256'];expected[name]=oracle.read_bytes()
    shared=[ROOT/'src/hybrid_postfilter.c',ROOT/'tests/spectral_variant.c',ROOT/'tests/spectral_compare.c',ROOT/'src/fixed_weight.c',ROOT/'src/fixed_inverse.c',ROOT/'src/fixed_fifth.c',ROOT/'src/compact_fft.c',ROOT/'src/parameters.c',source/'lsp.c']
    results=[]
    cases=[(bits,q,ifft) for bits in [16,24,32] for q in [14,22,30] for ifft in ([9] if a.radix else [9,10])]
    for bits,q,ifft in cases:
            tag=f'i{bits}-q{q}-f{ifft}-d{int(not a.radix)}';exe='.exe' if os.name=='nt' else '';program=BUILD/(tag+exe);kernel=BUILD/(tag+'-kernel'+exe);libm=[] if os.name=='nt' else ['-lm']
            common=[a.cc,'-O2','-fno-strict-aliasing','-ffp-contract=off','-D_CRT_SECURE_NO_WARNINGS','-DCODEC2_WEIGHT_CHECKS=1','-DCODEC2_FIXED_CHECKS=1','-DCODEC2_WEIGHT_BITS='+str(bits),'-DCODEC2_WEIGHT_TWIDDLE_Q='+str(q),'-I'+str(ROOT/'include'),'-I'+str(ROOT/'src'),'-I'+str(source)]
            common+=['-DCODEC2_FIXED_TWIDDLE_Q='+str(ifft),'-DCODEC2_WEIGHT_DIRECT_PAIR='+str(int(not a.radix))]
            front.run([*common,*shared,'-o',program,*libm]);front.run([*common,ROOT/'src/fixed_weight.c',ROOT/'tests/fixed_weight.c',source/'kiss_fft.c',source/'kiss_fftr.c','-o',kernel,*libm])
            kernel_result=json.loads(front.run([kernel],capture_output=True,text=True).stdout);streams=[]
            for name,path in corpus:
                output=BUILD/(tag+'-'+name+'.pcm');control=json.loads(front.run([program,path,output],capture_output=True,text=True).stdout)
                result={'name':name,**metrics(output.read_bytes(),expected[name]),**control,'output_sha256':front.digest(output)};result['passes']=admissible(result);streams.append(result)
            record={'component_bits':bits,'twiddle_q':q,'ifft_twiddle_q':ifft,'direct_pair':not a.radix,'kernel':kernel_result,'streams':streams,'passes':all(s['passes'] for s in streams)};results.append(record);print(json.dumps(record),flush=True)
    passing=[r for r in results if r['passes']]
    selected=min(passing,key=lambda r:(r['component_bits'],r['twiddle_q'],r['ifft_twiddle_q'])) if passing else None
    names=['src/fixed_weight.c','src/fixed_weight.h','src/fixed_weight_tables.inc','src/weight_round.h','src/spectral_table_access.h','src/spectral_decoder.c','tests/spectral_variant.c','tests/spectral_compare.c','tests/fixed_weight.c','tools/generate_weight_tables.py','tools/study_weight_precision.py']
    report={'baseline_report_sha256':front.digest(ROOT/'reports/postfilter-decoder.json'),'selection':{k:selected[k] for k in ['component_bits','twiddle_q','ifft_twiddle_q','direct_pair']} if selected else None,
        'results':results,'sources':{n:front.digest(ROOT/n) for n in names},'compiler':front.run([a.cc,'--version'],capture_output=True,text=True).stdout.splitlines()[0],
        'scope':'Native full PCM/RNG precision study for fixed gamma-weighted LPC spectrum; base LPC spectrum and phase still float. Not AVR/IRQ admission.'}
    front.dump(ROOT/('reports/weight-radix-recheck.json' if a.radix else 'reports/weight-direct-precision.json') if a.record else BUILD/'verification.json',report)
if __name__=='__main__':main()
