#!/usr/bin/env python3
"""Select fixed-point fifth-root precision using whole-decoder PCM gates."""
import argparse
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import verify_frontend as front
from verify_decoder import metrics
from study_fixed_precision import admissible
from generate_fifth_tables import generate

ROOT=front.ROOT
BUILD=ROOT.parents[1]/'build/codec2/postfilter-study'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc',default='clang');parser.add_argument('--record',action='store_true');args=parser.parse_args()
    BUILD.mkdir(parents=True,exist_ok=True)
    original=json.loads((ROOT/'reports/hybrid-decoder.json').read_text())
    for name,wanted in original['sources'].items():assert front.digest(ROOT/name)==wanted,name
    body=(ROOT/'src/compact_decoder.c').read_text()
    assert body.count('powf(')==1 and 'powf(rw, 0.2f)' in body
    source=front.VENDOR/'src';legacy=ROOT/'AVR/Codec2_Tiny13_Quality_R2/tests'
    corpus=[('speech.c2zx',legacy/'speech.c2zx'),('codec2_3200_8byte_frames.bin',legacy/'codec2_3200_8byte_frames.bin'),('all-11333',front.BUILD/'frames.bin')]
    expected={}
    for name,path in corpus:
        ref=next(r for r in original['streams'] if r['name']==name)
        pcm=ROOT.parents[1]/'build/codec2/hybrid'/(name+'.upstream.pcm')
        assert front.digest(path)==ref['packet_sha256'] and front.digest(pcm)==ref['oracle_sha256']
        expected[name]=pcm.read_bytes()
    library=[ROOT/'src/hybrid_postfilter.c',ROOT/'src/fixed_fifth.c',ROOT/'src/fixed_inverse.c',ROOT/'src/compact_fft.c',ROOT/'src/parameters.c',source/'lsp.c']
    results=[]
    for q in range(8,24):
        for bits in [3,4,5,6]:
            folder=BUILD/f'q{q}-b{bits}';folder.mkdir(exist_ok=True)
            table=folder/'fixed_fifth_tables.inc';table.write_bytes(generate(q,bits))
            common=[args.cc,'-O2','-fno-strict-aliasing','-ffp-contract=off','-D_CRT_SECURE_NO_WARNINGS','-DCODEC2_FIXED_CHECKS=1',
                '-DCODEC2_ROOT_Q='+str(q),'-DCODEC2_ROOT_TABLE_BITS='+str(bits),'-I'+str(folder),
                '-I'+str(ROOT/'include'),'-I'+str(ROOT/'src'),'-I'+str(source)]
            exe='.exe' if os.name=='nt' else '';libm=[] if os.name=='nt' else ['-lm']
            kernel=folder/('kernel'+exe);program=folder/('decode'+exe)
            front.run([*common,ROOT/'src/fixed_fifth.c',ROOT/'tests/fixed_fifth.c','-o',kernel,*libm])
            kernel_result=json.loads(front.run([kernel],capture_output=True,text=True).stdout)
            front.run([*common,*library,ROOT/'tests/hybrid_decode.c','-o',program,*libm])
            streams=[]
            for name,path in corpus:
                output=folder/(name+'.pcm');front.run([program,path,output],capture_output=True)
                result={'name':name,'output_sha256':front.digest(output),**metrics(output.read_bytes(),expected[name])}
                result['passes']=admissible(result);streams.append(result)
            record={'q':q,'table_bits':bits,'table_bytes':5*((1<<bits)+1)*(2 if q<=15 else 3)+5*(1<<bits)*2,
                'table_sha256':front.digest(table),'kernel':kernel_result,'streams':streams,'passes':all(r['passes'] for r in streams)}
            results.append(record);print(json.dumps({'q':q,'bits':bits,'passes':record['passes'],'stress':streams[-1]}),flush=True)
    selected=min((r for r in results if r['passes']),key=lambda r:(r['q'],r['table_bits']))
    names=['src/fixed_fifth.c','src/fixed_fifth.h','src/hybrid_postfilter.c','tests/fixed_fifth.c','tools/generate_fifth_tables.py','tools/study_postfilter.py']
    report={'baseline_report_sha256':front.digest(ROOT/'reports/hybrid-decoder.json'),
        'selection':{k:selected[k] for k in ['q','table_bits','table_bytes']},'results':results,
        'sources':{n:front.digest(ROOT/n) for n in names},
        'compiler':front.run([args.cc,'--version'],capture_output=True,text=True).stdout.splitlines()[0],
        'scope':'Native root precision/table-size study on 11333 packets and two reset streams; existing fixed IFFT16/Q9 unchanged. No AVR/IRQ admission.'}
    front.dump(ROOT/'reports/postfilter-precision.json' if args.record else BUILD/'precision.json',report)
if __name__=='__main__':main()
