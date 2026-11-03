#!/usr/bin/env python3
"""Reproduce isolated QMF common-product candidates without production edits.

Only QMF arithmetic primitives execute, including the unchanged explicit C
fallback. No full Speex C decoder is built, executed or timed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
KERNEL_SHA = {
    'baseline': '66af3d39a007be276d7b298cb167ef857bc10da84270a41eb5dee24d35e94350',
    'candidate': '621c138e79aa4b7b08a4cc81c8fc98ab6d3a1343ddf66e9f0ac7dd61073dfe35',
    'combined': 'cb6eafb62f2d9d46b4848ea9d5d6ec8dd070fa42d533cf9747d44c35f87a73e9',
}
MACRO7 = r'''/* P=7*x fits signed24. Z and r20 are dead scratch until WB_FINISH. */
.macro WB_PAIR_7_MINUS14 a,b,c,d,e,f
    ldi r20,7
    muls r20,r24
    movw r30,r0
    mulsu r20,r21
    mov r20,r0
    add r30,r1
    adc r31,r2
    add \a,r20
    adc \b,r30
    adc \c,r31
    lsl r20
    rol r30
    rol r31
    sub \d,r20
    sbc \e,r30
    sbc \f,r31
.endm
'''
MACRO10 = r'''/* P=10*x is even: P+(P>>1) is exactly 15*x for both signs. */
.macro WB_PAIR_MINUS10_15 a,b,c,d,e,f
    ldi r20,10
    muls r20,r24
    movw r30,r0
    mulsu r20,r21
    mov r20,r0
    add r30,r1
    adc r31,r2
    sub \a,r20
    sbc \b,r30
    sbc \c,r31
    add \d,r20
    adc \e,r30
    adc \f,r31
    asr r31
    ror r30
    ror r20
    add \d,r20
    adc \e,r30
    adc \f,r31
.endm
'''


def sha(path, text=False):
    data = path.read_bytes()
    return hashlib.sha256(data.replace(b'\r\n', b'\n') if text else data).hexdigest()


def toolchain(out, gcc, node):
    compiler = Path(shutil.which(gcc) or gcc).resolve()
    runtime = Path(shutil.which(node) or node).resolve()
    ext = '.exe' if compiler.suffix == '.exe' else ''
    paths = {'avr-gcc': compiler, 'avr-nm': compiler.with_name('avr-nm'+ext),
             'avr-objcopy': compiler.with_name('avr-objcopy'+ext),
             'node': runtime, 'python': Path(sys.executable)}
    data = {name: sha(path) for name, path in paths.items()}
    (out/'toolchain.json').write_text(json.dumps(data, indent=2)+'\n', encoding='utf-8')


def candidate_kernel(text, combined=False):
    def replace(before, after):
        nonlocal text
        assert text.count(before) == 1, before
        text = text.replace(before, after)
    replace('/* r20=128 on entry', MACRO7+'/* r20=128 on entry')
    replace('    WB_MAC r4,r5,r6,7\n    WB_MAC r10,r11,r12,-14',
            '    WB_PAIR_7_MINUS14 r4,r5,r6,r10,r11,r12')
    replace('    WB_MAC r7,r8,r9,-14\n    WB_MAC r13,r14,r15,7',
            '    WB_PAIR_7_MINUS14 r13,r14,r15,r7,r8,r9')
    if combined:
        replace('/* r20=128 on entry', MACRO10+'/* r20=128 on entry')
        replace('    WB_MAC r7,r8,r9,-10\n    WB_MAC r13,r14,r15,15',
                '    WB_PAIR_MINUS10_15 r7,r8,r9,r13,r14,r15')
        replace('    WB_MAC r4,r5,r6,15\n    WB_MAC r10,r11,r12,-10',
                '    WB_PAIR_MINUS10_15 r10,r11,r12,r4,r5,r6')
    key = 'combined' if combined else 'candidate'
    assert hashlib.sha256(text.encode()).hexdigest() == KERNEL_SHA[key]
    return text


def fixture_text():
    text = (ROOT/'tests/wb_kernels.c').read_text(encoding='utf-8')
    for before in ['int16_t wb_unit_den[8];', 'volatile int32_t wb_unit_gain;',
                   'volatile int32_t wb_unit_scale;', 'uint8_t wb_unit_indices[4];']:
        assert text.count(before) == 1
        text = text.replace(before, before[:-1]+' __attribute__((externally_visible,used));')
    text = '\n'.join(line for line in text.splitlines()
                     if not any('case '+str(i)+':' in line for i in range(2, 8)))+'\n'
    isr = '''#include <avr/io.h>
volatile uint16_t qmf_config[6];
#ifdef SPEEX_QMF_IRQ_TEST
#include <avr/interrupt.h>
volatile uint16_t qmf_irq_count,qmf_accumulator;
ISR(TIMER2_COMPA_vect)
{
    uint8_t u=(uint8_t)qmf_irq_count;
    qmf_accumulator+=(uint16_t)(uint8_t)(u+37)*(uint8_t)(u+129);++qmf_irq_count;
}
#endif
'''
    text = text.replace('int main(void)', isr+'int main(void)')
    return text.replace('    wb_unit_status=1;', '''    qmf_config[0]=_SFR_MEM_ADDR(SREG);
#ifdef SPEEX_QMF_IRQ_TEST
    qmf_config[1]=TIMER2_COMPA_vect_num*(_VECTORS_SIZE/(SPM_READY_vect_num+1))/2;
    qmf_config[2]=_SFR_MEM_ADDR(TIFR2);qmf_config[3]=_BV(OCF2A);
    qmf_config[4]=_SFR_MEM_ADDR(TIMSK2);qmf_config[5]=_BV(OCIE2A);
    TIMSK2=_BV(OCIE2A);sei();
#endif
    wb_unit_status=1;''', 1)


def verifier_text():
    text = (ROOT/'tests/verify_wb_kernels.mjs').read_text(encoding='utf-8')
    before = 'qmfRoundingAndClippingBoundaryBlocks:family===0?qmfEdges.length:0,peakStackBytes:2303-minSP'
    assert text.count(before) == 1
    return text.replace(before, before+',cycleSamples:cycles')


def prepare(out):
    assert sha(ROOT/'src/wb_qmf.S', True) == KERNEL_SHA['baseline'], 'Baseline QMF changed'
    for name in KERNEL_SHA:
        shutil.copytree(ROOT/'src', out/name/'src', dirs_exist_ok=True)
        if name != 'baseline':
            path = out/name/'src/wb_qmf.S'
            path.write_text(candidate_kernel(path.read_text(encoding='utf-8'), name == 'combined'),
                            encoding='utf-8', newline='\n')
    (out/'qmf_fixture.c').write_text(fixture_text(), encoding='utf-8', newline='\n')
    (out/'verify_cases.mjs').write_text(verifier_text(), encoding='utf-8', newline='\n')


def build(out, gcc):
    gcc = str(Path(shutil.which(gcc) or gcc).resolve())
    prefix = Path(gcc).parent
    ext = '.exe' if gcc.endswith('.exe') else ''
    version = subprocess.check_output([gcc, '--version'], text=True).splitlines()[0]
    for name in KERNEL_SHA:
        for irq in [False, True]:
            src, folder = out/name/'src', out/(name+('-irq' if irq else '-unit'))
            folder.mkdir(parents=True, exist_ok=True)
            flags = ['-mmcu=atmega328p', '-std=c11', '-Os', '-mcall-prologues', '-mrelax',
                     '-fwrapv', '-fno-strict-aliasing', '-ffunction-sections', '-fdata-sections', '-I'+str(src)]
            def run(command):
                subprocess.run(list(map(str, command)), check=True)
            run([gcc, *flags, '-DSPEEX_NB3_ENABLE_ASM=0', '-c', src/'wb_qmf.c', '-o', folder/'qmf_c.o'])
            run([gcc, *flags, '-flto', '-DSPEEX_NB3_ENABLE_ASM=1',
                 *(['-DSPEEX_QMF_IRQ_TEST'] if irq else []), folder/'qmf_c.o', src/'wb_qmf.S',
                 out/'qmf_fixture.c', '-Wl,--gc-sections', *['-Wl,--undefined='+s for s in [
                     'wb_unit_den', 'wb_unit_gain', 'wb_unit_scale', 'wb_unit_indices']], '-o', folder/'wb.elf'])
            run([prefix/('avr-objcopy'+ext), '-O', 'binary', '-R', '.eeprom', folder/'wb.elf', folder/'wb.bin'])
            for options, filename in [(['-n'], 'symbols.txt'), (['-S', '--size-sort'], 'symbol-sizes.txt')]:
                text = subprocess.check_output([prefix/('avr-nm'+ext), *options, folder/'wb.elf'], text=True)
                (folder/filename).write_text(text, encoding='utf-8')
            package = Path(gcc).resolve().parents[1]
            headers = next(p for p in [package/'avr/include/avr', package/'lib/avr/include/avr']
                           if (p/'iom328p.h').exists())
            meta = dict(binarySha256=sha(folder/'wb.bin'), compiler=version, flags=flags,
                        headers={n: sha(headers/n) for n in ['io.h', 'iom328p.h', 'interrupt.h']}, irq=irq)
            (folder/'input.json').write_text(json.dumps(meta, indent=2)+'\n', encoding='utf-8')


def verify(out, node):
    for name in KERNEL_SHA:
        for irq in [False, True]:
            folder = out/(name+('-irq' if irq else '-unit'))
            command = [node, ROOT/'tests/verify_qmf_common_product_irq.mjs', folder] if irq else [
                node, out/'verify_cases.mjs', '--firmware', folder, '--qmf-only', '--full-inputs']
            with (out/(folder.name+'-run.log')).open('w', encoding='utf-8') as log:
                subprocess.run(list(map(str, command)), stdout=log, stderr=subprocess.STDOUT, check=True)


def audit(out, receipt=None):
    assert (out/'qmf_fixture.c').read_text(encoding='utf-8') == fixture_text()
    assert (out/'verify_cases.mjs').read_text(encoding='utf-8') == verifier_text()
    images, source_hashes, reports = {}, {}, {}
    for name in KERNEL_SHA:
        assert sha(out/name/'src/wb_qmf.S', True) == KERNEL_SHA[name]
        for path in sorted((out/'baseline/src').iterdir()):
            if path.is_file():
                source_hashes['src/'+path.name] = sha(path, True)
                if path.name != 'wb_qmf.S':
                    assert path.read_bytes() == (out/name/'src'/path.name).read_bytes(), path.name
        for irq in [False, True]:
            key = name+('-irq' if irq else '-unit')
            folder = out/key
            metadata = json.loads((folder/'input.json').read_text(encoding='utf-8'))
            report = json.loads((folder/('irq-verification.json' if irq else 'verification.json')).read_text(encoding='utf-8'))
            assert sha(folder/'wb.bin') == metadata['binarySha256'] == report['binarySha256']
            end = next(int(line.split()[0], 16) & 65535
                       for line in (folder/'symbols.txt').read_text(encoding='utf-8').splitlines()
                       if line.endswith(' __bss_end'))
            images[key] = dict(binarySha256=metadata['binarySha256'], flashBytes=(folder/'wb.bin').stat().st_size,
                               staticSramBytes=end-256, deviceHeaderSha256ExactBytes=metadata['headers'])
            reports[key] = report
            assert sha(folder/'qmf_c.o') == sha(out/'baseline-unit/qmf_c.o')
    before = reports['baseline-unit']['streams']
    measured = {}
    for name, saving, muls, flash in [('baseline', 0, 1280, 0), ('candidate', 160, 1200, -8), ('combined', 200, 1120, -4)]:
        key = name+'-unit'
        current, irq = reports[key], reports[name+'-irq']
        assert current['qmfOnly'] and current['fullInputs'] and current['fullSigned16InputPairs'] == 65536
        assert len(current['streams']) == 2
        for a, b in zip(before, current['streams']):
            assert a['kernel'] == b['kernel'] and b['blocks'] == 2244 and b['samples'] == 179520
            assert b['pcmExact'] and b['guards'] and b['readOnlyInputs'] and b['mirroredHistoryExact']
            expected = saving if b['kernel'].endswith('_avr') else 0
            assert {x-y for x, y in zip(a['cycleSamples'], b['cycleSamples'])} == {expected}
            assert b['qmfRoundingAndClippingBoundaryBlocks'] == 92 and b['aliasQmf']
            assert b['peakStackBytes'] == a['peakStackBytes']
        assert images[key]['flashBytes']-images['baseline-unit']['flashBytes'] == flash
        assert images[key]['staticSramBytes'] == images['baseline-unit']['staticSramBytes']
        assert irq['cases'] == 8 and irq['asmReturns'] == 16 and irq['ownAsmStackBytes'] == 18
        assert irq['wholeProbePeakStackBytes'] == 31 and irq['injections'] == irq['isrMulInstructions']
        assert irq['nonzeroR1Interrupts'] > 0
        for flag in ['full32RegistersAndSregRestored', 'interruptPcAndSpRestored', 'traceUnchanged',
                     'calleeSavedAndR1Exact', 'wholeArenaInputsGuardsAndMirroredStateExact',
                     'bothIncomingTValues', 'permittedAliasAndSeparate']:
            assert irq[flag], flag
        assert {v['muls'] for v in irq['vectors']} == {muls}
        assert {a['cyclesIncludingRet']-b['cyclesIncludingRet']
                for a, b in zip(reports['baseline-irq']['vectors'], irq['vectors'])} == {saving}
        measured[name] = dict(pairedSavingEveryQmfBlock=saving, mulsEveryQmfBlock=muls,
                              isolatedFlashDelta=flash, injections=irq['injections'],
                              nonzeroR1Interrupts=irq['nonzeroR1Interrupts'])
    tests = ['tests/wb_kernels.c', 'tests/verify_wb_kernels.mjs',
             'tests/verify_qmf_common_product_irq.mjs', 'tests/screen_qmf_common_product.py']
    report = dict(scope='Isolated compact QMF C/ASM exact arithmetic; no full C decoder execution',
                  target='ATmega328P/classic AVR5, GNU ABI, AVR GCC 7.3.0, avr8js 0.21.1',
                  commonCompilerOptions=['-mmcu=atmega328p', '-std=c11', '-Os', '-mcall-prologues',
                                         '-mrelax', '-fwrapv', '-fno-strict-aliasing',
                                         '-ffunction-sections', '-fdata-sections'],
                  linkCompilerOptions=['-flto', '-Wl,--gc-sections'],
                  cFallbackSeparateObject=True,
                  textHashNormalization='CRLF to LF; external headers/binaries/C objects exact bytes',
                  kernelSha256=KERNEL_SHA, baselineSourceSha256=source_hashes,
                  testSourceSha256={n: sha(ROOT/n, True) for n in tests},
                  generatedFixtureSha256=sha(out/'qmf_fixture.c', True),
                  generatedVerifierSha256=sha(out/'verify_cases.mjs', True), images=images,
                  unchangedCObjectSha256ExactBytes=sha(out/'baseline-unit/qmf_c.o'),
                  perRecipe=measured, blocksPerBackendRecipe=2244, outputWordsPerBackendRecipe=179520,
                  roundingClippingBoundaryBlocks=92, abiReturnsPerAsmRecipe=2244,
                  staticSramAndStackUnchanged=True, wholeDecoderSpeedupMeasured=False,
                  predictedCombinedFourCallFrameSaving=800, predictedCombinedFourCallMulsRemoved=640,
                  productionOutputTimingAdmitted=False, physicalBoardTested=False)
    if (out/'toolchain.json').exists():
        report['externalToolSha256ExactBytes'] = json.loads((out/'toolchain.json').read_text(encoding='utf-8'))
    text = json.dumps(report, indent=2)+'\n'
    (out/'summary.json').write_text(text, encoding='utf-8')
    if receipt:
        receipt.write_text(text, encoding='utf-8')
    print('PASS isolated QMF: every block -160/-200 cycles, -8/-4 bytes; C and every-boundary IRQ exact')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['prepare', 'build', 'verify', 'audit', 'all'], default='all')
    parser.add_argument('--out', type=Path, default=ROOT/'build/qmf-common-product-screen')
    parser.add_argument('--avr-gcc')
    parser.add_argument('--node')
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if args.avr_gcc and args.node:
        toolchain(out, args.avr_gcc, args.node)
    if args.phase in ['prepare', 'all']:
        prepare(out)
    if args.phase in ['build', 'all']:
        if not args.avr_gcc:
            parser.error('--avr-gcc is required to build')
        build(out, args.avr_gcc)
    if args.phase in ['verify', 'all']:
        if not args.node:
            parser.error('--node is required to verify')
        verify(out, args.node)
    if args.phase in ['verify', 'audit', 'all']:
        audit(out, args.receipt)


if __name__ == '__main__':
    main()
