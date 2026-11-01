#!/usr/bin/env python3
"""Compile/link the exported C11 library; never execute or time the decoder."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--clang',required=True)
    p.add_argument('--export',type=Path,default=ROOT/'build/low-export');args=p.parse_args();root=args.export.resolve()
    manifest=json.loads((root/'sources.json').read_text())
    assert len(manifest['sources'])==len(set(manifest['sources']))==21
    assert set(manifest['widebandBitrates'])=={3950,5750,7750,9800,12800} and not list(root.rglob('*.S'))
    shim=root/'link_only.c'
    shim.write_bytes(b'''#include "speex_nb.h"
#include "speex_wb1.h"
static void sink(const int16_t *p,uint8_t n,void *ctx){(void)p;(void)n;(void)ctx;}
__declspec(dllexport) int link_all(const uint8_t *p,size_t n,int16_t *out,int wb)
{return wb?speex_wb1_decode(p,n,sink,0):speex_nb_decode(p,n,out);}
__declspec(dllexport) size_t link_init(void)
{speex_wb1_init();return speex_wb1_state_bytes()+speex_nb_state_bytes();}
''')
    subprocess.run([args.clang,'-x','c','-std=c11','-O2','-fwrapv','-fno-strict-aliasing','-shared',
        '-Wno-pointer-to-int-cast',*['-D'+x for x in manifest['definitions']],
        *['-I'+str(root/x) for x in manifest['includeDirectories']],
        *[str(root/x) for x in manifest['sources']],str(shim),'-o',str(root/'link_only.dll')],check=True)
    report=dict(scope='Portable C11 package compile/link only; C decoder is not executed or timed',
        sources=len(manifest['sources']),duplicateSources=False,handwrittenAssembly=False,
        widebandBitrates=sorted(manifest['widebandBitrates']),
        artifactSha256=hashlib.sha256((root/'link_only.dll').read_bytes()).hexdigest())
    (ROOT/'build/low-export-check.json').write_bytes((json.dumps(report,indent=2)+'\n').encode())
    print('PASS exported C11 sources compile and link; no C decoder runtime tests')


if __name__=='__main__':main()
