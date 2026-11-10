#!/usr/bin/env python3
"""Bind Flash-first WB changes to paired PCM, cycle and production-IRQ results."""
import argparse
import hashlib
import json
from pathlib import Path
from run_wb_ratio_stage import ROOT, PROFILES, LOADS


def sha(path, text=False):
    data = path.read_bytes()
    return hashlib.sha256(data.replace(b'\r\n', b'\n') if text else data).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'build/size-next')
    parser.add_argument('--screen', action='store_true')
    parser.add_argument('--record', action='store_true')
    args = parser.parse_args()
    out, kind = args.out, 'screen' if args.screen else 'full'
    baseline_receipt = load(ROOT / 'reports/wb-finite-response-full.json')
    reuse = load(out / 'baseline-reuse.json')
    assert reuse['baselineRevision'] == 'e5350100' and reuse['sourceManifestExact']
    assert reuse['admittedReceiptSha256'] == sha(ROOT / reuse['admittedReceipt'], True)
    before, after = [load(out / (epoch + '-source.json')) for epoch in ['before', 'after']]
    assert before == baseline_receipt['sourceSha256'] and before.keys() == after.keys()
    changes = sorted(path for path in before if before[path] != after[path])
    assert changes == ['src/compact_lsp.c.inc', 'src/lowrate_excitation.h', 'src/lsp_finish.S', 'src/nb3_lsp_finish.h',
                       'src/wb_fold.S', 'src/wb_gain_div.S', 'src/wb_qmf.S']
    for path, digest in after.items():
        assert sha(ROOT / path, True) == digest, path
    controls = load(out / 'c-controls.json')
    assert not controls['cDecoderExecuted'] and controls['baselineAsmRebuiltIdentically']
    assert controls['baselineRevision'] == 'e5350100'
    assert all(row['compileLinkedOnly'] for row in controls['images'])
    c_before, c_after = controls['images']
    assert c_before['binarySha256'] == reuse['cCompileOnly']['binarySha256'] == sha(out / 'c-before/wb.bin')
    assert c_after['binarySha256'] == sha(out / 'c-after/wb.bin')
    assert (out / 'baseline-rebuild/wb.bin').read_bytes() == (out / 'before/wb395/wb.bin').read_bytes()
    export = load(out / 'export.json')
    assert export['sources'] == 21 and not export['handwrittenAssembly']
    assert 'compile/link only' in export['scope'] and not export['duplicateSources']
    assert export['widebandBitrates'] == [3950, 5750, 7750, 9800, 12800]
    artifacts = [path for path in [out / 'export/link_only.so', out / 'export/link_only.dll'] if path.is_file()]
    assert len(artifacts) == 1 and sha(artifacts[0]) == export['artifactSha256']
    library = load(out / 'export/sources.json')
    assert len(library['sources']) == len(set(library['sources'])) == 21
    assert 'SPEEX_NB3_ENABLE_ASM=0' in library['definitions']
    for path, digest in load(out / 'export/SHA256.json').items():
        assert sha(out / 'export' / path) == digest, path
    assert not list((out / 'export').rglob('*.S'))

    components = ['wb-ratio-size-unit.json', 'lsp-finish-size-unit.json', 'wb-size-response-domain.json',
                  'wb-shared-fold-size.json', 'qmf-size-screen.json', 'nb1-pitch-size-admission.json',
                  'nb1-pitch-unit.json']
    lsp = load(ROOT / 'reports/lsp-finish-size-unit.json')
    assert all(after['src/' + name] == digest for name, digest in lsp['candidate'].items())
    assert after['src/wb_qmf.S'] == load(ROOT / 'reports/qmf-size-screen.json')['kernelSha256']['both']
    fold = load(ROOT / 'reports/wb-shared-fold-size.json')
    assert fold['candidateChangedSourceSha256']['wb_fold.S'] == after['src/wb_fold.S']
    pitch = load(ROOT / 'reports/nb1-pitch-size-admission.json')
    assert pitch['callerSha256'] == after['src/lowrate_excitation.h']
    assert pitch['helperSha256'] == after['src/nb1_pitch.h']
    domain = load(ROOT / 'reports/wb-size-response-domain.json')
    assert domain['currentPrimitiveMatchesSource'] and domain['untouchedXiphComparisons'] == 25171968
    assert (domain['responseMin'], domain['responseMax']) == (111, 31849)
    assert all(sha(ROOT / path, True) == digest for path, digest in domain['sourceSha256'].items())

    manifest = load(out / 'data/manifest.json')
    profiles = []
    for profile, width in PROFILES.items():
        folders = {epoch: out / 'runs' / kind / epoch / profile for epoch in ['before', 'after', 'irq']}
        reports = {epoch: load(folder / 'verification.json') for epoch, folder in folders.items()}
        old, new, irq = [reports[epoch] for epoch in ['before', 'after', 'irq']]
        for epoch, folder in folders.items():
            assert reports[epoch]['binarySha256'] == sha(folder / 'wb.bin') == load(folder / 'backend.json')['binarySha256']
        if not args.screen:
            prior = next(row for row in baseline_receipt['profiles'] if row['profile'] == profile)
            assert sha(folders['before'] / 'verification.json') == prior['reportSha256']['after']
            assert sha(folders['before'] / 'packet-timing.json') == prior['packetTraceSha256']['after']
        assert not old['includesInterrupts'] and not new['includesInterrupts'] and irq['includesInterrupts']
        assert new['flashBytes'] < old['flashBytes'] and new['staticSramBytes'] == old['staticSramBytes']
        assert irq['extraCpuCyclesPerFrame'] == LOADS[profile] and not irq['underruns']
        assert irq['freeSramAtPeak'] > 300 and irq['minQueuedSamplesBeforeOutput'] > 0
        assert all(row['pcmExact'] and row['reset'] for row in old['streams'] + new['streams'])
        traces = [load(folders[epoch] / 'packet-timing.json') for epoch in ['before', 'after']]
        for trace, report in zip(traces, [old, new]):
            assert trace['binarySha256'] == report['binarySha256'] and trace['packetBytes'] == width
            assert not trace['includesInterrupts'] and trace['frames'] == report['frames']
        maps = [{row['stream']: row for row in trace['streams']} for trace in traces]
        raw_rows = [{row['name']: row for row in report['streams']} for report in [old, new]]
        outputs = {row['stream']: row for row in irq['streams']}
        inputs = [row for row in manifest['streams'] if row['profile'] == profile]
        assert len(inputs) == len(maps[0]) == len(maps[1]) == len(outputs)
        streams, cycle_before, cycle_after = [], 0, 0
        for item in inputs:
            name = item['stream'] + '.spxraw'
            a, b, output = maps[0][name], maps[1][name], outputs[name]
            raw = out / 'data' / kind / profile / 'streams' / name
            pcm = out / 'data' / kind / profile / 'oracle' / (item['stream'] + '.pcm')
            frames = min(64, item['frames']) if args.screen else item['frames']
            assert raw.stat().st_size == frames * width and pcm.stat().st_size == frames * 640
            if not args.screen:
                assert sha(raw) == item['inputSha256'] and sha(pcm) == item['pcmSha256']
            for row in [a, b, output]:
                assert row['inputSha256'] == sha(raw) and row['pcmSha256'] == sha(pcm)
            assert len(a['cycles']) == len(b['cycles']) == output['frames'] == frames
            for row, rows in zip([a, b], raw_rows):
                assert all(type(value) is int and value > 0 for value in row['cycles'])
                summary = rows[name]
                assert summary['frames'] == frames
                assert (summary['minCycles'], summary['maxCycles']) == (min(row['cycles']), max(row['cycles']))
                assert summary['meanCycles'] == int(sum(row['cycles'])/frames + 0.5)
            assert output['s16AndPwmExact'] and output['fullHistoryWithoutChunkReset'] and not output['underruns']
            assert 990 <= output['timerIntervalMinCycles'] <= output['timerIntervalMaxCycles'] <= 1010
            deltas = [y-x for x, y in zip(a['cycles'], b['cycles'])]
            # Bound a size/speed tradeoff; active PWM is the actual deadline gate.
            assert max(deltas) <= 6400
            cycle_before += sum(a['cycles'])
            cycle_after += sum(b['cycles'])
            streams.append(dict(stream=name, frames=frames, inputSha256=sha(raw), pcmSha256=sha(pcm),
                cycleDeltaMin=min(deltas), cycleDeltaMax=max(deltas),
                cycleDeltaMean=sum(deltas)/frames, s16AndPwmExact=True,
                minQueue=output['minQueuedSamplesBeforeOutput'], freeSramAtPeak=output['freeSramAtPeak']))
        frames = sum(row['frames'] for row in streams)
        assert frames == old['frames'] == new['frames'] == irq['frames']
        assert cycle_before/frames == old['meanCycles'] and cycle_after/frames == new['meanCycles']
        for report, trace in zip([old, new], traces):
            assert report['maxCycles'] == max(value for row in trace['streams'] for value in row['cycles'])
        assert cycle_after <= cycle_before * 1.03
        profiles.append(dict(profile=profile, frames=frames, streams=streams,
            beforeMeanCycles=cycle_before/frames, afterMeanCycles=cycle_after/frames,
            beforeCpuPercent=cycle_before/frames/3200, afterCpuPercent=cycle_after/frames/3200,
            beforeFlashBytes=old['flashBytes'], afterFlashBytes=new['flashBytes'],
            staticSramBytes=new['staticSramBytes'], beforePeakStack=old['peakStack'], afterPeakStack=new['peakStack'],
            irq=dict(flashBytes=irq['flashBytes'], staticSramBytes=irq['staticSramBytes'],
                minQueue=irq['minQueuedSamplesBeforeOutput'], freeSramAtPeak=irq['freeSramAtPeak'],
                additionalCyclesPerFrame=LOADS[profile], underruns=0),
            binarySha256={epoch: report['binarySha256'] for epoch, report in reports.items()},
            reportSha256={epoch: sha(folder / 'verification.json') for epoch, folder in folders.items()},
            packetTraceSha256={epoch: sha(folders[epoch] / 'packet-timing.json') for epoch in ['before', 'after']}))
    test_paths = ['tests/audit_wb_size_stage.py', 'tests/run_wb_ratio_stage.py', 'tests/verify_wb.mjs',
                  'tests/verify_wb_stream.mjs', 'tests/avr_tick.mjs', 'tests/wb_decode.c', 'tests/avr_wb_stream.c']
    result = dict(scope=kind + ' Flash-first exact ASM WB comparison', baselineRevision='e5350100',
        sourceHashMode='UTF-8 text normalized to LF', sourceSha256=after, sourceOverlay=changes,
        testSourceSha256={path: sha(ROOT / path, True) for path in test_paths},
        baselineReuse=reuse, cControls=controls, portableExport=export, profiles=profiles,
        componentReceiptSha256={name: sha(ROOT / 'reports' / name, True) for name in components},
        rawFramesPerEpoch=sum(row['frames'] for row in profiles), irqFrames=sum(row['frames'] for row in profiles),
        limits=manifest['limits'] + ['Raw CPU excludes startup/reset and interrupts.',
            'IRQ packets ready in RAM; no physical board or external transport latency measured.',
            'C controls compile/link only; no complete project C decoder executed or timed.'], physicalBoardTested=False)
    path = ROOT / 'reports' / ('wb-size-' + kind + '.json')
    if args.record:
        path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    else:
        assert load(path) == result
    print('PASS', kind, result['rawFramesPerEpoch'], 'matched raw and IRQ frames, exact PCM/PWM, no underruns')


if __name__ == '__main__':
    main()
