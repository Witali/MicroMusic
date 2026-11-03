#!/usr/bin/env python3
"""Bind matched WB speed, exact PCM and active-IRQ evidence for pinned stages."""
import argparse
import hashlib
import json
from pathlib import Path
from run_wb_ratio_stage import ROOT, OUT, PROFILES, LOADS, save

STAGES = {
    'ratio': dict(folder='speed-next', label='ratio-only', prefix='wb-ratio', baseline='9772b0a4',
        changes=['src/speex_wb1.c', 'src/wb_gain_div.S', 'src/wb_gain_div.h'],
        added=['src/nb1_pitch.h'], flashDelta=26, stackDelta=-2, unit='wb-ratio-unit.json'),
    'interpolation': dict(folder='hb-speed', label='HB interpolation', prefix='wb-interpolation', baseline='7ca56cf1',
        changes=['src/speex_wb1.c'], added=[], flashDelta=192, stackDelta=0,
        unit='wb-interpolation-unit.json', domain='wb-interpolation-domain.json'),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def text_sha(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def main():
    global OUT
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--screen', action='store_true')
    p.add_argument('--record', action='store_true')
    p.add_argument('--stage', choices=list(STAGES), default='ratio')
    args = p.parse_args()
    config = STAGES[args.stage]
    OUT = ROOT / 'build' / config['folder']
    kind = 'screen' if args.screen else 'full'
    manifest = load(OUT / 'data/manifest.json')
    sources = [load(OUT / (epoch + '-source.json')) for epoch in ['before', 'after']]
    changed = sorted(n for n in sources[0] if sources[0][n] != sources[1][n])
    assert changed == config['changes']
    assert sorted(set(sources[1]) - set(sources[0])) == config['added']
    # The prepared pitch helper remains unused during this ratio-only stage.
    for path in (ROOT / 'src').iterdir():
        if path.is_file() and path.name != 'nb1_pitch.h':
            assert b'#include "nb1_pitch.h"' not in path.read_bytes(), path.name
    for name, digest in sources[1].items():
        data = (ROOT / name).read_bytes().replace(b'\r\n', b'\n')
        assert hashlib.sha256(data).hexdigest() == digest, name
    controls = load(OUT / 'c-controls.json')
    assert controls['baselineAsmRebuiltIdentically'] and not controls['cDecoderExecuted']
    assert controls['baselineRevision'] == config['baseline']
    assert all(r['compileLinkedOnly'] for r in controls['images'])
    for image in controls['images']:
        assert image['binarySha256'] == sha(OUT / ('c-' + image['epoch']) / 'wb.bin')
    assert (OUT / 'baseline-rebuild/wb.bin').read_bytes() == (OUT / 'before/wb395/wb.bin').read_bytes()
    export = load(OUT / 'export.json')
    assert export['sources'] == 21 and not export['duplicateSources'] and not export['handwrittenAssembly']
    assert export['widebandBitrates'] == [3950, 5750, 7750, 9800, 12800]
    rows = []
    for profile, width in PROFILES.items():
        folders = {epoch: OUT / 'runs' / kind / epoch / profile for epoch in ['before', 'after', 'irq']}
        reports = {epoch: load(folder / 'verification.json') for epoch, folder in folders.items()}
        traces = {epoch: load(folders[epoch] / 'packet-timing.json') for epoch in ['before', 'after']}
        for epoch, folder in folders.items():
            r = reports[epoch]
            assert r['binarySha256'] == sha(folder / 'wb.bin')
            assert r['binarySha256'] == load(folder / 'backend.json')['binarySha256']
        before, after, irq = [reports[e] for e in ['before', 'after', 'irq']]
        assert not before['includesInterrupts'] and not after['includesInterrupts']
        assert after['staticSramBytes'] == before['staticSramBytes']
        assert after['flashBytes'] == before['flashBytes'] + config['flashDelta']
        assert after['peakStack'] == before['peakStack'] + config['stackDelta']
        assert irq['includesInterrupts'] and not irq['underruns']
        assert irq['extraCpuCyclesPerFrame'] == LOADS[profile]
        inputs = [r for r in manifest['streams'] if r['profile'] == profile]
        assert len(inputs) == len(traces['before']['streams']) == len(traces['after']['streams']) == len(irq['streams'])
        old = {r['stream']: r for r in traces['before']['streams']}
        new = {r['stream']: r for r in traces['after']['streams']}
        outputs = {r['stream']: r for r in irq['streams']}
        streams = []
        for item in inputs:
            name = item['stream'] + '.spxraw'
            a, b, output = old[name], new[name], outputs[name]
            raw = OUT / 'data' / kind / profile / 'streams' / name
            pcm = OUT / 'data' / kind / profile / 'oracle' / (item['stream'] + '.pcm')
            frames = min(64, item['frames']) if args.screen else item['frames']
            assert len(raw.read_bytes()) == frames * width
            assert len(pcm.read_bytes()) == frames * 640
            for r in [a, b, output]:
                assert r['inputSha256'] == sha(raw) and r['pcmSha256'] == sha(pcm)
            assert len(a['cycles']) == len(b['cycles']) == output['frames'] == frames
            delta = [y-x for x, y in zip(a['cycles'], b['cycles'])]
            assert max(delta) <= 0 and (args.stage != 'ratio' or max(delta) < 0), (profile, name, max(delta))
            assert output['s16AndPwmExact'] and output['fullHistoryWithoutChunkReset'] and not output['underruns']
            assert 990 <= output['timerIntervalMinCycles'] <= output['timerIntervalMaxCycles'] <= 1010
            streams.append(dict(stream=name, frames=frames, inputSha256=a['inputSha256'], pcmSha256=a['pcmSha256'],
                beforeCycles=sum(a['cycles']), afterCycles=sum(b['cycles']),
                cycleDeltaMin=min(delta), cycleDeltaMax=max(delta),
                s16AndPwmExact=True, minQueuedSamples=output['minQueuedSamplesBeforeOutput'],
                freeSramAtPeak=output['freeSramAtPeak']))
        frames = sum(s['frames'] for s in streams)
        assert frames == before['frames'] == after['frames'] == irq['frames']
        assert all(r['reset'] and r['pcmExact'] for r in before['streams'] + after['streams'])
        means = [sum(s[key] for s in streams)/frames for key in ['beforeCycles', 'afterCycles']]
        assert means[1] < means[0]
        rows.append(dict(profile=profile, frames=frames, streams=streams,
            beforeMeanCycles=means[0], afterMeanCycles=means[1], speedupPercent=100*(means[0]-means[1])/means[0],
            beforeCpuPercent=means[0]/3200, afterCpuPercent=means[1]/3200,
            beforeFlashBytes=before['flashBytes'], afterFlashBytes=after['flashBytes'],
            staticSramBytes=after['staticSramBytes'], beforePeakStack=before['peakStack'], afterPeakStack=after['peakStack'],
            irq=dict(binarySha256=irq['binarySha256'], flashBytes=irq['flashBytes'], staticSramBytes=irq['staticSramBytes'],
                additionalCyclesPerFrame=LOADS[profile], minQueue=irq['minQueuedSamplesBeforeOutput'],
                freeSramAtPeak=irq['freeSramAtPeak'], underruns=0),
            binarySha256={e: r['binarySha256'] for e, r in reports.items()},
            reportSha256={e: sha(folders[e] / 'verification.json') for e in folders},
            packetTraceSha256={e: sha(folders[e] / 'packet-timing.json') for e in traces}))
    checks = ['tests/run_wb_ratio_stage.py', 'tests/audit_wb_ratio_stage.py',
        'tests/verify_wb.mjs', 'tests/verify_wb_stream.mjs', 'tests/avr_tick.mjs',
        'tests/wb_decode.c', 'tests/avr_wb_stream.c', 'package.json', 'package-lock.json']
    if args.stage == 'interpolation':
        checks += ['tests/check_wb_interpolation.py', 'tests/avr_wb_interpolation.c',
            'tests/build_wb_interpolation.py', 'tests/verify_wb_interpolation.mjs']
    result = dict(scope=kind + ' matched ASM ' + config['label'] + ' raw and production-IRQ comparisons',
        baselineRevision=config['baseline'], sourceHashMode='UTF-8 text normalized to LF',
        baselineSourceManifestSha256=text_sha(OUT / 'before-source.json'), sourceSha256=sources[1],
        testSourceSha256={n: hashlib.sha256((ROOT / n).read_bytes().replace(b'\r\n', b'\n')).hexdigest() for n in checks},
        unitReceiptSha256=text_sha(ROOT / 'reports' / config['unit']),
        exportPackageManifestSha256=sha(OUT / 'export/SHA256.json'),
        sourceOverlay=changed, unusedPreparedHeader='src/nb1_pitch.h',
        cControls=controls, portableExport=export, profiles=rows, physicalBoardTested=False,
        rawFramesPerEpoch=sum(r['frames'] for r in rows), irqFrames=sum(r['frames'] for r in rows),
        limits=manifest['limits'] + ['Raw timing excludes startup/reset and interrupts.',
            'IRQ input packets are ready in RAM; no external transport latency or physical board is measured.',
            'No new complete-C-decoder execution or timing. C controls compile/link only.'])
    if 'domain' in config:
        result['domainReceiptSha256'] = text_sha(ROOT / 'reports' / config['domain'])
    destination = ROOT / 'reports' / (config['prefix'] + '-' + kind + '.json')
    if args.record:
        save(destination, result)
    else:
        assert load(destination) == result
    print('PASS', kind, result['rawFramesPerEpoch'], 'frames per raw epoch plus', result['irqFrames'], 'IRQ frames')


if __name__ == '__main__':
    main()
