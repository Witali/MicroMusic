#!/usr/bin/env python3
"""Screen exact split-H/L QMF accumulation without changing production files.

Isolated explicit C filter primitives may execute. Complete decoder runs are
ASM only. Whole-image builds replace only the wb_qmf.S compiler argument.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

import screen_qmf_common_product as common

ROOT = Path(__file__).resolve().parents[1]
KERNEL_SHA = {
    'baseline': 'cb6eafb62f2d9d46b4848ea9d5d6ec8dd070fa42d533cf9747d44c35f87a73e9',
    'stack': '85789b70d8b94a4ba48f105876c45ef1272a5dcf26b2309dfe8f94ed71e48f26',
    'mirror': '529bcb7148ae04b80237028b242f3a74344cfd1567066d9bae396cbc76ced676',
}
PROFILES = {'wb395': 10, 'wb128': 32}
MACROS = r'''/* Split exact accumulation: L is biased unsigned16, H is signed16-54.
 * Llo,Lhi,Hlo,Hhi use four registers. r30 holds54 during first products. */
.macro WB_MAC a,b,c,d,coefficient,first=0
    ldi r20,lo8(\coefficient)
    muls r20,r24
    .if \first
    movw \c,r0
    sub \c,r30
    sbc \d,r2
    .else
    add \c,r0
    adc \d,r1
    .endif
    mulsu r20,r21
    .if \first
    movw \a,r0
    add \b,r30
    .else
    add \a,r0
    adc \b,r1
    .endif
.endm
.macro WB_PAIR_7_MINUS14 a,b,c,d,e,f,g,h
    ldi r20,7
    muls r20,r24
    add \c,r0
    adc \d,r1
    lsl r0
    rol r1
    sub \g,r0
    sbc \h,r1
    mulsu r20,r21
    add \a,r0
    adc \b,r1
    lsl r0
    rol r1
    sub \e,r0
    sbc \f,r1
.endm
'''


def sha(path, text=False):
    return common.sha(path, text)


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2)+'\n', encoding='utf-8')


def split_kernel(text, mirror=False):
    def replace(before, after):
        nonlocal text
        assert text.count(before) == 1, before
        text = text.replace(before, after)
    start, end = text.index('/* first=1 initializes'), text.index('/* r20=128 on entry')
    text = text[:start]+MACROS+text[end:]
    replace('    WB_PAIR_MINUS10_15 r7,r8,r9,r13,r14,r15',
            '    WB_MAC r7,r8,r9,-10\n    WB_MAC r13,r14,r15,15')
    replace('    WB_PAIR_MINUS10_15 r10,r11,r12,r4,r5,r6',
            '    WB_MAC r10,r11,r12,-10\n    WB_MAC r4,r5,r6,15')
    for old, new in [('r4,r5,r6', 'r4,r5,r6,r7'), ('r7,r8,r9', 'r8,r9,r10,r11'),
                     ('r10,r11,r12', 'r12,r13,r14,r15'), ('r13,r14,r15', 'r16,r17,r18,r19')]:
        text = text.replace('    WB_MAC '+old+',', '    WB_MAC '+new+',')
    replace('    WB_PAIR_7_MINUS14 r4,r5,r6,r10,r11,r12',
            '    WB_PAIR_7_MINUS14 r4,r5,r6,r7,r12,r13,r14,r15')
    replace('    WB_PAIR_7_MINUS14 r13,r14,r15,r7,r8,r9',
            '    WB_PAIR_7_MINUS14 r16,r17,r18,r19,r8,r9,r10,r11')
    replace('    WB_INPUT\n    WB_INPUT\n',
            '    WB_INPUT\n    WB_INPUT\n    push r16\n    push r17\n'
            '    push r18\n    push r19\n    ldi r30,54\n')
    replace('    movw r30,r22\n    WB_FINISH r4,r5,r6\n    WB_FINISH r7,r8,r9\n'
            '    WB_FINISH r10,r11,r12\n    WB_FINISH r13,r14,r15\n    movw r22,r30',
            '    movw r30,r22\n    add r6,r5\n    adc r7,r2\n    WB_FINISH r4,r6,r7\n'
            '    add r10,r9\n    adc r11,r2\n    WB_FINISH r8,r10,r11\n'
            '    add r14,r13\n    adc r15,r2\n    WB_FINISH r12,r14,r15\n'
            '    add r18,r17\n    adc r19,r2\n    WB_FINISH r16,r18,r19\n'
            '    movw r22,r30\n    pop r19\n    pop r18\n    pop r17\n    pop r16')
    if mirror:
        replace('    push r16\n    push r17\n    push r18\n    push r19\n    ldi r30,54',
                '    cp r28,r25\n    brne .Lcursor\n    sbiw r28,32\n.Lcursor:\n'
                '    std Y+32,r16\n    std Y+33,r17\n    std Y+34,r18\n'
                '    std Y+35,r19\n    ldi r30,54')
        replace('    movw r26,r28\n    adiw r26,32\n    cp r28,r25\n'
                '    brne .Lcursor\n    sbiw r28,32\n.Lcursor:',
                '    movw r26,r28\n    adiw r26,32')
        replace('    pop r19\n    pop r18\n    pop r17\n    pop r16',
                '    ldd r16,Y+32\n    ldd r17,Y+33\n    ldd r18,Y+34\n    ldd r19,Y+35')
        replace('.Ldone:\n    clr r1',
                '.Ldone:\n    ld r16,Y\n    ldd r17,Y+1\n    ldd r18,Y+2\n    ldd r19,Y+3\n'
                '    std Y+32,r16\n    std Y+33,r17\n    std Y+34,r18\n    std Y+35,r19\n    clr r1')
    key = 'mirror' if mirror else 'stack'
    assert hashlib.sha256(text.encode()).hexdigest() == KERNEL_SHA[key]
    return text


def arithmetic_proof(source):
    table = re.search(r'static const int8_t h\[16\] AVR_TABLE=\{(.*?)\}',
                      source.read_text(encoding='utf-8'), re.S)
    assert table, 'Pinned QMF coefficient declaration'
    coefficients = list(map(int, re.findall(r'-?\d+', table.group(1))))
    assert coefficients == [-4, -10, 7, 15, -14, -26, 37, 123, 123, 37, -26, -14, 15, 7, -10, -4]
    checks = subsets = windows = 0
    for c in sorted(set(coefficients)):
        for x in range(-32768, 32768):
            hi, lo = x >> 8, x & 255
            assert c*x == (c*hi)*256+c*lo
            assert -32768 <= c*hi <= 32767 and -32768 <= c*lo <= 32767
            h, low = c*hi-54, 13824+c*lo
            assert -32768 <= h <= 32767 and 0 <= low <= 65535
            assert (h+(low >> 8))*256+(low & 255) == c*x
            checks += 1
    for phase in [coefficients[::2], coefficients[1::2]]:
        assert sum(max(c, 0) for c in phase) == 182
        assert sum(-min(c, 0) for c in phase) == 54
        # Every possible partial subset, so the bounds do not depend on MAC order.
        for mask in range(256):
            pos = sum(max(c, 0) for i, c in enumerate(phase) if mask & (1 << i))
            neg = sum(-min(c, 0) for i, c in enumerate(phase) if mask & (1 << i))
            hmin, hmax = -128*pos-127*neg-54, 127*pos+128*neg-54
            lmin, lmax = 13824-255*neg, 13824+255*pos
            assert -32768 <= hmin <= hmax <= 32767
            assert 0 <= lmin <= lmax <= 65535
            assert -32768 <= hmin+(lmin >> 8) <= hmax+(lmax >> 8) <= 32767
            subsets += 1
    for low in range(256):
        base = 0x300+low
        for offset in [0, 8, 16, 24]:
            advanced = base+offset+8
            wrap = (advanced & 255) == ((base+32) & 255)
            assert wrap == (offset == 24)
            y = advanced-32 if wrap else advanced
            assert 0 <= y-base <= 24 and y+35 < base+64
            old_start = advanced
            for k in range(32):
                assert ((old_start+k-base) & 31) == ((y+k-base) & 31)
            windows += 1
    logical = bytearray(range(32)); state = logical*2; y = 0
    for block in range(20):
        for sample in range(2):
            value = bytes(((block*8+sample*4+i+117) & 255) for i in range(4))
            logical[y:y+4] = value;state[y:y+4] = value;state[y+32:y+36] = value;y += 4
        if y == 32:
            y = 0
        assert state == logical*2
        expected = bytes(state[y:y+32])
        state[y+32:y+36] = b'PTR!'
        assert bytes(state[y:y+32]) == expected
    state[y+32:y+36] = state[y:y+4]
    assert y == 0 and state == logical*2
    return dict(scalarByteProductChecks=checks, allPartialCoefficientSubsets=subsets,
                highSumRange=[-30154, 30026], biasedHighRange=[-30208, 29972],
                lowSumRange=[54, 60234], geometryBaseLowBytes=256, geometryWindows=windows,
                deadMirrorSteps=20, finalPublicMirrorStateExact=True)


def prepare(out):
    assert sha(ROOT/'src/wb_qmf.S', True) == KERNEL_SHA['baseline'], 'QMF baseline changed'
    for name in KERNEL_SHA:
        shutil.copytree(ROOT/'src', out/name/'src', dirs_exist_ok=True)
        if name != 'baseline':
            path = out/name/'src/wb_qmf.S'
            path.write_text(split_kernel(path.read_text(encoding='utf-8'), name == 'mirror'),
                            encoding='utf-8', newline='\n')
    (out/'qmf_fixture.c').write_text(common.fixture_text(), encoding='utf-8', newline='\n')
    (out/'verify_cases.mjs').write_text(common.verifier_text(), encoding='utf-8', newline='\n')


def primitive_phase(out, phase, gcc, node):
    recipes = common.KERNEL_SHA
    try:
        # Reuse the existing fixture compiler/runner with this private process's
        # recipe list. Their algorithms and production fallback stay unchanged.
        common.KERNEL_SHA = KERNEL_SHA
        (common.build(out, gcc) if phase == 'build' else common.verify(out, node))
    finally:
        common.KERNEL_SHA = recipes


def whole_build(out, reference, gcc):
    sys.path.insert(0, str(ROOT/'tools'))
    import build
    import build_wb
    import build_wb_stream_test
    expected = read(reference/'after-source.json')
    assert all(sha(ROOT/n, True) == h for n, h in expected.items())
    generated = ROOT/'build/profile/source'
    cache = {str(p.relative_to(generated)): sha(p, True) for p in generated.rglob('*') if p.is_file()}
    original_run, original_prepare = build.run, build_wb.prepare
    original_argv = sys.argv
    counts = {}
    try:
        # Reuse the already prepared cache; baseline binary identity below binds
        # it to the reference. Do not modify a shared preparation directory.
        build_wb.prepare = lambda: generated
        for name in KERNEL_SHA:
            counts[name] = 0
            def run(argv, cwd=None):
                args = []
                for arg in argv:
                    if str(arg).replace('\\', '/') == str(ROOT/'src/wb_qmf.S').replace('\\', '/'):
                        counts[name] += 1
                        args.append(arg if name == 'baseline' else out/name/'src/wb_qmf.S')
                    else:
                        args.append(arg)
                return original_run(args, cwd=cwd)
            build.run = run
            for label, width in PROFILES.items():
                folder = out/'whole'/name/'raw'/label
                build_wb.avr(gcc, 'asm', packet_bytes=width, enable_nb4=True, low_rates=7, destination=folder)
                sys.argv = ['build_wb_stream_test.py', '--avr-gcc', gcc, '--packet-bytes', str(width),
                            '--low-rates', '7', '--enable-nb4', '--frame-load-cycles', '25600',
                            '--out', str(out/'whole'/name/'irq'/label)]
                build_wb_stream_test.main()
                if name == 'baseline':
                    for part, epoch in [('raw', 'after'), ('irq', 'irq')]:
                        assert (out/'whole'/name/part/label/'wb.bin').read_bytes() == (reference/epoch/label/'wb.bin').read_bytes()
            assert counts[name] == 4
    finally:
        build.run, build_wb.prepare, sys.argv = original_run, original_prepare, original_argv
    assert all(sha(ROOT/n, True) == h for n, h in expected.items())
    assert cache == {str(p.relative_to(generated)): sha(p, True) for p in generated.rglob('*') if p.is_file()}
    save(out/'whole/build-receipt.json', dict(baselineImagesRebuiltIdentically=True,
         onlyCompilerSourceArgumentReplaced='src/wb_qmf.S', substitutions=counts,
         baselineSourceSha256=expected, cachedSourceUnchanged=True))


def whole_run(out, reference, node):
    for part, epoch in [('raw', 'after'), ('irq', 'irq')]:
        for label in PROFILES:
            source, dest = reference/'runs/screen'/epoch/label, out/'whole/baseline'/part/label
            assert (source/'wb.bin').read_bytes() == (dest/'wb.bin').read_bytes()
            for filename in ['verification.json', *(['packet-timing.json'] if part == 'raw' else [])]:
                shutil.copyfile(source/filename, dest/filename)
    def run(task):
        name, part, label = task
        folder, data = out/'whole'/name/part/label, reference/'data/screen'/label
        test = 'verify_wb.mjs' if part == 'raw' else 'verify_wb_stream.mjs'
        with (folder/'run.log').open('w', encoding='utf-8') as log:
            subprocess.run(list(map(str, [node, ROOT/'tests'/test, '--firmware', folder,
                '--streams', data/'streams', '--oracle', data/'oracle',
                *(['--packet-timing'] if part == 'raw' else [])])), stdout=log, stderr=subprocess.STDOUT, check=True)
        print('PASS', name, part, label, flush=True)
    tasks = [(n, p, l) for n in ['stack', 'mirror'] for p in ['raw', 'irq'] for l in PROFILES]
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, tasks))


def image(folder, filename):
    report, meta = read(folder/filename), read(folder/'input.json')
    assert sha(folder/'wb.bin') == report['binarySha256'] == meta['binarySha256']
    return report


def audit(out, reference, receipt):
    assert (out/'qmf_fixture.c').read_text(encoding='utf-8') == common.fixture_text()
    assert (out/'verify_cases.mjs').read_text(encoding='utf-8') == common.verifier_text()
    sources = {}
    for path in sorted((out/'baseline/src').iterdir()):
        if path.is_file():
            sources['src/'+path.name] = sha(path, True)
            for name in ['stack', 'mirror']:
                if path.name != 'wb_qmf.S':
                    assert path.read_bytes() == (out/name/'src'/path.name).read_bytes(), path.name
    rows = {}
    for name, saving, flash, own, peak in [('baseline', 0, 0, 18, 31), ('stack', 500, -74, 22, 35), ('mirror', 484, -58, 18, 31)]:
        assert sha(out/name/'src/wb_qmf.S', True) == KERNEL_SHA[name]
        r = image(out/(name+'-unit'), 'verification.json')
        irq = image(out/(name+'-irq'), 'irq-verification.json')
        before = read(out/'baseline-unit/verification.json')
        assert len(r['streams']) == 2 and r['fullSigned16InputPairs'] == 65536
        for a, b in zip(before['streams'], r['streams']):
            assert a['kernel'] == b['kernel'] and b['blocks'] == 2244 and b['samples'] == 179520
            assert b['guards'] and b['pcmExact'] and b['readOnlyInputs'] and b['mirroredHistoryExact'] and b['aliasQmf']
            assert b['qmfRoundingAndClippingBoundaryBlocks'] == 92
            assert len(a['cycleSamples']) == len(b['cycleSamples']) == 2244
            expected = saving if b['kernel'].endswith('_avr') else 0
            assert {x-y for x, y in zip(a['cycleSamples'], b['cycleSamples'])} == {expected}
        assert irq['ownAsmStackBytes'] == own and irq['wholeProbePeakStackBytes'] == peak
        assert irq['cases'] == 8 and irq['asmReturns'] == 16 and irq['injections'] == irq['isrMulInstructions']
        assert irq['nonzeroR1Interrupts'] > 0
        for flag in ['full32RegistersAndSregRestored', 'interruptPcAndSpRestored', 'traceUnchanged',
                     'calleeSavedAndR1Exact', 'wholeArenaInputsGuardsAndMirroredStateExact',
                     'bothIncomingTValues', 'permittedAliasAndSeparate']:
            assert irq[flag], flag
        assert {v['muls'] for v in irq['vectors']} == ({1120} if name == 'baseline' else {1200})
        size = (out/(name+'-unit/wb.bin')).stat().st_size
        assert size-(out/'baseline-unit/wb.bin').stat().st_size == flash
        assert sha(out/(name+'-unit/qmf_c.o')) == sha(out/'baseline-unit/qmf_c.o')
        rows[name] = dict(pairedBlockSaving=saving, flashBytes=size, ownAsmStack=own, irqProbeStack=peak,
                          binarySha256=r['binarySha256'], irqBinarySha256=irq['binarySha256'],
                          injections=irq['injections'], dirtyR1Interrupts=irq['nonzeroR1Interrupts'],
                          mulsPerCall=irq['vectors'][0]['muls'],
                          deviceHeaderSha256ExactBytes=read(out/(name+'-unit/input.json'))['headers'])
    builder = read(out/'whole/build-receipt.json')
    assert builder['baselineImagesRebuiltIdentically'] and builder['cachedSourceUnchanged']
    assert builder['onlyCompilerSourceArgumentReplaced'] == 'src/wb_qmf.S'
    whole = {}
    inputs = []
    for label in PROFILES:
        old_trace = read(out/'whole/baseline/raw'/label/'packet-timing.json')
        old = {r['stream']: r for r in old_trace['streams']}
        for filename, row in old.items():
            raw, pcm = reference/'data/screen'/label/'streams'/filename, reference/'data/screen'/label/'oracle'/(Path(filename).stem+'.pcm')
            assert sha(raw) == row['inputSha256'] and sha(pcm) == row['pcmSha256']
            inputs.append(dict(profile=label, stream=filename, inputSha256=sha(raw), pcmSha256=sha(pcm), frames=len(row['cycles'])))
        whole[label] = {}
        for name, saving, flash in [('baseline', 0, 0), ('stack', 2000, -74), ('mirror', 1936, -58)]:
            reports = {}
            for part in ['raw', 'irq']:
                folder = out/'whole'/name/part/label
                r, meta = read(folder/'verification.json'), read(folder/'backend.json')
                assert sha(folder/'wb.bin') == r['binarySha256'] == meta['binarySha256']
                base = read(out/'whole/baseline'/part/label/'verification.json')
                assert r['flashBytes']-base['flashBytes'] == flash and r['staticSramBytes'] == base['staticSramBytes']
                if part == 'raw':
                    trace = read(folder/'packet-timing.json')
                    assert set(old) == {row['stream'] for row in trace['streams']}
                    assert all(len(row['cycles']) == len(old[row['stream']]['cycles']) for row in trace['streams'])
                    assert {a-b for row in trace['streams'] for a, b in zip(old[row['stream']]['cycles'], row['cycles'])} == {saving}
                    assert r['frames'] == sum(len(row['cycles']) for row in old.values())
                    assert all(row['pcmExact'] and row['reset'] for row in r['streams'])
                    reports[part] = {k: r[k] for k in ['binarySha256', 'frames', 'meanCycles', 'maxCycles', 'flashBytes', 'staticSramBytes', 'peakStack', 'freeSram']}
                else:
                    assert r['includesInterrupts'] and r['extraCpuCyclesPerFrame'] == 25600 and r['underruns'] == 0
                    assert r['frames'] == sum(len(row['cycles']) for row in old.values())
                    assert set(old) == {row['stream'] for row in r['streams']}
                    assert all(row['inputSha256'] == old[row['stream']]['inputSha256'] and
                               row['pcmSha256'] == old[row['stream']]['pcmSha256'] for row in r['streams'])
                    assert r['freeSramAtPeak'] > 0 and all(s['s16AndPwmExact'] and s['underruns'] == 0 for s in r['streams'])
                    reports[part] = {k: r[k] for k in ['binarySha256', 'frames', 'flashBytes', 'staticSramBytes', 'freeSramAtPeak', 'minQueuedSamplesBeforeOutput', 'underruns', 'extraCpuCyclesPerFrame']}
                    reports[part]['peakStack'] = max(s['peakStackBytes'] for s in r['streams'])
                    reports[part]['timerIntervalMinCycles'] = min(s['timerIntervalMinCycles'] for s in r['streams'])
                    reports[part]['timerIntervalMaxCycles'] = max(s['timerIntervalMaxCycles'] for s in r['streams'])
            whole[label][name] = reports
    tests = ['tests/screen_qmf_split_accum.py', 'tests/screen_qmf_common_product.py',
             'tests/verify_qmf_common_product_irq.mjs', 'tests/wb_kernels.c', 'tests/verify_wb_kernels.mjs',
             'tests/verify_wb.mjs', 'tests/verify_wb_stream.mjs', 'tests/avr_tick.mjs']
    result = dict(scope='Isolated QMF and complete WB3.95/WB12.8 matched screens; production files unchanged',
                  textHashNormalization='CRLF to LF; tool/header/binary/C-object hashes exact bytes',
                  kernelSha256=KERNEL_SHA, baselineSourceSha256=sources,
                  testSourceSha256={p: sha(ROOT/p, True) for p in tests},
                  arithmeticProof=arithmetic_proof(out/'baseline/src/wb_qmf.c'), isolated=rows, wholeScreens=whole, screenInputs=inputs,
                  wholeBuildReceiptSha256=sha(out/'whole/build-receipt.json'),
                  explicitCObjectSha256=sha(out/'baseline-unit/qmf_c.o'), fullCDecoderExecuted=False,
                  fullCorpusAdmitted=False, physicalBoardTested=False,
                  limits=['WB3.95 uses18 streams capped at64 frames each.',
                          'WB12.8 uses one64-frame prefix of the retained long recording.',
                          'IRQ screens model ready RAM packets and8% extra foreground work; no transport latency.'])
    if (out/'toolchain.json').exists():
        result['externalToolSha256ExactBytes'] = read(out/'toolchain.json')
    save(out/'summary.json', result)
    if receipt:
        save(receipt, result)
    print('PASS split QMF: -500/-484 cycles per block; -2000/-1936 per complete screened frame; IRQ output exact')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['prepare', 'build', 'verify', 'whole-build', 'whole-run', 'audit', 'all'], default='all')
    parser.add_argument('--out', type=Path, default=ROOT/'build/qmf-split-accum-screen')
    parser.add_argument('--reference-stage', type=Path, default=ROOT/'build/hb-finite-speed')
    parser.add_argument('--avr-gcc')
    parser.add_argument('--node')
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    out, reference = args.out.resolve(), args.reference_stage.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if args.avr_gcc and args.node:
        common.toolchain(out, args.avr_gcc, args.node)
    if args.phase in ['prepare', 'all']:
        prepare(out)
    for phase in ['build', 'verify']:
        if args.phase in [phase, 'all']:
            if not (args.avr_gcc if phase == 'build' else args.node):
                parser.error('--avr-gcc/--node is required for the selected phase')
            primitive_phase(out, phase, args.avr_gcc, args.node)
    if args.phase in ['whole-build', 'all']:
        if not args.avr_gcc:
            parser.error('--avr-gcc is required for whole-build')
        whole_build(out, reference, args.avr_gcc)
    if args.phase in ['whole-run', 'all']:
        if not args.node:
            parser.error('--node is required for whole-run')
        whole_run(out, reference, args.node)
    if args.phase in ['audit', 'whole-run', 'all']:
        audit(out, reference, args.receipt)


if __name__ == '__main__':
    main()
