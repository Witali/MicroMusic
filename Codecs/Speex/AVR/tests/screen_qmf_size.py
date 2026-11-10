#!/usr/bin/env python3
"""Compare private QMF helper recipes in frozen sources, never production.

Only isolated C primitives execute. Complete decoder and loaded-player runs
select ASM. No full project C decoder executes or is timed.
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
from screen_qmf_split_accum import split_kernel

ROOT = Path(__file__).resolve().parents[1]
KERNELS = {
    'baseline': 'cb6eafb62f2d9d46b4848ea9d5d6ec8dd070fa42d533cf9747d44c35f87a73e9',
    'stack': 'ceb111d259911a4cd7d82288881543390c00e9e0a97a2c507165504d36f9ac27',
    'input': '68a00a353937f65c3b672e7368516f0a424273800974bb4c522137a395b75638',
    'finish': '7507cd190789d48f4fad215d131309778887f6bb3be1ad53b8bbb414e0bea761',
    'both': '57fdc8545d415799a639febff21adc806567a3c21ed06c67d35072e615f4f7b0',
}
PROFILES = {'wb395': 10, 'wb128': 32}
INPUT_HELPER = '''
/* Private fixed-register helper: preserves r0:r1 and X, may keep dirty r1. */
.type qmf_input_private,@function
qmf_input_private:
    WB_INPUT
    ret
.size qmf_input_private,.-qmf_input_private
'''
FINISH_HELPER = '''
/* Private: signed24 input r20,r24,r25; scratch r21; output via Z.
 * r0 retains the main loop's cursor limit across all four calls. */
.type qmf_finish_private,@function
qmf_finish_private:
    ldi r21,32
    add r20,r21
    adc r24,r2
    adc r25,r2
    mov r21,r25
    andi r21,224
    breq .LFconvert
    cpi r21,224
    breq .LFconvert
    sbrc r25,7
    rjmp .LFclipneg
    ldi r20,255
    ldi r24,127
    rjmp .LFstore
.LFconvert:
    .rept 2
    lsl r20
    rol r24
    rol r25
    .endr
    mov r20,r24
    mov r24,r25
    cpi r24,128
    brne .LFstore
    tst r20
    brne .LFstore
.LFclipneg:
    ldi r20,1
    ldi r24,128
.LFstore:
    st Z+,r20
    st Z+,r24
    ret
.size qmf_finish_private,.-qmf_finish_private
'''


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
    text = split_kernel(base)
    if recipe in ['input', 'both']:
        old = '    WB_INPUT\n    WB_INPUT\n'
        assert text.count(old) == 1
        text = text.replace(old, '    rcall qmf_input_private\n    rcall qmf_input_private\n')+INPUT_HELPER
    if recipe in ['finish', 'both']:
        text = text.replace('    movw r30,r22\n    add r6,r5', '    movw r30,r22\n    mov r0,r25\n    add r6,r5')
        for low, high in [('r4', 'r6'), ('r8', 'r10'), ('r12', 'r14'), ('r16', 'r18')]:
            old = '    WB_FINISH '+low+','+high+',r'+str(int(high[1:])+1)
            assert text.count(old) == 1
            text = text.replace(old, '    mov r20,'+low+'\n    movw r24,'+high+'\n    rcall qmf_finish_private')
        old = '    movw r22,r30\n    pop r19'
        assert text.count(old) == 1
        text = text.replace(old, '    mov r25,r0\n'+old)+FINISH_HELPER
    text = text.replace(' * E0 r4..6, O0 r7..9, E1 r10..12, O1 r13..15; low r16:17,\n'
                        ' * high r18:19, out r22:23, zero r2, count r3, cursor end r25.',
                        ' * Split Llo,Lhi,Hlo,Hhi groups: E0 r4..7, O0 r8..11,\n'
                        ' * E1 r12..15, O1 r16..19. Low/high pointers r16..19 spill four bytes\n'
                        ' * across the MAC section; out r22:23, zero r2, count r3, cursor end r25.')
    text = text.replace('    /* The first tap initializes each signed24 accumulator. Consume the\n'
                        '     * saved oldest difference before MUL clobbers r0:r1, then its sum.\n'
                        '     * This also avoids an intermediate copy through r10:r11. */',
                        '    /* Consume the saved oldest difference before MUL clobbers r0:r1,\n'
                        '     * then its sum. Each split accumulator starts with H bias -54\n'
                        '     * and L bias +13824, using the shared r30 constant. */')
    assert hashlib.sha256(text.encode()).hexdigest() == KERNELS[recipe]
    return text


def prepare(out, entry, source):
    # Reject a different production revision before overwriting retained proof
    # sources. A merged-baseline checkout can be supplied after integration.
    assert sha(source/'src/wb_qmf.S', True) == KERNELS['baseline'], 'prepare requires the merged QMF baseline'
    ref = out/'reference/Codecs/Speex/AVR'
    for part in ['src', 'tests']:
        shutil.copytree(source/part, ref/part, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.mid', '*.midi', '*.smf'))
    shutil.copytree(source.parents[1]/'common', out/'reference/Codecs/common', dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.mid', '*.midi', '*.smf'))
    base = (ref/'src/wb_qmf.S').read_text(encoding='utf-8')
    assert sha(ref/'src/wb_qmf.S', True) == KERNELS['baseline']
    for name in KERNELS:
        shutil.copytree(ref/'src', out/name/'src', dirs_exist_ok=True)
        (out/name/'src/wb_qmf.S').write_text(kernel(base, name), encoding='utf-8', newline='\n')
    (out/'qmf_fixture.c').write_text(common.fixture_text(), encoding='utf-8', newline='\n')
    scripts = {'verify_cases.mjs': common.verifier_text(), 'verify_irq.mjs': (ROOT/'tests/verify_qmf_common_product_irq.mjs').read_text(encoding='utf-8')}
    scripts.update({n: (ROOT/'tests'/n).read_text(encoding='utf-8') for n in ['verify_wb.mjs', 'verify_wb_stream.mjs', 'avr_tick.mjs']})
    for name, text in scripts.items():
        (out/name).write_text(text.replace("from 'avr8js'", "from '"+entry.resolve().as_uri()+"'"), encoding='utf-8', newline='\n')
    save(out/'frozen-source.json', {p.relative_to(out/'reference').as_posix(): sha(p, True)
         for p in (out/'reference').rglob('*') if p.is_file()})


def primitive_build(out, gcc):
    original = common.KERNEL_SHA
    try:
        common.KERNEL_SHA = KERNELS
        common.build(out, gcc)
    finally:
        common.KERNEL_SHA = original


def run_tests(out, node, corpus, whole=False):
    def run(task):
        name, mode, profile = task
        folder = out/'whole'/name/mode/profile if whole else out/(name+'-'+mode)
        if whole:
            command = [node, out/('verify_wb.mjs' if mode == 'raw' else 'verify_wb_stream.mjs'),
                       '--firmware', folder, '--streams', corpus/profile/'streams', '--oracle', corpus/profile/'oracle',
                       *(['--packet-timing'] if mode == 'raw' else [])]
        else:
            command = [node, out/'verify_irq.mjs', folder] if mode == 'irq' else [
                node, out/'verify_cases.mjs', '--firmware', folder, '--qmf-only', '--full-inputs']
        with (folder/'run.log').open('w', encoding='utf-8') as log:
            subprocess.run(list(map(str, command)), stdout=log, stderr=subprocess.STDOUT, check=True)
        print('PASS', name, mode, profile, flush=True)
    tasks = [(n, p, l) for n in ['baseline', 'input', 'both'] for p in ['raw', 'irq'] for l in PROFILES] if whole else [
        (n, p, '') for n in KERNELS for p in ['unit', 'irq']]
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, tasks))


def whole_build(out, gcc, cache):
    sys.path.insert(0, str(ROOT/'tools'))
    import build
    import build_wb
    import build_wb_stream_test
    previous = (build.ROOT, build.run, build_wb.prepare, sys.argv)
    ref = out/'reference/Codecs/Speex/AVR'
    try:
        build.ROOT = ref
        build_wb.prepare = lambda: cache
        original = build.run
        for name in ['baseline', 'input', 'both']:
            def run(argv, cwd=None):
                args = [out/name/'src/wb_qmf.S' if str(a).replace('\\', '/') == str(ref/'src/wb_qmf.S').replace('\\', '/') else a for a in argv]
                return original(args, cwd=cwd)
            build.run = run
            for label, width in PROFILES.items():
                build_wb.avr(gcc, 'asm', packet_bytes=width, enable_nb4=True, low_rates=7,
                             destination=out/'whole'/name/'raw'/label)
                sys.argv = ['build_wb_stream_test.py', '--avr-gcc', gcc, '--packet-bytes', str(width),
                            '--low-rates', '7', '--enable-nb4', '--frame-load-cycles', '25600',
                            '--out', str(out/'whole'/name/'irq'/label)]
                build_wb_stream_test.main()
    finally:
        build.ROOT, build.run, build_wb.prepare, sys.argv = previous


def audit(out, corpus, receipt):
    primitive, images = {}, {}
    base = read(out/'baseline-unit/verification.json')['streams']
    for name, saving, delta in [('baseline', 0, 0), ('stack', 500, -74), ('input', 220, -126), ('finish', -260, -224), ('both', -540, -276)]:
        assert sha(out/name/'src/wb_qmf.S', True) == KERNELS[name]
        report = read(out/(name+'-unit/verification.json'))
        assert len(report['streams']) == 2
        for a, b in zip(base, report['streams']):
            assert b['blocks'] == 2244 and b['samples'] == 179520 and b['guards'] and b['readOnlyInputs'] and b['mirroredHistoryExact']
            assert len(a['cycleSamples']) == len(b['cycleSamples']) == 2244
            expected = saving if b['kernel'].endswith('_avr') else 0
            assert {x-y for x, y in zip(a['cycleSamples'], b['cycleSamples'])} == {expected}
        size = (out/(name+'-unit/wb.bin')).stat().st_size
        assert size-(out/'baseline-unit/wb.bin').stat().st_size == delta
        assert sha(out/(name+'-unit/qmf_c.o')) == sha(out/'baseline-unit/qmf_c.o')
        assert sha(out/(name+'-unit/wb.bin')) == report['binarySha256']
        row = dict(flashBytes=size, flashDelta=delta, pairedCyclesSaved=saving,
                   binarySha256=report['binarySha256'], cObjectSha256=sha(out/(name+'-unit/qmf_c.o')))
        irq_path = out/(name+'-irq/irq-verification.json')
        if irq_path.exists():
            irq = read(irq_path)
            assert sha(out/(name+'-irq/wb.bin')) == irq['binarySha256']
            assert all(irq[k] for k in ['full32RegistersAndSregRestored', 'interruptPcAndSpRestored',
                       'traceUnchanged', 'calleeSavedAndR1Exact', 'wholeArenaInputsGuardsAndMirroredStateExact',
                       'bothIncomingTValues', 'permittedAliasAndSeparate'])
            row['irq'] = {k: irq[k] for k in ['binarySha256', 'injections', 'nonzeroR1Interrupts', 'ownAsmStackBytes', 'wholeProbePeakStackBytes', 'deviceHeaders']}
        primitive[name] = row
    inputs = []
    for profile in PROFILES:
        images[profile] = {}
        reference = read(out/'whole/baseline/raw'/profile/'verification.json')
        old = {r['stream']: r for r in read(out/'whole/baseline/raw'/profile/'packet-timing.json')['streams']}
        for row in old.values():
            assert sha(corpus/profile/'streams'/row['stream']) == row['inputSha256']
            assert sha(corpus/profile/'oracle'/(Path(row['stream']).stem+'.pcm')) == row['pcmSha256']
            inputs.append(dict(profile=profile, stream=row['stream'], inputSha256=row['inputSha256'],
                               pcmSha256=row['pcmSha256'], frames=len(row['cycles'])))
        for name, saving, delta in [('baseline', 0, 0), ('input', 880, -126), ('both', -2160, -276)]:
            pair = {}
            for mode in ['raw', 'irq']:
                folder = out/'whole'/name/mode/profile
                r = read(folder/'verification.json')
                assert sha(folder/'wb.bin') == r['binarySha256'] == read(folder/'backend.json')['binarySha256']
                baseline = read(out/'whole/baseline'/mode/profile/'verification.json')
                assert r['flashBytes']-baseline['flashBytes'] == delta
                assert r['staticSramBytes'] == baseline['staticSramBytes']
                if mode == 'raw':
                    trace = read(folder/'packet-timing.json')
                    assert set(old) == {row['stream'] for row in trace['streams']}
                    assert all(len(row['cycles']) == len(old[row['stream']]['cycles']) for row in trace['streams'])
                    assert {x-y for row in trace['streams'] for x, y in zip(old[row['stream']]['cycles'], row['cycles'])} == {saving}
                    assert all(s['pcmExact'] and s['reset'] for s in r['streams'])
                    pair[mode] = {k: r[k] for k in ['binarySha256', 'frames', 'meanCycles', 'maxCycles', 'flashBytes', 'staticSramBytes', 'peakStack', 'freeSram']}
                else:
                    assert r['includesInterrupts'] and r['underruns'] == 0 and r['extraCpuCyclesPerFrame'] == 25600
                    assert r['freeSramAtPeak'] > 0 and all(s['s16AndPwmExact'] for s in r['streams'])
                    pair[mode] = {k: r[k] for k in ['binarySha256', 'frames', 'flashBytes', 'staticSramBytes', 'underruns', 'freeSramAtPeak', 'minQueuedSamplesBeforeOutput']}
                    pair[mode]['peakStack'] = max(s['peakStackBytes'] for s in r['streams'])
            images[profile][name] = pair
    reference = out/'reference'
    compiled = [p for p in (reference/'Codecs/Speex/AVR/src').iterdir() if p.is_file()]
    compiled += [reference/'Codecs/Speex/AVR/tests'/n for n in ['wb_decode.c', 'avr_wb_stream.c']]
    compiled += [p for p in (reference/'Codecs/common').rglob('*') if p.is_file()]
    source = {p.relative_to(reference).as_posix(): sha(p, True) for p in sorted(compiled)}
    tests = ['tests/screen_qmf_size.py', 'tests/screen_qmf_common_product.py', 'tests/screen_qmf_split_accum.py',
             'tests/verify_wb_kernels.mjs', 'tests/verify_qmf_common_product_irq.mjs', 'tests/verify_wb.mjs',
             'tests/verify_wb_stream.mjs', 'tests/avr_tick.mjs']
    report = dict(scope='Frozen QMF size comparison; isolated C primitives and complete ASM screens only',
                  sourceHashNormalization='CRLF to LF; tools/headers/images/C objects exact bytes',
                  compiler='AVR GCC 7.3.0', simulator='avr8js0.21.1',
                  compilerOptions=['-Os', '-mcall-prologues', '-mrelax', '-fwrapv', '-fno-strict-aliasing',
                                   '-flto'],
                  primitiveCFallbackSeparateNonLtoObject=True,
                  kernelSha256=KERNELS, frozenSourceSha256=source,
                  testSourceSha256={n: sha(ROOT/n, True) for n in tests}, primitives=primitive,
                  generatedFixtureSha256=sha(out/'qmf_fixture.c', True),
                  completeScreens=images, screenInputs=inputs, fullCDecoderExecuted=False, physicalBoardTested=False,
                  frozenBaselineRawFlashBytes=images['wb395']['baseline']['raw']['flashBytes'],
                  mergedMainReferenceRawFlashBytes=26164,
                  fullFiveRateAdmission=False,
                  limits=['WB3.95:18 streams capped at64 frames; WB12.8:one64-frame long-recording prefix.',
                          'QMF deltas use the frozen source baseline; its separate optimizations affect total image size.',
                          'Production IRQ screens use ready RAM packets plus8% extra work, without transport latency.'])
    if (out/'toolchain.json').exists():
        report['externalToolSha256ExactBytes'] = read(out/'toolchain.json')
    if (out/'avr8js-runtime.json').exists():
        runtime = read(out/'avr8js-runtime.json')
        assert runtime['version'] == '0.21.1'
        report['avr8jsExactBytes'] = runtime
    save(out/'summary.json', report)
    if receipt:
        save(receipt, report)
    print('PASS QMF size screen: -276 B / +2160 cycles per complete frame, exact loaded IRQ output')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['prepare', 'build', 'verify', 'whole-build', 'whole-run', 'audit', 'all'], default='all')
    parser.add_argument('--out', type=Path, default=ROOT/'build/qmf-size')
    parser.add_argument('--source-root', type=Path, default=ROOT, help='Merged-baseline codec root used to freeze sources')
    parser.add_argument('--avr-gcc')
    parser.add_argument('--node')
    parser.add_argument('--avr8js-entry', type=Path, help='Existing avr8js dist/cjs/index.js; no download')
    parser.add_argument('--profile-cache', type=Path, help='Existing prepared profile/source directory')
    parser.add_argument('--corpus', type=Path, help='Retained data/screen directory with wb395 and wb128')
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
        if not args.avr8js_entry:
            parser.error('prepare needs --avr8js-entry')
        prepare(out, args.avr8js_entry, args.source_root.resolve())
    if args.phase in ['build', 'all']:
        if not args.avr_gcc:
            parser.error('build needs --avr-gcc')
        primitive_build(out, args.avr_gcc)
    if args.phase in ['verify', 'all']:
        if not args.node:
            parser.error('verify needs --node')
        run_tests(out, args.node, args.corpus)
    if args.phase in ['whole-build', 'all']:
        if not args.avr_gcc or not args.profile_cache:
            parser.error('whole-build needs --avr-gcc and --profile-cache')
        whole_build(out, args.avr_gcc, args.profile_cache.resolve())
    if args.phase in ['whole-run', 'all']:
        if not args.node or not args.corpus:
            parser.error('whole-run needs --node and --corpus')
        run_tests(out, args.node, args.corpus.resolve(), whole=True)
    if args.phase in ['audit', 'whole-run', 'all']:
        if not args.corpus:
            parser.error('audit needs --corpus')
        audit(out, args.corpus.resolve(), args.receipt)


if __name__ == '__main__':
    main()
