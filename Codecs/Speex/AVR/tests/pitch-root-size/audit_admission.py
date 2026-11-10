"""Bind frozen whole-image pitch-root controls, exact scalar reuse and bounded ASM PCM screens."""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def raw_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_sha(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def read(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--record', action='store_true')
    choice.add_argument('--check', action='store_true')
    parser.add_argument('--toolchains-root', type=Path, default=Path('C:/Work/MicroMusic/build/toolchains'))
    parser.add_argument('--avr8js-root', type=Path, default=Path('C:/Work/MicroMusic/.worktree/speex-wb-speed-next/Codecs/Speex/AVR/node_modules/avr8js'))
    args = parser.parse_args()
    frozen = read(ROOT / 'source.json')
    for name, digest in frozen['sourceSha256'].items():
        assert source_sha(ROOT / 'source' / name) == digest, name
    prior = read(ROOT / 'source/reports/nb1-pitch-unit.json')
    for name, digest in prior['sourceSha256'].items():
        assert source_sha(ROOT / 'source' / name) == digest
    assert prior['pitchMin'] == 17 and prior['pitchMax'] == 144
    assert prior['portableArithmeticExplicitlySelectable'] and prior['allRecipesExact']
    lowrate = (ROOT / 'source/src/lowrate_excitation.h').read_text()
    assert '#include "nb1_pitch.h"' in lowrate
    assert 'int16_t amplitude=(int16_t)((int32_t)speex_nb1_pitch_root(pitch)*' in lowrate
    assert 'uint8_t pitch=17+speex_packet_field(packet,23,7);' in lowrate
    build = read(ROOT / 'build.json')
    screen = read(ROOT / 'screen.json')
    data = read(ROOT / 'data.json')
    rows = []
    reports = {}
    timing = {}
    for row in build['rows']:
        profile = row['profile']
        table = int(row['tableEnabled'])
        directory = ROOT / ('table' + str(table)) / profile
        wideband = profile == 'wb395'
        binary = directory / ('wb.bin' if wideband else 'speex-test.bin')
        meta = read(directory / 'backend.json')
        report_file = directory / ('verification.json' if wideband else 'avr-verification.json')
        report = read(report_file)
        trace = read(directory / 'packet-timing.json')
        assert row['binarySha256'] == meta['binarySha256'] == report['binarySha256'] == trace['binarySha256'] == raw_sha(binary)
        assert meta['backend'] == report['backend'] == 'asm'
        assert meta['packetBytes'] == row['packetBytes'] == trace['packetBytes']
        assert meta['lowRates'] == row['lowRates']
        assert meta['nb4Enabled'] == row['nb4Enabled']
        assert report['frames'] == trace['frames'] == 384
        assert report['includesInterrupts'] is False and trace['includesInterrupts'] is False
        assert report['flashBytes'] == row['flashBytes'] == binary.stat().st_size
        assert report['staticSramBytes'] == row['staticSramBytes']
        assert len(trace['streams']) == len(report['streams']) == 3
        total = 0
        for stream, measured in zip(trace['streams'], report['streams']):
            name = stream['stream']
            assert name == measured['name' if wideband else 'stream']
            assert len(stream['cycles']) == measured['frames'] == 128
            assert all(isinstance(value, int) and value > 0 for value in stream['cycles'])
            assert min(stream['cycles']) == measured['minCycles']
            assert max(stream['cycles']) == measured['maxCycles']
            assert measured['pcmExact'] and measured['reset'] if wideband else measured['resetVerified']
            manifest = next(item for item in data['streams'] if item['profile'] == profile and item['stream'] + '.spxraw' == name)
            raw = ROOT / 'data' / profile / 'streams' / name
            pcm = ROOT / 'data' / profile / 'oracle' / name.replace('.spxraw', '.pcm')
            assert manifest['inputSha256'] == stream['inputSha256'] == raw_sha(raw)
            assert manifest['pcmSha256'] == stream['pcmSha256'] == raw_sha(pcm)
            assert raw.stat().st_size == row['packetBytes'] * 128
            assert pcm.stat().st_size == (640 if wideband else 320) * 128
            total += sum(stream['cycles'])
        result = next(item for item in screen['rows'] if item['profile'] == profile and item['tableEnabled'] == bool(table))
        assert result['totalFrameCycles'] == total
        assert result['meanFrameCycles'] == total / 384
        assert result['binarySha256'] == row['binarySha256']
        assert result['pcmExact'] and result['resetExact']
        if wideband:
            assert report['meanCycles'] == total / 384
        rows.append(dict(**result, reportSha256=source_sha(report_file),
                         packetTimingSha256=source_sha(directory / 'packet-timing.json'),
                         buildMetadataSha256=source_sha(directory / 'admission-build.json')))
        reports[(profile, table)] = report
        timing[(profile, table)] = trace

    comparisons = []
    for profile in ['wb395', 'nb215-min']:
        pair = [next(row for row in build['rows'] if row['profile'] == profile and row['tableEnabled'] == bool(table)) for table in [0, 1]]
        normalize = lambda command: [re.sub(r'<admission>/table[01]/' + profile, '<output>',
                                    re.sub(r'SPEEX_NB1_PITCH_ROOT_TABLE=[01]', 'SPEEX_NB1_PITCH_ROOT_TABLE=<selection>', arg.replace('\\', '/'))) for arg in command]
        assert normalize(pair[0]['command']) == normalize(pair[1]['command']), 'Only TABLE and destination may differ'
        assert pair[0]['staticSramBytes'] == pair[1]['staticSramBytes']
        positive = []
        zero = []
        all_savings = []
        for before, after in zip(timing[(profile, 0)]['streams'], timing[(profile, 1)]['streams']):
            assert before['stream'] == after['stream']
            assert before['inputSha256'] == after['inputSha256'] and before['pcmSha256'] == after['pcmSha256']
            width = pair[0]['packetBytes']
            raw = (ROOT / 'data' / profile / 'streams' / before['stream']).read_bytes()
            for index, (a, b) in enumerate(zip(before['cycles'], after['cycles'])):
                packet = int.from_bytes(raw[index*width:(index+1)*width], 'big')
                code = (packet >> (width*8-34)) & 15
                saving = a-b
                (positive if code >= 4 else zero).append(saving)
                all_savings.append(saving)
        def summarize(values):
            return dict(frames=len(values), totalCycles=sum(values),
                        minCycles=min(values) if values else None,
                        maxCycles=max(values) if values else None,
                        meanCycles=sum(values)/len(values) if values else None)
        comparisons.append(dict(profile=profile, flashChangeTable1Minus0=pair[1]['flashBytes']-pair[0]['flashBytes'],
                                staticSramChange=0, frameCycleSavingsTable0Minus1=summarize(all_savings),
                                positiveGainFrameSavings=summarize(positive), zeroGainFrameSavings=summarize(zero)))

    for item in build['scalarBinaryIdentity']:
        directory = ROOT / 'scalar-prior' / item['fixture']
        fresh = ROOT / 'source/build/nb1-pitch-unit' / item['fixture']
        report = read(directory / 'verification.json')
        assert raw_sha(directory / 'unit.bin') == raw_sha(fresh / 'unit.bin') == item['binarySha256'] == report['binarySha256']
        assert source_sha(directory / 'verification.json') == item['reportSha256']
        assert report['all128PitchCodes'] and report['originalThresholdTableAndSelectionExact']
        assert report['exactFlashAddresses'] and report['lookupHasNoMuls'] and report['calleeSavedAndR1Returns'] == 512
        assert report['values'] == prior['values']
    for export in build['portableExports']:
        directory = ROOT / export['export']
        assert source_sha(directory / 'src/nb1_pitch.h') == export['helperSha256'] == source_sha(ROOT / 'source/src/nb1_pitch.h')
        assert source_sha(directory / 'sources.json') == export['sourcesManifestSha256']
        manifest = read(directory / 'SHA256.json')
        for name, digest in manifest.items():
            assert raw_sha(directory / name) == digest
        assert export['helperIncluded'] and export['polynomialExplicitlySelectable'] and not export['cDecoderExecuted']
    # Reuse pinned byte identities, checking the actual local tool files again.
    tools = read(ROOT / 'tool-provenance.json')['toolsByteSha256']
    for name, digest in tools.items():
        if name.startswith('avr/'):
            path = args.toolchains_root / 'avr-7.3.0' / name[4:]
        elif name.startswith('node/'):
            path = args.toolchains_root / 'node-22.22.3' / name[5:]
        else:
            assert name.startswith('avr8js/')
            path = args.avr8js_root / name[7:]
        assert raw_sha(path) == digest, name
    assert tools['avr/bin/avr-gcc.exe'] == build['compilerSha256']
    retained = ['build_admission.py', 'run_screen.py', 'audit_admission.py', 'verify_avr.mjs', 'verify_wb.mjs',
                'source.json', 'build.json', 'screen.json', 'data.json', 'tool-provenance.json', 'cookbook-addition.md']
    result = dict(scope='Frozen whole-image decoder-mailbox ASM controls plus bounded independent PCM/reset screens; full IRQ admission remains separate',
                  target='ATmega328P / AVR5 / GNU ABI', compiler='AVR GCC 7.3.0', simulator='avr8js 0.21.1',
                  sourceHashMode='UTF-8 source/report bytes normalized to LF; external tool/vendor-device byte hashes unchanged',
                  frozenSourceManifestSha256=source_sha(ROOT / 'source.json'),
                  callerSha256=source_sha(ROOT / 'source/src/lowrate_excitation.h'),
                  helperSha256=source_sha(ROOT / 'source/src/nb1_pitch.h'),
                  priorScalarReceiptSha256=source_sha(ROOT / 'source/reports/nb1-pitch-unit.json'),
                  scalarSourcesAllMatched=True, scalarRebuilds=build['scalarBinaryIdentity'],
                  portableExports=build['portableExports'], measurements=rows, comparisons=comparisons,
                  corpus=data['streams'], sourceSha256={name: source_sha(ROOT/name) for name in retained},
                  toolsByteSha256=tools,
                  cDecoderExecuted=False, includesInterrupts=False, physicalBoardTested=False,
                  limitations=['384 frames per image on coverage/English/Russian excerpts; not full-corpus admission',
                               'Mailbox-image Flash is measured; player firmware may link differently',
                               'Only the private pitch domain 17..144 is admitted',
                               'Final combined production timing/PCM/IRQ/stack gates belong to root'])
    path = ROOT / 'receipt.json'
    if args.record:
        path.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    else:
        assert read(path) == result
    print(('Recorded' if args.record else 'Verified') + ' pitch-root admission receipt: ' + source_sha(path))


if __name__ == '__main__':
    main()
