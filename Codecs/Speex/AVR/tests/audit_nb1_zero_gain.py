#!/usr/bin/env python3
"""Bind exact gain-zero preparation to full decoding, IRQ, SPI and state evidence."""
import argparse
import json
from pathlib import Path
from audit_nb1_gain import ROOT, PROFILES, filename, sha, read, save

CHANGED = ['src/lowrate_excitation.h', 'tests/verify_low_api.mjs', 'tests/verify_nb1_streaming.mjs']
ADDED = ['src/nb1_zero_gain.h', 'tests/avr_nb1_unity.c', 'tests/build_nb1_unity.py',
         'tests/verify_nb1_unity.mjs', 'tests/screen_nb1_zero_gain.py',
         'tests/build_nb1_zero_admission.py', 'tests/run_nb1_zero_admission.py',
         'tests/audit_nb1_zero_gain.py']
OUT = ROOT / 'build/nb1-zero-final'


def paired(corpus):
    profiles = {}
    for label, wb in PROFILES.items():
        traces = [json.loads((OUT / e / label / 'packet-timing.json').read_text()) for e in ['before', 'after']]
        assert all(t['frames'] == 10627 and len(t['streams']) == 18 for t in traces)
        groups = [dict(code=k, frames=0, beforeCycles=0, afterCycles=0, deltaMin=None, deltaMax=None) for k in range(16)]
        speech = dict(frames=0, beforeCycles=0, afterCycles=0, codeHistogram=[0]*16)
        streams = []
        for a, b in zip(traces[0]['streams'], traces[1]['streams']):
            for k in ['stream', 'inputSha256', 'pcmSha256']:
                assert a[k] == b[k]
            raw = corpus / label / 'streams' / a['stream']
            assert sha(raw, False) == a['inputSha256']
            data = raw.read_bytes(); width = 10 if wb else 6
            assert len(a['cycles']) == len(b['cycles']) == len(data)//width
            histogram = [0]*16
            for i, (x, y) in enumerate(zip(a['cycles'], b['cycles'])):
                p = i*width; assert data[p] >> 3 == 1
                code = ((data[p+3] & 3) << 2) | (data[p+4] >> 6)
                g = groups[code]; delta = y-x
                g['frames'] += 1; g['beforeCycles'] += x; g['afterCycles'] += y; histogram[code] += 1
                g['deltaMin'] = delta if g['deltaMin'] is None else min(g['deltaMin'], delta)
                g['deltaMax'] = delta if g['deltaMax'] is None else max(g['deltaMax'], delta)
            row = dict(stream=a['stream'], frames=len(a['cycles']), beforeCycles=sum(a['cycles']), afterCycles=sum(b['cycles']))
            if a['stream'].startswith(('en_', 'ru_')):
                for k in ['frames', 'beforeCycles', 'afterCycles']:
                    speech[k] += row[k]
                speech['codeHistogram'] = [x+y for x, y in zip(speech['codeHistogram'], histogram)]
            streams.append(row)
        for epoch in ['before', 'after']:
            speech[epoch+'MeanCycles'] = speech[epoch+'Cycles']/speech['frames']
            speech[epoch+'CpuPercent'] = speech[epoch+'MeanCycles']/3200
        speech['zeroGainFrames'] = sum(speech['codeHistogram'][:4])
        profiles[label] = dict(frames=10627, beforeBinarySha256=traces[0]['binarySha256'],
                              afterBinarySha256=traces[1]['binarySha256'], codeGroups=groups, speech=speech, streams=streams)
    return dict(scope='Paired complete-history command intervals, excluding reset/startup/IRQ; before traces reused after verification', profiles=profiles)


