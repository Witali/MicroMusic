#!/usr/bin/env python3
"""Audit exact seven-MUL noise speed evidence and source overlay."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def read(name):
    return json.loads((ROOT/'reports'/name).read_text())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--corpus', type=Path, help='Optional original lower-profile corpus')
    p.add_argument('--avr-gcc', help='Optionally rebuild five final decoder/IRQ/SPI images')
    p.add_argument('--spi-stream', type=Path, help='Original long WB3.95 stream, required for rebuild')
    args = p.parse_args()
    admission = read('noise-speed-admission.json')
    baseline = read('low-final-admission.json')
    assert digest(ROOT/'reports/low-final-admission.json') == admission['baselineAdmissionSha256']
    changed = []
    for name, sha in baseline['sourceSha256'].items():
        if digest(ROOT/name) != sha: changed.append(name)
    assert changed == ['src/lowrate_noise.c'], changed
    for name, sha in admission['sourceSha256'].items():
        assert digest(ROOT/name) == sha, name
    for name, sha in admission['reportSha256'].items():
        assert digest(ROOT/'reports'/name) == sha, name
    for name, sha in read('spi-input-admission.json')['sourceSha256'].items():
        assert digest(ROOT.parents[2]/name) == sha, name
    unit = read('noise-speed-unit.json')
    assert unit['seeds'] == unit['calleeSavedAndR1Returns'] == 135243
    assert unit['cAndAsmExact'] and unit['arbitraryCalleeSavedPatterns']
    assert unit['asmMulsPerSeed'] == 7 and unit['genericCMulsPerSeed'] == 10
    for mode in ['nb215', 'wb395']:
        after, before = read('noise-speed-'+mode+'.json'), read('low-final-'+mode+'.json')
        assert after['frames'] == before['frames'] == 10627
        assert after['staticSramBytes'] == before['staticSramBytes']
        assert after['maxCycles'] < before['maxCycles']
        assert after['flashBytes']-before['flashBytes'] == 54
        assert len(after['streams']) == len(before['streams']) == 18
        for a, b in zip(after['streams'], before['streams']):
            assert a.get('name', a.get('stream')) == b.get('name', b.get('stream'))
            assert a['frames'] == b['frames'] and a.get('reset', a.get('resetVerified'))
            if mode == 'wb395': assert a['pcmExact']
        if args.corpus:
            bindings = [row for row in read('low-final-corpus.json')['streams'] if row['profile'] == mode]
            for row in bindings:
                for sub, suffix, key in [('streams', '.spxraw', 'inputSha256'), ('oracle', '.pcm', 'pcmSha256')]:
                    path = args.corpus/mode/sub/(Path(row['stream']).stem+suffix)
                    assert hashlib.sha256(path.read_bytes()).hexdigest() == row[key]
    for suffix, load in [('normal', 0), ('load6', 19200)]:
        irq = read('noise-speed-irq-'+suffix+'.json')
        assert irq['frames'] == 10627 and irq['extraCpuCyclesPerFrame'] == load
        assert irq['includesInterrupts'] and irq['underruns'] == 0 and len(irq['streams']) == 18
        for row in irq['streams']:
            assert row['s16AndPwmExact'] and row['fullHistoryWithoutChunkReset']
            assert row['underruns'] == 0 and row['timerIntervalMinCycles'] >= 990 and row['timerIntervalMaxCycles'] <= 1010
    spi = read('noise-speed-spi.json')
    assert spi['passed'] and spi['pwmExact'] and spi['frames'] == 3600
    assert spi['includesInterrupts'] and spi['underruns'] == 0 and spi['fullHistoryWithoutReset']
    assert spi['modelStats']['readBytes'] == 36000 and spi['modelStats']['unsupportedCommands'] == 0
    assert spi['pwmSha256'] == read('spi-input-wb395-production.json')['pwmSha256']
    for mode, rejects in [('nb', 6144), ('wb', 7168)]:
        api = read('noise-speed-api-'+mode+'.json')
        assert api['pcmExact'] and api['frames'] == 1024 and api['rejectedCalls'] == rejects
        assert api['mixedEnabledModes'] == [1, 2, 8, 3, 4]
    identity = read('noise-speed-identities.json')
    assert len(identity['minimalAsm']) == 4 and all(row['byteIdentical'] for row in identity['minimalAsm'])
    assert len(identity['cPlayers']) == 2 and all(row['byteIdentical'] for row in identity['cPlayers'])
    export = read('noise-speed-export.json')
    assert not export['handwrittenAssembly'] and not export['duplicateSources']
    rejected = read('noise-speed-rejected-load8.json')
    assert not rejected['passed'] and rejected['underruns'] == 380 and rejected['framesAttempted'] == 128
    if args.avr_gcc:
        if not args.spi_stream: p.error('--avr-gcc requires --spi-stream')
        sys.path.insert(0, str(ROOT/'tools'))
        import build
        import build_wb
        out = ROOT/'build/noise-rebuild'
        build.avr(args.avr_gcc, backend='asm', packet_bytes=6, enable_nb4=True, low_rates=7, destination=out/'nb215')
        build_wb.avr(args.avr_gcc, 'asm', packet_bytes=10, enable_nb4=True, low_rates=7, destination=out/'wb395')
        targets = [('nb215/speex-test.bin', read('noise-speed-nb215.json')['binarySha256']),
                   ('wb395/wb.bin', read('noise-speed-wb395.json')['binarySha256'])]
        for label, load in [('normal', 0), ('load6', 19200)]:
            subprocess.run([sys.executable, ROOT/'tools/build_wb_stream_test.py', '--avr-gcc', args.avr_gcc,
                            '--packet-bytes', '10', '--low-rates', '7', '--enable-nb4',
                            '--frame-load-cycles', str(load), '--out', out/label], check=True)
            targets.append((label+'/wb.bin', read('noise-speed-irq-'+label+'.json')['binarySha256']))
        subprocess.run([sys.executable, ROOT/'tools/build_spi_player.py', '--avr-gcc', args.avr_gcc,
                        '--backend', 'asm', '--wideband', '--enable-nb4', '--stream', args.spi_stream,
                        '--out', out/'spi'], check=True)
        targets.append(('spi/player.bin', spi['input']['binarySha256']))
        for name, sha in targets:
            assert hashlib.sha256((out/name).read_bytes()).hexdigest() == sha, name
    # Historical audits pin the previous implementation. This overlay verifies
    # their unchanged source contracts and adds evidence for the one changed C file.
    print('PASS: seven-MUL exact RNG, 21254 decoder / 21254 IRQ / 3600 SPI frames; C identity and ABI'
          + ('; five images rebuilt identically' if args.avr_gcc else ''))


if __name__ == '__main__': main()
