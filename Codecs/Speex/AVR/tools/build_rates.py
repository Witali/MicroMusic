#!/usr/bin/env python3
"""Build PC references and an experimental low-memory native WB/UWB decoder.

The patched build tests QMF layout and subframe scratch lifetime only. It is
not the ATmega328P decoder and is not advertised as a playable AVR profile.
"""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import build
from apply_profile import replace

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc',required=True)
    parser.add_argument('--memory',action='store_true')
    args=parser.parse_args()
    output,source=build.prepare('reference')
    output=build.ROOT/'build'/('rates-memory' if args.memory else 'rates-reference')
    output.mkdir(parents=True,exist_ok=True)
    # Separate copies allow both builds to coexist and preserve the NB oracle.
    import shutil
    shutil.copytree(source,output/'source',dirs_exist_ok=True)
    source=output/'source'
    extra=[]
    if args.memory:
        path=source/'libspeex/sb_celp.c'
        text=path.read_text()
        begin=text.index('void *sb_decoder_init(')
        text=text[:begin]+text[begin:].replace('(QMF_ORDER)*sizeof(spx_word16_t)',
                                               '(QMF_ORDER/2)*sizeof(spx_word16_t)')
        # State reset follows the denser history allocation too.
        begin=text.index('int sb_decoder_ctl(')
        text=text[:begin]+text[begin:].replace('i<QMF_ORDER','i<QMF_ORDER/2')
        begin=text.index('int sb_decode(')
        before,body=text[:begin],text[begin:]
        body=replace(body,'   for (sub=0;sub<st->nbSubframes;sub++)',
                     '   VARDECL(spx_word32_t *exc);\n   ALLOC(exc, st->subframeSize, spx_word32_t);\n\n   for (sub=0;sub<st->nbSubframes;sub++)')
        body=replace(body,'      VARDECL(spx_word32_t *exc);','')
        body=replace(body,'      ALLOC(exc, st->subframeSize, spx_word32_t);','')
        text=before+body
        call='qmf_synth(out, out+st->frame_size, h0, out, st->full_frame_size, QMF_ORDER, st->g0_mem, st->g1_mem, stack);'
        text=replace(text,call,'speex_avr_qmf_memory(out, st->full_frame_size, st->g0_mem, st->g1_mem);',3)
        text='#include "qmf_memory.h"\n'+text
        path.write_text(text)
        path=source/'libspeex/lsp.c'
        text=path.read_text()
        begin=text.index('void lsp_to_lpc(')
        end=text.index('\n#else',begin)
        text=text[:begin]+(build.ROOT/'src/compact_lsp_rates.c.inc').read_text()+text[end:]
        path.write_text(text)
        extra=[build.ROOT/'src/qmf_memory.c']
    definitions=[d for d in build.DEFINES if d!='DISABLE_WIDEBAND']
    sources=build.SOURCES+['modes_wb','sb_celp','high_lsp_tables','hexc_table','hexc_10_32_table']
    exe=output/'decode.exe'
    build.run([args.cc,'-O2','-fwrapv','-fno-strict-aliasing','-Wno-pointer-to-int-cast',
               '-D_CRT_SECURE_NO_WARNINGS',*['-D'+d for d in definitions],
               '-I'+str(source/'include'),'-I'+str(source/'libspeex'),'-I'+str(build.ROOT/'src'),
               *[source/'libspeex'/(s+'.c') for s in sources],*extra,
               build.ROOT/'tests/decode_rates.c','-o',exe])
    if args.memory:
        flags=['-O2','-fwrapv','-fno-strict-aliasing','-Wno-pointer-to-int-cast',
               *['-D'+d for d in definitions],'-I'+str(source/'include'),'-I'+str(source/'libspeex')]
        build.run([args.cc,*flags,'-Dlsp_to_lpc=reference_lsp',
                   '-Dlsp_interpolate=reference_interpolate','-c',
                   build.ROOT/'vendor/speex-1.2.1/libspeex/lsp.c','-o',output/'oracle-lsp.o'])
        build.run([args.cc,*flags,source/'libspeex/lsp.c',output/'oracle-lsp.o',
                   build.ROOT/'tests/lsp_rates.c','-o',output/'lsp-test.exe'])
        build.run([output/'lsp-test.exe'])
    print(exe)

if __name__=='__main__': main()