def record(args):
    assert args.corpus, '--record requires --corpus'
    reports = []

    def retain(name, path, binary=None):
        data = json.loads(path.read_text())
        if binary:
            assert sha(binary, False) == data.get('binarySha256', data.get('input', {}).get('binarySha256'))
        name = 'nb1-zero-'+name+'.json'; save(name, data); reports.append(name)

    retain('baseline-source', OUT/'baseline-source.json')
    retain('screen', ROOT/'build/nb1-zero-screen/summary.json')
    retain('corpus', ROOT/'build/nb1-gain-screen-data/manifest.json')
    retain('export', ROOT/'build/low-export-check.json')
    retain('streaming', ROOT/'build/noise-cache-unit/verification.json', ROOT/'build/noise-cache-unit/cache.bin')
    for backend in ['asm', 'c']:
        folder = ROOT/'build/nb1-unity-unit'/backend
        retain('unit-'+backend, folder/'verification.json', folder/'unit.bin')
        retain('unit-image-'+backend, folder/'input.json', folder/'unit.bin')
    for epoch in ['before', 'after']:
        for label, wb in PROFILES.items():
            folder = OUT/epoch/label
            retain(epoch+'-'+label, folder/filename(wb), folder/('wb.bin' if wb else 'speex-test.bin'))
            folder = OUT/epoch/'spi'/label
            retain(epoch+'-spi-'+label, folder/'verification.json', folder/'player.bin')
        for label in ['irq8', 'irq11']:
            folder = OUT/epoch/label
            retain(epoch+'-'+label, folder/'verification.json', folder/'wb.bin')
        for label in ['nb', 'wb']:
            folder = OUT/epoch/'api'/label
            retain(epoch+'-api-'+label, folder/'verification.json', folder/'api.bin')
    for label, wb in PROFILES.items():
        folder = OUT/'features/asm'/label
        retain('feature-'+label, folder/filename(wb), folder/('wb.bin' if wb else 'speex-test.bin'))
        for variant in ['before', 'root-only', 'loop', 'split', 'common-fold']:
            folder = ROOT/'build/nb1-zero-screen'/variant/label
            retain('screen-'+variant+'-'+label, folder/filename(wb), folder/('wb.bin' if wb else 'speex-test.bin'))
    name = 'nb1-zero-timing.json'; save(name, paired(args.corpus)); reports.append(name)
    controls = dict(images=[], features=[], cImages=[], cDecoderExecuted=False)
    for label in ['nb8', 'nb11', 'wb98', 'wb128', 'nb395', 'wb575']:
        binary = 'wb.bin' if label.startswith('wb') else 'speex-test.bin'
        paths = [OUT/'identities'/e/label/binary for e in ['before', 'after']]
        assert paths[0].read_bytes() == paths[1].read_bytes(), label
        controls['images'].append(dict(profile=label, byteIdentical=True, flashBytes=paths[1].stat().st_size, binarySha256=sha(paths[1], False)))
    for label, wb in PROFILES.items():
        for backend in ['asm', 'c']:
            folder = OUT/'features'/backend/label; meta = json.loads((folder/'backend.json').read_text())
            binary = folder/('wb.bin' if wb else 'speex-test.bin')
            assert sha(binary, False) == meta['binarySha256'] and meta['backend'] == backend and meta['lowRates'] == 4
            controls['features'].append(dict(profile=label, backend=backend, lowRates=4, flashBytes=binary.stat().st_size,
                                            binarySha256=meta['binarySha256'], compiledLinkedOnly=backend == 'c'))
        folder = OUT/'c'/label; meta = json.loads((folder/'input.json').read_text()); binary = folder/'player.bin'
        assert meta['backend'] == 'c' and sha(binary, False) == meta['binarySha256']
        controls['cImages'].append(dict(profile=label, flashBytes=binary.stat().st_size, binarySha256=meta['binarySha256'], compiledLinkedOnly=True))
    name = 'nb1-zero-controls.json'; save(name, controls); reports.append(name)
    base = read('nb1-gain-admission.json'); sources = list(base['sourceSha256'])+ADDED
    assert len(sources) == len(set(sources))
    save('nb1-zero-admission.json', dict(baselineRevision='1cdda26c', baselineAdmissionSha256=sha(ROOT/'reports/nb1-gain-admission.json'),
        target='ATmega328P / classic AVR5 / 16 MHz / 2 KB SRAM / GNU ABI', compiler='AVR GCC 7.3.0; existing mixed Os/O2/O3, LTO, mcall-prologues, mrelax',
        backend='Explicit AVR ASM decoder with portable C preparation identities', physicalBoardTested=False,
        sourceSha256={n: sha(ROOT/n) for n in sources}, reportSha256={n: sha(ROOT/'reports'/n) for n in reports},
        limits=['Fresh after: 21254 full raw frames, 21254 WB IRQ frames at +8/+11%, 9600 continuous SPI frames.',
                'Before raw/IRQ/SPI reports, images and raw traces reused from verified parent; before APIs freshly reobserved.',
                'Gain-zero is not silence: preserve noise, prior pulse, persistent state, all 160 RNG transitions and original QMF.',
                'NB1-disabled images are byte-identical; no fresh full all-feature timing for other modes.',
                'Full C decoders/export compile/link only; only isolated C scalar primitives execute.',
                'ISA simulation only; no physical-board or analog measurements.']))


