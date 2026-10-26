#!/usr/bin/env python3
"""Explain low-precision rejection by comparing actual RNG state every frame."""
import argparse,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import verify_frontend as front
from generate_fifth_tables import generate
ROOT=front.ROOT
BUILD=ROOT.parents[1]/'build/codec2/postfilter-control'
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cc',default='clang');p.add_argument('--record',action='store_true');a=p.parse_args()
    source=front.VENDOR/'src';legacy=ROOT/'AVR/Codec2_Tiny13_Quality_R2/tests';results=[]
    for q,bits in [(8,3),(11,6)]:
        folder=BUILD/f'q{q}-b{bits}';folder.mkdir(parents=True,exist_ok=True);table=folder/'fixed_fifth_tables.inc';table.write_bytes(generate(q,bits))
        exe=folder/('control.exe' if os.name=='nt' else 'control')
        front.run([a.cc,'-O2','-fno-strict-aliasing','-ffp-contract=off','-D_CRT_SECURE_NO_WARNINGS','-DCODEC2_ROOT_Q='+str(q),'-DCODEC2_ROOT_TABLE_BITS='+str(bits),
            '-I'+str(folder),'-I'+str(ROOT/'include'),'-I'+str(ROOT/'src'),'-I'+str(source),ROOT/'src/hybrid_decoder.c',ROOT/'tests/postfilter_variant.c',ROOT/'tests/postfilter_control.c',
            ROOT/'src/fixed_fifth.c',ROOT/'src/fixed_inverse.c',ROOT/'src/compact_fft.c',ROOT/'src/parameters.c',source/'lsp.c','-o',exe,*([] if os.name=='nt' else ['-lm'])])
        streams=[]
        for name,path in [('speech.c2zx',legacy/'speech.c2zx'),('codec2_3200_8byte_frames.bin',legacy/'codec2_3200_8byte_frames.bin'),('all-11333',front.BUILD/'frames.bin')]:
            result={'name':name,'packet_sha256':front.digest(path),**json.loads(front.run([exe,path],capture_output=True,text=True).stdout)}
            if q==11:assert result['first_rng_mismatch_frame']==-1,result
            streams.append(result)
        results.append({'q':q,'table_bits':bits,'table_sha256':front.digest(table),'streams':streams});print(json.dumps(results[-1]),flush=True)
    names=['src/fixed_fifth.c','src/fixed_fifth.h','src/hybrid_postfilter.c','tests/postfilter_variant.c','tests/postfilter_control.c','tools/verify_postfilter_control.py','tools/generate_fifth_tables.py']
    report={'results':results,'sources':{n:front.digest(ROOT/n) for n in names},'scope':'Native frame-by-frame RNG states, low-precision counterexample and selected configuration; not an exhaustive threshold proof.'}
    front.dump(ROOT/'reports/postfilter-control.json' if a.record else BUILD/'verification.json',report)
if __name__=='__main__':main()
