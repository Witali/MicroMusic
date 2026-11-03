#!/usr/bin/env python3
"""Reproduce the isolated second-last-old-coefficient IIR cache experiment.

Production sources are never edited. Only isolated C/ASM filter primitives
execute; this driver does not build or run the full Speex C decoder.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE_KERNEL_SHA = '0c2ab6382ebfe97cdcd412db62809ad1149d3861d790e73baf4696f0e30a982e'
CANDIDATE_KERNEL_SHA = '193437dbc79dabc3a710ee062f0714a1896d53e16d29ec7d6674551607e7cda9'
FIXTURES = [('baseline-unit', 'baseline', False),
            ('candidate-unit', 'candidate', False),
            ('candidate-irq', 'candidate', True)]


def sha(path, text=False):
    data = path.read_bytes()
    return hashlib.sha256(data.replace(b'\r\n', b'\n') if text else data).hexdigest()


def candidate_kernel(text):
    def replace(before, after):
        nonlocal text
        assert text.count(before) == 1, before
        text = text.replace(before, after)
    replace('    movw r12, r18\n    movw r28,r18', '    movw r28,r18')
    replace('    /* Exactly order warm samples update all coefficient ages. Y wraps\n',
            '    /* r12:r13 cache the second-last old age until output order-2.\n'
            '     * T records the final warm phase; no arithmetic here changes T. */\n'
            '    ldd r12,Y+(6*IIR_ORDER-4)\n'
            '    ldd r13,Y+(6*IIR_ORDER-3)\n'
            '    clt\n'
            '    /* Exactly order warm samples update all coefficient ages. Y wraps\n')
    replace('    ldi r18,IIR_ORDER\n    mov r3,r18\n.Lwarm_sample:',
            '    ldi r18,IIR_ORDER-1\n    mov r3,r18\n.Lwarm_sample:')
    replace('    .rept IIR_ORDER-2\n    IIR_MAC memory\n    .endr\n    IIR_MAC r16,0,16,17',
            '    .rept IIR_ORDER-3\n    IIR_MAC memory\n    .endr\n'
            '    IIR_MAC r12\n    IIR_MAC r16,0,16,17')
    replace('    dec r3\n    breq .Lsteady_setup\n    rjmp .Lwarm_sample\n'
            '.Lsteady_setup:\n    movw r28,r12',
            '    dec r3\n    breq .Lwarm_phase\n    rjmp .Lwarm_sample\n'
            '.Lwarm_phase:\n    brts .Lsteady_setup\n    movw r12,r18\n'
            '    set\n    inc r3\n    rjmp .Lwarm_sample\n'
            '.Lsteady_setup:\n    sbiw r28,2*IIR_ORDER')
    assert hashlib.sha256(text.encode()).hexdigest() == CANDIDATE_KERNEL_SHA
    return text


def prepare(out):
    assert sha(ROOT/'src/iir_kernel.inc', True) == BASE_KERNEL_SHA, 'The baseline kernel changed'
    for name in ['baseline', 'candidate']:
        shutil.copytree(ROOT/'src', out/name/'src', dirs_exist_ok=True)
    kernel = out/'candidate/src/iir_kernel.inc'
    kernel.write_text(candidate_kernel(kernel.read_text(encoding='utf-8')),
                      encoding='utf-8', newline='\n')


def run_logged(command, log):
    with log.open('w', encoding='utf-8') as stream:
        subprocess.run(list(map(str, command)), stdout=stream, stderr=subprocess.STDOUT, check=True)


def audit(out):
    assert sha(out/'baseline/src/iir_kernel.inc', True) == BASE_KERNEL_SHA
    assert sha(out/'candidate/src/iir_kernel.inc', True) == CANDIDATE_KERNEL_SHA
    sources = {}
    for path in sorted((out/'baseline/src').iterdir()):
        if path.is_file():
            sources['src/'+path.name] = sha(path, True)
            if path.name != 'iir_kernel.inc':
                assert path.read_bytes() == (out/'candidate/src'/path.name).read_bytes(), path.name
    reports, images = {}, {}
    for name, _, _ in FIXTURES:
        folder = out/name
        metadata = json.loads((folder/'backend.json').read_text(encoding='utf-8'))
        report = json.loads((folder/'verification.json').read_text(encoding='utf-8'))
        assert sha(folder/'unit.bin') == metadata['binarySha256'] == report['binarySha256']
        reports[name] = report
        end = next(int(line.split()[0], 16) & 65535
                   for line in (folder/'symbols.txt').read_text(encoding='utf-8').splitlines()
                   if line.endswith(' __bss_end'))
        images[name] = dict(binarySha256=report['binarySha256'],
                            flashBytes=(folder/'unit.bin').stat().st_size,
                            staticSramBytes=end-256,
                            deviceHeaderSha256ExactBytes=metadata['headers'])
    before, after, irq = (reports[n] for n in ['baseline-unit', 'candidate-unit', 'candidate-irq'])
    for r in [before, after]:
        assert r['cases'] == 7374 and r['calls'] == 14748
        assert r['samplesPerPath'] == 294960 and r['statePageLowBytes'] == 256
        assert r['calleeSavedAndR1AtRet'] == 7374
        for flag in ['selectedAndExplicitProductionCExact', 'independentBigIntOracle',
                     'fullSigned16InputNegationSweep', 'inPlaceAndSeparate', 'wholeWorkArenaAndGuardsExact']:
            assert r[flag], flag
    assert before['ownAsmStackBytes'] == after['ownAsmStackBytes'] == 20
    assert before['peakStackBytes'] == after['peakStackBytes'] == 32
    measured = {}
    for order, saving in [('8', 12), ('10', 18)]:
        a, b = before['primitiveCyclesIncludingRet'][order], after['primitiveCyclesIncludingRet'][order]
        assert all(a[k]-b[k] == saving for k in ['min', 'max'])
        measured[order] = dict(before=a, after=b, minAndMaxSaving=saving)
    assert images['candidate-unit']['flashBytes']-images['baseline-unit']['flashBytes'] == 24
    assert images['candidate-unit']['staticSramBytes'] == images['baseline-unit']['staticSramBytes']
    assert irq['injections'] == irq['isrMulInstructions'] == 75463
    assert irq['nonzeroR1Interrupts'] == 50077
    for flag in ['everyExecutedBoundaryPreempted', 'all32RegistersAndSregRestoredAtReti',
                 'interruptPcAndSpRestored', 'traceUnchanged', 'wholeWorkArenaAndGuardsExact']:
        assert irq[flag], flag
    c_objects = {}
    for name in ['nb.o', 'wb.o']:
        assert sha(out/'baseline-unit'/name) == sha(out/'candidate-unit'/name)
        c_objects[name] = sha(out/'baseline-unit'/name)
    tests = ['tests/avr_iir_block.c', 'tests/iir_nb_forced_c.c', 'tests/verify_iir_block.mjs',
             'tools/build_iir_block_test.py', 'tests/screen_iir_second_cache.py']
    result = dict(scope='Isolated two-order C/ASM IIR primitives; production decoder unchanged',
                  target='ATmega328P/classic AVR5, GNU ABI, AVR GCC 7.3.0, avr8js 0.21.1',
                  sourceHashNormalization='CRLF to LF; external headers and binary artifacts exact bytes',
                  baselineKernelSha256=BASE_KERNEL_SHA, candidateKernelSha256=CANDIDATE_KERNEL_SHA,
                  baselineSourceSha256=sources,
                  testSourceSha256={n: sha(ROOT/n, True) for n in tests}, images=images,
                  measuredMinAndMaxKernelCycles=measured, addedIsolatedFlashBytes=24,
                  staticSramAndStackUnchanged=True, explicitCObjectsByteIdentical=c_objects,
                  candidateIrqInjections=irq['injections'], dirtyR1Injections=irq['nonzeroR1Interrupts'],
                  expectedWholeWbFrameSavingCycles=120, wholeDecoderSavingMeasured=False,
                  productionOutputTimingAdmitted=False, physicalBoardTested=False,
                  fullCDecoderExecuted=False)
    (out/'summary.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print('PASS isolated second cache: order8 -12 / order10 -18 min/max cycles; +24 B; IRQ exact')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['prepare', 'build', 'verify', 'audit', 'all'], default='all')
    parser.add_argument('--out', type=Path, default=ROOT/'build/iir-second-cache-screen')
    parser.add_argument('--avr-gcc')
    parser.add_argument('--node')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if args.phase in ['prepare', 'all']:
        prepare(out)
    if args.phase in ['build', 'all']:
        if not args.avr_gcc:
            parser.error('--avr-gcc is required to build')
        for name, source, irq in FIXTURES:
            run_logged([sys.executable, ROOT/'tools/build_iir_block_test.py', '--avr-gcc', args.avr_gcc,
                        '--source-root', out/source, '--out', out/name, *(['--irq'] if irq else [])],
                       out/(name+'-build.log'))
    if args.phase in ['verify', 'all']:
        if not args.node:
            parser.error('--node is required to verify')
        for name, _, _ in FIXTURES:
            run_logged([args.node, ROOT/'tests/verify_iir_block.mjs', '--firmware', out/name],
                       out/(name+'-run.log'))
    if args.phase in ['verify', 'audit', 'all']:
        audit(out)


if __name__ == '__main__':
    main()
