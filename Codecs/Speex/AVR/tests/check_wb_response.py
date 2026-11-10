#!/usr/bin/env python3
"""Exhaust HB1 response bounds with paired isolated current/Xiph LPC primitives.

Requires a POSIX host GCC/Clang toolchain with GNU-style ELF linker options.
This compiles and executes scalar LSP-to-LPC routines, never a C decoder.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import apply_profile
import build


def sha(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cc',default='gcc')
    p.add_argument('--record',action='store_true',help='Retain a compact source-bound complete-domain report')
    p.add_argument('--report',type=Path,default=ROOT/'reports/wb-response-domain.json',
        help='Destination for --record; preserve historical stage receipts when sources change')
    p.add_argument('--pilot-old-count',type=int,help='Explicit incomplete cost pilot; cannot be recorded')
    args=p.parse_args()
    if args.pilot_old_count is not None and not 1<=args.pilot_old_count<=4096:p.error('Pilot count must be 1..4096')
    if args.record and args.pilot_old_count is not None:p.error('An incomplete pilot cannot be recorded')
    _,source=build.prepare('wb-response-source')
    apply_profile.apply(source)
    out=ROOT/'build/wb-response-domain'
    out.mkdir(parents=True,exist_ok=True)
    compiler=subprocess.check_output([args.cc,'--version'],text=True).splitlines()[0]
    common=['-std=c11','-O3','-fwrapv','-fno-strict-aliasing','-ffunction-sections','-fdata-sections','-DFIXED_POINT']

    def run(command):
        subprocess.run(list(map(str,command)),check=True)

    reference=out/'reference.o'
    run([args.cc,*common,'-Dlsp_to_lpc=original_lsp_to_lpc','-Dlsp_interpolate=original_lsp_interpolate',
         '-Dlpc_to_lsp=original_lpc_to_lsp','-I'+str(source/'include'),
         '-I'+str(build.VENDOR/'libspeex'),'-c',build.VENDOR/'libspeex/lsp.c','-o',reference])
    executable=out/'proof'
    run([args.cc,*common,'-D_POSIX_C_SOURCE=200809L','-DCHECK_REFERENCE',
         '-DSPEEX_ENABLE_WB1=1','-DSPEEX_NB3_ENABLE_ASM=0','-DSPEEX_AVR_COMPACT_LSP',
         '-DSPEEX_AVR_TIGHT_EXC','-DSPEEX_AVR_PROFILE','-I'+str(source/'include'),
         '-I'+str(source/'libspeex'),'-I'+str(ROOT/'src'),source/'libspeex/lsp.c',
         source/'libspeex/high_lsp_tables.c',ROOT/'tests/host_wb_response.c',reference,
         '-Wl,--gc-sections','-o',executable])
    with (out/'verification.json').open('w',encoding='utf-8') as log:
        subprocess.run([str(executable),*([str(args.pilot_old_count),'pilot'] if args.pilot_old_count else [])],
                       stdout=log,check=True)
    result=json.loads((out/'verification.json').read_text(encoding='utf-8'))
    if args.pilot_old_count:
        print('INCOMPLETE pilot:',result['elapsedSeconds'],'host seconds')
        return
    assert result['oldEndpointLimit']==4096 and not result['pilot']
    assert [row['count'] for row in result['rows']]==[4096**2,4096*4097//2,4096]
    assert result['untouchedXiphComparisons']==25171968
    assert [(row['min'],row['max']) for row in result['rows']]==[(111,31849),(111,31831),(111,31605)]
    assert all(not row['nonpositive'] and not row['above32767'] for row in result['rows'])
    assert result['modular16ResponseExact'] and result['zeroDenResponse']==8274
    assert 111<=result['zeroDenResponse']<=31849
    # The generated primitive must be the current project body, not a frozen
    # copied surrogate. The separate reference is the untouched vendor file.
    marker='void speex_wb_lsp8('
    generated=(source/'libspeex/lsp.c').read_text(encoding='utf-8')
    current=(ROOT/'src/compact_lsp.c.inc').read_text(encoding='utf-8')
    body=lambda text:text[text.index(marker):text.index('#endif',text.index(marker))]
    assert body(generated)==body(current)
    if args.record:
        sources=['tests/host_wb_response.c','tests/check_wb_response.py','tests/check_wb_interpolation.py',
                 'src/compact_lsp.c.inc','src/nb3_lsp_finish.h','src/nb3_lsp_first.h','src/nb3_lsp_stage.h','src/nb3_c_math.h',
                 'src/avr_fixed.h','src/speex_platform.h','src/speex_wb1.c','tools/build.py',
                 'tools/apply_profile.py','handoff/upstream/tools/apply_upstream_port.py',
                 'handoff/upstream/tools/apply_tight_exc.py','vendor/speex-1.2.1/libspeex/lsp.c',
                 'vendor/speex-1.2.1/libspeex/arch.h','vendor/speex-1.2.1/libspeex/math_approx.h',
                 'vendor/speex-1.2.1/libspeex/fixed_generic.h','vendor/speex-1.2.1/libspeex/high_lsp_tables.c']
        report=dict(scope='Exhaustive isolated HB1 LPC response domain; no complete C decoder execution',
                    compilerVersion=compiler,compilerFlags=common,
                    currentPrimitiveMatchesSource=True,untouchedXiphComparisons=result['untouchedXiphComparisons'],
                    sourceHashMode='Text normalized to LF',sourceSha256={n:sha(ROOT/n) for n in sources},
                    generatedSourceSha256={n:sha(source/n) for n in [
                        'libspeex/lsp.c','libspeex/high_lsp_tables.c','libspeex/arch.h',
                        'libspeex/math_approx.h','libspeex/fixed_generic.h',
                        'include/speex/speex_types.h','include/speex/speex_config_types.h']},
                    endpointVectors=4096,uniquePrimitiveCases=25171968,representedQuarterCases=4*4096**2,
                    responseExpression='8274 + sum(den[odd] - den[even])',responseMin=111,responseMax=31849,
                    zeroDenResponse=result['zeroDenResponse'],zeroDenInsideBounds=True,
                    quarterRows=result['rows'],termsAndPrefixes=result['termsAndPrefixes'],
                    modular16ResponseExact=True,
                    symmetryProof=[
                        'Every endpoint component is a multiple of 16. Quarter 3(old,new) equals quarter 1(new,old), including deterministic margin repair.',
                        'Quarter 2 is symmetric in old/new; all unordered pairs and the diagonal are checked.',
                        'Quarter 4 depends only on the new endpoint; all 4096 are checked.'],
                    backend='Host portable C primitive compared with untouched pinned Xiph primitive',
                    includesInterrupts=False,physicalBoardTested=False,cDecoderExecuted=False,
                    limits=[
                        'The bound applies to the pinned 4096 HB1 codebook endpoints, exact quarter interpolation and sequential margin repair.',
                        'AVR applicability also depends on the existing exact C/ASM LPC primitive contract; this host run does not execute assembly.',
                        'Modulo 16 storage of a proven final response alone does not establish signed16 safety of intermediate terms or prefixes; separate measured ranges are included.',
                        'No decoder cycle, continuous-output or physical-board timing is measured.'])
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('PASS: 25,171,968 paired scalar conversions; response 111..31849; exact modulo 16 reduction')


if __name__=='__main__':main()
