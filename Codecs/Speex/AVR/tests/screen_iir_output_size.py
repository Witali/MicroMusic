#!/usr/bin/env python3
"""Reproduce IIR finish factoring in frozen sources, with unchanged C fallback.

Only isolated C filters execute. Complete decoder/player runs select ASM.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import screen_qmf_common_product as common

ROOT = Path(__file__).resolve().parents[1]
KERNELS = {
    'baseline': '193437dbc79dabc3a710ee062f0714a1896d53e16d29ec7d6674551607e7cda9',
    'local': 'f0c862140f82c918670ff00a83b5f0bb4fd2be4c93db4062b2eb2bb9dbe53118',
    'shared': 'd7382e9da1ae4accd9ef3ef3621e7f1ac6db99a645fa67a3f888c288f153180b',
    'phase': '649a950fb66eed41cbc0d0d21d9803ac154044bd21a2ee8d6278cd105e30456b',
}
PROFILES = {'wb395': 10, 'wb128': 32}
BASE_IMAGES = {
    'raw/wb395': '8243c252b616ecb424838a6eeb96dcea7750bed39509b40cc1fd31f82d561400',
    'raw/wb128': 'c341aff5171516aa02e7aa75b53fac486dff19d73f8cbcb52a64f8190f9976e1',
    'irq/wb395': '02805ff16b18572b7edfa147679ac3c2b804aea75a3185f6da7f6a5f826ec13e',
    'irq/wb128': '97994b85799c863dee272ad181e0f1469f96d64a8824db895a0db5eb74c8e467',
}
IGNORE = shutil.ignore_patterns('__pycache__', '*.mid', '*.midi', '*.smf')


def sha(path, text=False):
    return common.sha(path, text)


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')


def kernel(base, recipe):
    if recipe == 'baseline':
        return base
    text = base
    def replace(old, new):
        nonlocal text
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    start = base.index('    /* PSHR32(sum,13)')
    if recipe in ['local', 'shared']:
        end = base.index('    /* Y advances to the next sample')
        prefix = base[start:end].replace('\\@', '_output')
        name = 'iir_output_private' if recipe == 'local' else 'speex_avr_iir_output_private'
        text = text[:start]+('    rcall ' if recipe == 'local' else '    call ')+name+'\n'+text[end:]
        section = '\n.text\n' if recipe == 'local' else (
            '\n.section .text.'+name+',"axG",@progbits,'+name+',comdat\n.global '+name+'\n.hidden '+name+'\n')
        text += section+'.type '+name+',@function\n'+name+':\n'+prefix+'    ret\n.size '+name+',.-'+name+'\n'
    else:
        end = base.index('    /* Sample 0 uses all previous coefficients')
        body = base[start:end].replace('\\@', '_phase')
        replace('    IIR_FINISH 1\n    dec r3', '    rjmp .Liir_finish\n.Lwarm_finish_return:\n    dec r3')
        replace('.Liir_group:\n    ldi r18,IIR_ORDER', '.Liir_group:\n    ldi r18,lo8(-IIR_ORDER)')
        replace('    IIR_FINISH 0\n    dec r3\n    breq .Lgroup_done\n    rjmp .Lsteady_sample\n.Lgroup_done:',
                '.Liir_finish:\n'+body+
                '    /* Positive counters are warm; negative counters are steady groups. */\n'
                '    sbrs r3,7\n    rjmp .Lwarm_age\n    inc r3\n    breq .Lgroup_done\n'
                '    rjmp .Lsteady_sample\n.Lwarm_age:\n    movw r26,r10\n    ld r18,X+\n'
                '    ld r19,X+\n    movw r10,r26\n    std Y+(4*IIR_ORDER-2),r18\n'
                '    std Y+(4*IIR_ORDER-1),r19\n    rjmp .Lwarm_finish_return\n.Lgroup_done:')
        # This definition no longer has an invocation. Keep the shared finish
        # once; six rebuild identities bind this cleanup to executed evidence.
        assert hashlib.sha256(text.encode()).hexdigest() == '2581261f199e6eef33acf76701c8372c5fee3b762bf3a7f8294a6a54008746be'
        assert text.count('IIR_FINISH') == 1
        a = text.index('.macro IIR_FINISH age')
        b = text.index('.endm\n', a)+len('.endm\n')
        text = text[:a]+text[b:]
        assert 'IIR_FINISH' not in text
    assert hashlib.sha256(text.encode()).hexdigest() == KERNELS[recipe]
    return text


def prepare(out, source, cache, avr8js):
    assert sha(source/'src/iir_kernel.inc', True) == KERNELS['baseline'], 'Supply the admitted pre-factoring source root'
    ref = out/'reference/Codecs/Speex/AVR'
    if source.resolve() != ref.resolve():
        for part in ['src', 'tests', 'tools']:
            shutil.copytree(source/part, ref/part, dirs_exist_ok=True, ignore=IGNORE)
        shutil.copytree(source.parents[1]/'common', out/'reference/Codecs/common', dirs_exist_ok=True, ignore=IGNORE)
    if cache.resolve() != (out/'generated-source').resolve():
        shutil.copytree(cache, out/'generated-source', dirs_exist_ok=True, ignore=IGNORE)
    base = (ref/'src/iir_kernel.inc').read_text(encoding='utf-8')
    for name in KERNELS:
        shutil.copytree(ref/'src', out/name/'src', dirs_exist_ok=True, ignore=IGNORE)
        (out/name/'src/iir_kernel.inc').write_text(kernel(base, name), encoding='utf-8', newline='\n')
    text = (source/'tests/verify_iir_block.mjs').read_text(encoding='utf-8')
    text = text.replace('(op&0xf000)===0xd000', '((op&0xf000)===0xd000||(op&0xfe0e)===0x940e)')
    text = text.replace('min:Math.min(...timings[n]),max:Math.max(...timings[n])',
                        'min:Math.min(...timings[n]),max:Math.max(...timings[n]),cycles:timings[n]')
    scripts = {'verify_iir.mjs': text, **{n: (source/'tests'/n).read_text(encoding='utf-8')
               for n in ['verify_wb.mjs', 'verify_wb_stream.mjs', 'avr_tick.mjs']}}
    for name, text in scripts.items():
        (out/name).write_text(text.replace("from 'avr8js'", "from '"+avr8js.resolve().as_uri()+"'"),
                             encoding='utf-8', newline='\n')


def build_primitive(out, gcc):
    for name in KERNELS:
        for irq in [False, True]:
            folder = out/(name+('-irq' if irq else '-unit'))
            with (out/(folder.name+'-build.log')).open('w', encoding='utf-8') as log:
                subprocess.run(list(map(str, [sys.executable, ROOT/'tools/build_iir_block_test.py', '--avr-gcc', gcc,
                    '--source-root', out/name, '--out', folder, *(['--irq'] if irq else [])])),
                    stdout=log, stderr=subprocess.STDOUT, check=True)


def run_primitive(out, node):
    def run(name):
        with (out/(name+'-run.log')).open('w', encoding='utf-8') as log:
            subprocess.run([node, out/'verify_iir.mjs', '--firmware', out/name], stdout=log, stderr=subprocess.STDOUT, check=True)
        print('PASS', name, flush=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, [n+s for n in KERNELS for s in ['-unit', '-irq']]))


def whole_build(out, gcc):
    sys.path.insert(0, str(ROOT/'tools'))
    import build
    import build_wb
    import build_wb_stream_test
    saved = (build.ROOT, build.run, build_wb.prepare, sys.argv)
    ref = out/'reference/Codecs/Speex/AVR'
    try:
        build.ROOT = ref
        build_wb.prepare = lambda: out/'generated-source'
        original = build.run
        for name in ['baseline', 'shared', 'phase']:
            def run(argv, cwd=None):
                args = []
                for arg in argv:
                    if str(arg).replace('\\', '/') in [str(ref/'src'/n).replace('\\', '/') for n in ['lpc_dot.S', 'wb_iir.S']]:
                        args.append(out/name/'src'/Path(arg).name)
                    else:
                        args.append(arg)
                return original(args, cwd=cwd)
            build.run = run
            for profile, width in PROFILES.items():
                build_wb.avr(gcc, 'asm', packet_bytes=width, low_rates=7, enable_nb4=True,
                             destination=out/'whole'/name/'raw'/profile)
                sys.argv = ['build_wb_stream_test.py', '--avr-gcc', gcc, '--packet-bytes', str(width),
                            '--low-rates', '7', '--enable-nb4', '--frame-load-cycles', '25600',
                            '--out', str(out/'whole'/name/'irq'/profile)]
                build_wb_stream_test.main()
                if name == 'baseline':
                    for mode in ['raw', 'irq']:
                        assert sha(out/'whole'/name/mode/profile/'wb.bin') == BASE_IMAGES[mode+'/'+profile]
    finally:
        build.ROOT, build.run, build_wb.prepare, sys.argv = saved


def whole_run(out, node, corpus):
    def run(task):
        name, mode, profile = task
        folder = out/'whole'/name/mode/profile
        test = 'verify_wb.mjs' if mode == 'raw' else 'verify_wb_stream.mjs'
        with (folder/'run.log').open('w', encoding='utf-8') as log:
            subprocess.run(list(map(str, [node, out/test, '--firmware', folder, '--streams', corpus/profile/'streams',
                '--oracle', corpus/profile/'oracle', *(['--packet-timing'] if mode == 'raw' else [])])),
                stdout=log, stderr=subprocess.STDOUT, check=True)
        print('PASS', name, mode, profile, flush=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, [(n, m, p) for n in ['baseline', 'shared', 'phase'] for m in ['raw', 'irq'] for p in PROFILES]))


def audit(out, corpus, receipt):
    for key, digest in BASE_IMAGES.items():
        assert sha(out/'whole/baseline'/key/'wb.bin') == digest
    isolated = {}
    base = read(out/'baseline-unit/verification.json')
    for name, delta, extra8, extra10, own in [('baseline', 0, 0, 0, 20), ('local', -200, 280, 280, 22),
                                            ('shared', -308, 280, 280, 22), ('phase', -212, 120, 130, 20)]:
        assert sha(out/name/'src/iir_kernel.inc', True) == KERNELS[name]
        r, irq = read(out/(name+'-unit/verification.json')), read(out/(name+'-irq/verification.json'))
        assert sha(out/(name+'-unit/unit.bin')) == r['binarySha256']
        assert sha(out/(name+'-irq/unit.bin')) == irq['binarySha256']
        assert r['cases'] == 7374 and r['calls'] == 14748 and r['samplesPerPath'] == 294960
        assert r['statePageLowBytes'] == 256 and r['calleeSavedAndR1AtRet'] == 7374
        assert r['ownAsmStackBytes'] == own and r['privateAsmCalls'] == r['privateAsmReturns']
        for order, extra in [('8', extra8), ('10', extra10)]:
            a, b = base['primitiveCyclesIncludingRet'][order]['cycles'], r['primitiveCyclesIncludingRet'][order]['cycles']
            assert len(a) == len(b) and {y-x for x, y in zip(a, b)} == {extra}
        for flag in ['selectedAndExplicitProductionCExact', 'independentBigIntOracle', 'fullSigned16InputNegationSweep',
                     'inPlaceAndSeparate', 'wholeWorkArenaAndGuardsExact']:
            assert r[flag], flag
        for flag in ['everyExecutedBoundaryPreempted', 'all32RegistersAndSregRestoredAtReti',
                     'interruptPcAndSpRestored', 'traceUnchanged']:
            assert irq[flag], flag
        assert irq['injections'] == irq['isrMulInstructions'] and irq['nonzeroR1Interrupts'] > 0
        size = (out/(name+'-unit/unit.bin')).stat().st_size
        assert size-(out/'baseline-unit/unit.bin').stat().st_size == delta
        for obj in ['nb.o', 'wb.o']:
            assert sha(out/(name+'-unit')/obj) == sha(out/'baseline-unit'/obj)
        isolated[name] = dict(flashBytes=size, flashDelta=delta, cyclesAddedOrder8=extra8, cyclesAddedOrder10=extra10,
                              binarySha256=r['binarySha256'], ownStack=own, publicAbiReturns=r['calleeSavedAndR1AtRet'],
                              irqBinarySha256=irq['binarySha256'], irqInjections=irq['injections'], dirtyR1=irq['nonzeroR1Interrupts'],
                              irqPeakStack=irq['peakStackBytes'], deviceHeaders=irq['deviceHeaders'])
    complete, inputs = {}, []
    for profile in PROFILES:
        old = {s['stream']: s for s in read(out/'whole/baseline/raw'/profile/'packet-timing.json')['streams']}
        complete[profile] = {}
        for row in old.values():
            assert sha(corpus/profile/'streams'/row['stream']) == row['inputSha256']
            assert sha(corpus/profile/'oracle'/(Path(row['stream']).stem+'.pcm')) == row['pcmSha256']
            inputs.append(dict(profile=profile, stream=row['stream'], frames=len(row['cycles']),
                               inputSha256=row['inputSha256'], pcmSha256=row['pcmSha256']))
        for name, added, raw_delta, irq_delta in [('baseline', 0, 0, 0), ('shared', 2560, -300, -298), ('phase', 1000, -212, -212)]:
            pair = {}
            for mode in ['raw', 'irq']:
                folder = out/'whole'/name/mode/profile
                r, b = read(folder/'verification.json'), read(out/'whole/baseline'/mode/profile/'verification.json')
                assert sha(folder/'wb.bin') == r['binarySha256'] == read(folder/'backend.json')['binarySha256']
                assert r['flashBytes']-b['flashBytes'] == (raw_delta if mode == 'raw' else irq_delta)
                assert r['staticSramBytes'] == b['staticSramBytes']
                if mode == 'raw':
                    trace = read(folder/'packet-timing.json')
                    assert set(old) == {s['stream'] for s in trace['streams']}
                    assert all(len(s['cycles']) == len(old[s['stream']]['cycles']) for s in trace['streams'])
                    assert {y-x for s in trace['streams'] for x, y in zip(old[s['stream']]['cycles'], s['cycles'])} == {added}
                    assert all(s['pcmExact'] and s['reset'] for s in r['streams'])
                    assert r['peakStack'] == b['peakStack']
                    pair[mode] = {k: r[k] for k in ['binarySha256', 'frames', 'flashBytes', 'staticSramBytes', 'meanCycles', 'maxCycles', 'peakStack', 'freeSram']}
                else:
                    assert r['includesInterrupts'] and r['extraCpuCyclesPerFrame'] == 25600 and r['underruns'] == 0
                    assert all(s['s16AndPwmExact'] and s['underruns'] == 0 for s in r['streams'])
                    assert r['freeSramAtPeak'] == b['freeSramAtPeak']
                    pair[mode] = {k: r[k] for k in ['binarySha256', 'frames', 'flashBytes', 'staticSramBytes', 'underruns', 'freeSramAtPeak', 'minQueuedSamplesBeforeOutput']}
                    pair[mode]['peakStack'] = max(s['peakStackBytes'] for s in r['streams'])
            complete[profile][name] = pair
    ref = out/'reference'
    used = [p for p in (ref/'Codecs/Speex/AVR/src').iterdir() if p.is_file()]
    used += [p for p in (ref/'Codecs/common').rglob('*') if p.is_file()]
    tests = ['tests/screen_iir_output_size.py', 'tools/build_iir_block_test.py', 'tests/avr_iir_block.c',
             'tests/iir_nb_forced_c.c', 'tests/verify_iir_block.mjs', 'tests/verify_wb.mjs',
             'tests/verify_wb_stream.mjs', 'tests/avr_tick.mjs', 'tools/build.py',
             'tools/build_wb.py', 'tools/build_wb_stream_test.py', 'tools/apply_profile.py']
    generated = {p.relative_to(out/'generated-source').as_posix(): sha(p, True)
                 for p in (out/'generated-source').rglob('*') if p.is_file()}
    generated_digest = hashlib.sha256(json.dumps(generated, sort_keys=True).encode()).hexdigest()
    result = dict(scope='Frozen IIR factoring, scalar C/ASM/state/IRQ and complete ASM screens',
                  baseline='1da660ea', sourceHashNormalization='CRLF to LF; external tools/headers/images/objects exact bytes',
                  compiler='AVR GCC7.3.0', options=['-Os', '-flto', '-mcall-prologues', '-mrelax', '-fwrapv', '-fno-strict-aliasing'],
                  kernelSha256=KERNELS, frozenSourceSha256={p.relative_to(ref).as_posix(): sha(p, True) for p in sorted(used)},
                  admittedBaselineImages=BASE_IMAGES, baselineRebuiltIdentically=True,
                  testSourceSha256={n: sha(ROOT/n, True) for n in tests}, isolated=isolated, completeScreens=complete,
                  generatedSourceFiles=len(generated), generatedSourceTreeSha256=generated_digest,
                  screenInputs=inputs, cObjectSha256={n: sha(out/'baseline-unit'/n) for n in ['nb.o', 'wb.o']},
                  fullCDecoderExecuted=False, fullFiveRateAdmission=False, physicalBoardTested=False,
                  limits=['WB3.95:18 streams capped at64 frames; WB12.8:one64-frame prefix.',
                          'Production queue/timer screens use ready RAM plus8% extra work; no transport latency.'])
    if (out/'phase-cleanup-identity.json').exists():
        cleanup = read(out/'phase-cleanup-identity.json')
        assert cleanup['allSixImagesByteIdentical'] and not cleanup['simulationsRepeated']
        assert all(sha(out/n) == h for n, h in cleanup['images'].items())
        cleanup.update(beforeKernelSha256='2581261f199e6eef33acf76701c8372c5fee3b762bf3a7f8294a6a54008746be',
                       afterKernelSha256=KERNELS['phase'], removedDefinition='IIR_FINISH', remainingInvocations=0)
        result['phaseUnusedMacroCleanup'] = cleanup
    if (out/'toolchain.json').exists():
        result['externalToolSha256ExactBytes'] = read(out/'toolchain.json')
    if (out/'avr8js-runtime.json').exists():
        runtime = read(out/'avr8js-runtime.json')
        assert runtime['version'] == '0.21.1'
        result['avr8jsExactBytes'] = runtime
    save(out/'summary.json', result)
    if receipt:
        save(receipt, result)
    print('PASS IIR size screen: phase -212B/+1000 cycles/frame, unchanged stack, exact loaded output')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['prepare', 'build', 'verify', 'whole-build', 'whole-run', 'audit', 'all'], default='all')
    parser.add_argument('--out', type=Path, default=ROOT/'build/filter-size-next')
    parser.add_argument('--source-root', type=Path, default=ROOT)
    parser.add_argument('--avr-gcc')
    parser.add_argument('--node')
    parser.add_argument('--profile-cache', type=Path)
    parser.add_argument('--avr8js-entry', type=Path)
    parser.add_argument('--corpus', type=Path)
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    out = args.out.resolve();out.mkdir(parents=True, exist_ok=True)
    if args.avr8js_entry:
        package = args.avr8js_entry.resolve().parents[2]
        save(out/'avr8js-runtime.json', dict(version=read(package/'package.json')['version'],
             sha256={p.relative_to(package).as_posix(): sha(p) for p in [package/'package.json',
                     *sorted((package/'dist/cjs').rglob('*.js'))]}))
    if args.avr_gcc and args.node:
        common.toolchain(out, args.avr_gcc, args.node)
    if args.phase in ['prepare', 'all']:
        if not args.profile_cache or not args.avr8js_entry:
            parser.error('prepare needs --profile-cache and --avr8js-entry')
        prepare(out, args.source_root.resolve(), args.profile_cache.resolve(), args.avr8js_entry)
    if args.phase in ['build', 'all']:
        if not args.avr_gcc:
            parser.error('build needs --avr-gcc')
        build_primitive(out, args.avr_gcc)
    if args.phase in ['verify', 'all']:
        if not args.node:
            parser.error('verify needs --node')
        run_primitive(out, args.node)
    if args.phase in ['whole-build', 'all']:
        if not args.avr_gcc:
            parser.error('whole-build needs --avr-gcc')
        whole_build(out, args.avr_gcc)
    if args.phase in ['whole-run', 'all']:
        if not args.node or not args.corpus:
            parser.error('whole-run needs --node and --corpus')
        whole_run(out, args.node, args.corpus.resolve())
    if args.phase in ['audit', 'whole-run', 'all']:
        if not args.corpus:
            parser.error('audit needs --corpus')
        audit(out, args.corpus.resolve(), args.receipt)


if __name__ == '__main__':
    main()
