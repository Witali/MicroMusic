#!/usr/bin/env python3
"""Audit the counted HB divider against the admitted unrolled scalar fixture."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sha(path, text=False):
    data = path.read_bytes()
    return hashlib.sha256(data.replace(b'\r\n', b'\n') if text else data).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def body(folder, name):
    matches = list(re.finditer(r'^([0-9a-f]+) <([^>]+)>:',
        (folder / 'disassembly.txt').read_text(encoding='utf-8'), re.M))
    index = next(i for i, match in enumerate(matches) if match[2] == name)
    return (folder / 'unit.bin').read_bytes()[int(matches[index][1], 16):int(matches[index + 1][1], 16)]


def checked(folder, name):
    report = load(folder / name)
    assert report['binarySha256'] == sha(folder / 'unit.bin')
    assert report['independentBigIntExact'] and report['explicitBackendSelectionVerified']
    assert report['readonlyInputs'] and report['arbitraryCalleeSavedPatterns']
    assert report['includesInterrupts'] and report['noLostTimerInterrupts']
    assert report['completedTimerInterrupts'] == report['timerCompareEvents'] > 0
    for path, digest in report['sourceSha256'].items():
        assert sha(ROOT / path, True) == digest, path
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unit', type=Path, default=ROOT / 'build/ratio-size')
    parser.add_argument('--reference', type=Path, required=True,
        help='Admitted wb-hb-ratio-unit directory with asm-replay and replay/actual-all.json')
    parser.add_argument('--record', action='store_true')
    args = parser.parse_args()
    out, ref = args.unit, args.reference
    full = checked(out / 'asm', 'verification-full-irq.json')
    assert full['allValidatedHbDivisors'] and full['divisorsSwept'] == 31739
    assert full['cases'] == 106727 and full['calleeSavedAndR1Returns'] == 213454
    controls = {name: checked(out / name, 'verification-quick-irq.json') for name in ['c', 'generic']}
    assert all(report['cases'] == 1862 for report in controls.values())
    assert (out / 'c/unit.bin').read_bytes() == (out / 'generic/unit.bin').read_bytes()
    assert (out / 'generic-control/unit.bin').read_bytes() == (ref / 'generic-control/unit.bin').read_bytes()

    replay = checked(out / 'asm', 'verification-replay-irq.json')
    before = load(ref / 'asm-replay/verification-replay-irq.json')
    assert before['binarySha256'] == sha(ref / 'asm-replay/unit.bin')
    assert before['independentBigIntExact'] and before['noLostTimerInterrupts']
    assert replay['cases'] == before['cases'] == 15076
    assert replay['replayInputSha256'] == before['replayInputSha256'] == sha(ref / 'replay/actual-all.json')
    baseline_source = subprocess.check_output(['git', 'show',
        'e5350100:Codecs/Speex/AVR/src/wb_gain_div.S'], cwd=ROOT).replace(b'\r\n', b'\n')
    assert hashlib.sha256(baseline_source).hexdigest() == before['sourceSha256']['src/wb_gain_div.S']
    for path, digest in before['sourceSha256'].items():
        if path != 'src/wb_gain_div.S':
            assert sha(ROOT / path, True) == digest, path
    traces = []
    for folder in [ref / 'asm-replay', out / 'asm']:
        data = (folder / 'timing-replay-irq.bin').read_bytes()
        assert len(data) == replay['cases'] * 4
        traces.append([pair for pair in struct.iter_unpack('<HH', data)])
    deltas = Counter()
    for old, new in zip(*traces):
        assert new[0] - old[0] == new[1] - old[1]
        delta = new[0] - old[0]
        assert delta in (-1, 44)
        deltas[delta] += 1
    sizes = [len(body(folder, 'speex_wb_ratio_hb_div_avr')) for folder in [ref / 'asm-replay', out / 'asm']]
    assert sizes == [306, 58]
    assert replay['peakStack'] == before['peakStack']
    screens = []
    for profile in ['wb98', 'wb128']:
        old_folder = ref.parent / 'hb-finite-speed/runs/screen/after' / profile
        new_folder = out / 'whole/runs/screen/after' / profile
        irq_folder = out / 'whole/runs/screen/irq' / profile
        old, new, irq = [load(folder / 'verification.json') for folder in [old_folder, new_folder, irq_folder]]
        for folder, report in [(old_folder, old), (new_folder, new), (irq_folder, irq)]:
            assert sha(folder / 'wb.bin') == report['binarySha256']
        assert new['flashBytes'] == old['flashBytes'] - 248
        assert new['staticSramBytes'] == old['staticSramBytes'] and new['peakStack'] == old['peakStack']
        assert irq['includesInterrupts'] and not irq['underruns'] and irq['extraCpuCyclesPerFrame'] == 25600
        assert all(row['s16AndPwmExact'] and row['fullHistoryWithoutChunkReset'] for row in irq['streams'])
        assert all(990 <= row['timerIntervalMinCycles'] <= row['timerIntervalMaxCycles'] <= 1010 for row in irq['streams'])
        old_trace, new_trace = [load(folder / 'packet-timing.json') for folder in [old_folder, new_folder]]
        old_rows = {row['stream']: row for row in old_trace['streams']}
        differences = []
        for row in new_trace['streams']:
            old_row = old_rows[row['stream']]
            assert (row['inputSha256'], row['pcmSha256']) == (old_row['inputSha256'], old_row['pcmSha256'])
            assert len(row['cycles']) == len(old_row['cycles']) > 0
            differences += [b-a for a, b in zip(old_row['cycles'], row['cycles'])]
        assert len(differences) == new['frames'] == irq['frames']
        assert set(differences) <= {-4, 41, 86, 131, 176}
        sources = [load(folder / 'source.json') for folder in
            [ref.parent / 'hb-finite-speed/after' / profile, out / 'whole/after' / profile]]
        assert sources[0].keys() == sources[1].keys()
        assert [path for path in sources[0] if sources[0][path] != sources[1][path]] == ['src/wb_gain_div.S']
        for path, digest in sources[1].items():
            assert sha(ROOT / path, True) == digest, path
        screens.append(dict(profile=profile, frames=new['frames'], flashBefore=old['flashBytes'], flashAfter=new['flashBytes'],
            cycleDeltaMin=min(differences), cycleDeltaMax=max(differences), cycleDeltaMean=sum(differences)/len(differences),
            sourceSha256=sources[1]['src/wb_gain_div.S'], binarySha256=new['binarySha256'],
            irqBinarySha256=irq['binarySha256'], minQueue=irq['minQueuedSamplesBeforeOutput'],
            freeSramAtPeak=irq['freeSramAtPeak'], underruns=0, exact=True,
            reportSha256={name: sha(folder / 'verification.json') for name, folder in
                [('before', old_folder), ('after', new_folder), ('irq', irq_folder)]}))
    result = dict(scope='Counted HB1 divider scalar/ABI/active-IRQ proof; whole-decoder admission is separate',
        baselineRevision='e5350100', cpu='ATmega328P AVR5', compiler=load(out / 'asm/input.json')['compiler'],
        sourceHashMode='UTF-8 normalized to LF', sourceSha256=replay['sourceSha256'],
        checkerSha256={path: sha(ROOT / path, True) for path in
            ['tests/avr_wb_hb_ratio.c', 'tests/build_wb_hb_ratio.py', 'tests/verify_wb_hb_ratio.mjs',
             'tests/avr_tick.mjs', 'tests/audit_wb_ratio_size.py']},
        full=dict(cases=full['cases'], divisors=full['divisorsSwept'], bounds=full['validatedHbDivisorBounds'],
            exact=True, asmReturns=full['calleeSavedAndR1Returns'], timerEvents=full['timerCompareEvents'],
            lostInterrupts=0, peakStack=full['peakStack']),
        explicitCAndGeneric=dict(casesPerBackend=1862, exact=True, binariesIdentical=True),
        widerGenericControlBinaryIdentical=True,
        replay=dict(cases=replay['cases'], inputSha256=replay['replayInputSha256'],
            beforeBinarySha256=before['binarySha256'], afterBinarySha256=replay['binarySha256'],
            beforeTimingSha256=sha(ref / 'asm-replay/timing-replay-irq.bin'),
            afterTimingSha256=sha(out / 'asm/timing-replay-irq.bin'),
            cycleDeltaHistogram={str(k): v for k, v in sorted(deltas.items())}),
        leafFlashBefore=sizes[0], leafFlashAfter=sizes[1], flashSaved=sizes[0] - sizes[1],
        localStackBytes=0, addedSramBytes=0, wholeDecoderScreen=screens,
        cDecoderExecuted=False, physicalBoardTested=False)
    target = ROOT / 'reports/wb-ratio-size-unit.json'
    if args.record:
        target.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    else:
        assert load(target) == result
    print('PASS counted HB divider: 248 B saved; exact full scalar, C selection, ABI, IRQ and replay')


if __name__ == '__main__':
    main()