def audit(args):
    admission = read('nb1-zero-admission.json'); base = read('nb1-gain-admission.json')
    assert admission['baselineAdmissionSha256'] == sha(ROOT/'reports/nb1-gain-admission.json')
    assert sorted(n for n, h in base['sourceSha256'].items() if sha(ROOT/n) != h) == sorted(CHANGED)
    for n, h in admission['sourceSha256'].items():
        assert sha(ROOT/n) == h, n
    for n, h in {**base['reportSha256'], **admission['reportSha256']}.items():
        assert sha(ROOT/'reports'/n) == h, n
    for n, h in read('spi-input-admission.json')['sourceSha256'].items():
        assert sha(ROOT.parents[2]/n) == h, n
    b = read('nb1-zero-baseline-source.json')
    assert b['sourceTreeVerified'] and b['sourceFiles'] == len(base['sourceSha256']) and b['admissionSha256'] == admission['baselineAdmissionSha256']
    for backend in ['asm', 'c']:
        u = read('nb1-zero-unit-'+backend+'.json'); image = read('nb1-zero-unit-image-'+backend+'.json')
        assert u['backend'] == image['backend'] == backend
        assert u['binarySha256'] == image['binarySha256'] == read('nb1-zero-unit-asm.json')['binarySha256']
        assert u['fullSigned16Inputs'] == 65536 and u['boundedInputsExcludingMin'] == 65535 and u['calleeSavedAndR1Returns'] == 196607
        assert u['negativeEndpointAndFloorsExact'] and u['originalAndIndependentExact'] and u['noMulsInSimplifications']
        assert [r['calls'] for r in u['statistics']] == [65536, 65536, 65535]
        assert [r['muls'] for r in u['statistics']] == [262144, 0, 0]
    state = read('nb1-zero-streaming.json')
    for k in ['independentOriginalVocoder', 'allPartialStatesExact', 'classesAndSeedPerQuarterExact', 'readOnlyFoldWorkspace',
              'outputAndScratchBounds', 'pcmExact', 'resetClearsWorkspace', 'preparationPreservesPersistentState']:
        assert state[k], k
    assert state['frames'] == 1024 and state['cacheFrames'] == 205 and state['generatedBlocks'] == state['foldedBlocks'] == 820
    assert state['zeroGainFrames'] == 49 and state['nonzeroToZero'] > 0 and state['zeroToNonzero'] > 0
    targeted = state['targetedZeroGainWithPriorPulse']
    assert targeted['allFourGainCodes'] and [r['code'] for r in targeted['cases']] == [0, 1, 2, 3]
    assert all(r['priorPulse'] != 0 and r['independentExcitationAndQuarterStatesExact'] for r in targeted['cases'])
    assert (state['reusedWorkspaceBytes'], state['guardBytes'], state['firstDelayedInputByte'], state['nextHistorySourceByte']) == (208, 2, 210, 320)
    screen = read('nb1-zero-screen.json'); assert screen['baselineSourceVerified'] and len(screen['rows']) == 10
    for label, wb in PROFILES.items():
        old, new = [read('nb1-zero-'+e+'-'+label+'.json') for e in ['before', 'after']]
        assert old == read('nb1-gain-after-'+label+'.json')
        timing = read('nb1-zero-timing.json')['profiles'][label]
        assert old['frames'] == new['frames'] == timing['frames'] == 10627 and len(new['streams']) == 18
        assert old['binarySha256'] == timing['beforeBinarySha256'] and new['binarySha256'] == timing['afterBinarySha256']
        assert new['flashBytes'] == old['flashBytes']+(132 if wb else 100) and new['staticSramBytes'] == old['staticSramBytes']
        assert all(r.get('reset', r.get('resetVerified')) and r.get('pcmExact', True) for r in new['streams'])
        if wb:
            assert new['peakStack'] == old['peakStack'] and new['freeSram'] == old['freeSram']
        else:
            assert new['minStackPointer'] == old['minStackPointer']-2 and new['freeSramAtPeak'] == old['freeSramAtPeak']-2
        assert timing['speech']['frames'] == 6467 and timing['speech']['afterMeanCycles'] < timing['speech']['beforeMeanCycles']
        assert sum(r['frames'] for r in timing['codeGroups']) == 10627
        assert all(r['frames'] > 0 for r in timing['codeGroups'])
        assert all(r['deltaMax'] < 0 for r in timing['codeGroups'][:4])
        variants = {r['variant']: r for r in screen['rows'] if r['profile'] == label}; chosen = variants['common-fold']
        assert chosen['sourceSha256'] == sha(ROOT/'src/lowrate_excitation.h') and chosen['binarySha256'] == new['binarySha256']
        assert chosen['meanCycles'] < variants['before']['meanCycles']
        if wb:
            assert variants['split']['flashBytes']-chosen['flashBytes'] == 78
            assert 0 < chosen['meanCycles']-variants['split']['meanCycles'] < 4
        else:
            assert chosen['binarySha256'] == variants['split']['binarySha256']
        for variant, row in variants.items():
            r = read('nb1-zero-screen-'+variant+'-'+label+'.json')
            assert r['frames'] == 384 and r['binarySha256'] == row['binarySha256'] and row['pcmExact'] and row['resetExact']
        f = read('nb1-zero-feature-'+label+'.json'); assert f['frames'] == 384
        for epoch in ['before', 'after']:
            s = read('nb1-zero-'+epoch+'-spi-'+label+'.json')
            assert s['passed'] and s['frames'] == (3600 if wb else 6000) and s['s16Exact'] and s['pwmExact'] and not s['underruns']
            assert s['includesInterrupts'] and s['fullHistoryWithoutReset'] and s['input']['streamBytes'] == s['modelStats']['readBytes'] == 36000
            assert (990 if wb else 1990) <= s['timerIntervalMinCycles'] <= s['timerIntervalMaxCycles'] <= (1010 if wb else 2010)
        old, new = [read('nb1-zero-'+e+'-spi-'+label+'.json') for e in ['before', 'after']]
        assert old == read('nb1-gain-after-spi-'+label+'.json')
        for k in ['pcmSha256', 'pwmSha256', 'modelWasmSha256']:
            assert old[k] == new[k]
        for k in ['inputSha256', 'driverSha256']:
            assert old['input'][k] == new['input'][k]
    for name, load in [('irq8', 25600), ('irq11', 35200)]:
        old, new = [read('nb1-zero-'+e+'-'+name+'.json') for e in ['before', 'after']]
        assert old == read('nb1-gain-after-'+name+'.json')
        for r in [old, new]:
            assert r['frames'] == 10627 and len(r['streams']) == 18 and r['extraCpuCyclesPerFrame'] == load and r['includesInterrupts'] and not r['underruns']
            for s in r['streams']:
                assert s['s16AndPwmExact'] and s['fullHistoryWithoutChunkReset'] and not s['underruns']
                assert 990 <= s['timerIntervalMinCycles'] <= s['timerIntervalMaxCycles'] <= 1010
        for x, y in zip(old['streams'], new['streams']):
            for k in ['stream', 'frames', 'inputSha256', 'pcmSha256']:
                assert x[k] == y[k]
    for label, rejected in [('nb', 6144), ('wb', 7168)]:
        old, new = [read('nb1-zero-'+e+'-api-'+label+'.json') for e in ['before', 'after']]
        original = json.loads(json.dumps(old)); del original['framePreparationArithmetic']['byGain']
        assert original == read('nb1-gain-after-api-'+label+'.json')
        for r in [old, new]:
            assert r['frames'] == 1024 and r['rejectedCalls'] == rejected and r['pcmExact'] and r['resetExact'] and r['paddingIgnored']
            g = r['nb1GainLookup']; assert g['calls'] == sum(g['codeHistogram']) == 206
            assert g['exactFlashAddressPerFrame'] and g['originalFiniteMapVerified'] and g['invalidAndOtherModeCallsDoNotExecute']
            assert r['framePreparationArithmetic']['byGain']['zero']['calls'] == sum(g['codeHistogram'][:4]) == 49
        assert old['inputSha256'] == new['inputSha256'] and old['pcmSha256'] == new['pcmSha256']
        assert old['framePreparationArithmetic']['byGain']['zero']['min'] == old['framePreparationArithmetic']['byGain']['zero']['max'] == 94
        groups = new['framePreparationArithmetic']['byGain']
        assert groups['zero']['min'] == groups['zero']['max'] == 16
        assert groups['nonzero']['min'] == groups['nonzero']['max'] == 94
        assert new['framePreparationArithmetic']['hardwareMultiplies'] == 49*16+157*94
    controls = read('nb1-zero-controls.json')
    assert not controls['cDecoderExecuted'] and len(controls['images']) == 6 and all(r['byteIdentical'] for r in controls['images'])
    assert controls['images'] == read('nb1-gain-controls.json')['images']
    assert len(controls['features']) == 4 and all(r['lowRates'] == 4 for r in controls['features'])
    assert all(r['compiledLinkedOnly'] for r in controls['features'] if r['backend'] == 'c')
    assert len(controls['cImages']) == 2 and all(r['compiledLinkedOnly'] and r['flashBytes'] <= 32768 for r in controls['cImages'])
    export = read('nb1-zero-export.json'); assert export['sources'] == 21 and not export['handwrittenAssembly'] and not export['duplicateSources']
    if args.corpus:
        for row in read('low-final-corpus.json')['streams']:
            if row['profile'] not in PROFILES:
                continue
            for folder, suffix, key in [('streams', '.spxraw', 'inputSha256'), ('oracle', '.pcm', 'pcmSha256')]:
                assert sha(args.corpus/row['profile']/folder/(Path(row['stream']).stem+suffix), False) == row[key]
        assert paired(args.corpus) == read('nb1-zero-timing.json')
    print('PASS gain-zero: 21254 fresh raw / 21254 fresh loaded IRQ / 9600 fresh SPI frames, verified parent before; exact PCM/PWM/state')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', action='store_true'); parser.add_argument('--corpus', type=Path); args = parser.parse_args()
    if args.record:
        record(args)
    audit(args)


if __name__ == '__main__':
    main()
