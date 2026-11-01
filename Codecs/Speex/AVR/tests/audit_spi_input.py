#!/usr/bin/env python3
"""Check source-bound long-file SPI/PWM evidence; optionally rebuild exact images."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[2]
PROFILES = {'nb11': (1200, 28), 'wb395': (3600, 10), 'wb575': (2200, 15),
            'wb775': (1800, 20), 'wb128': (2200, 32), 'wb395-production': (3600, 10)}


def digest(path, text=False):
    data = path.read_bytes()
    return hashlib.sha256(data.replace(b'\r\n', b'\n') if text else data).hexdigest()


def read(name):
    return json.loads((ROOT/'reports'/name).read_text())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--corpus', type=Path, help='Prepared SPI streams/oracles for hash checks or rebuilds')
    p.add_argument('--avr-gcc', help='Rebuild six final ASM images; no decoder simulations')
    p.add_argument('--wasm-clang', help='Rebuild the host-only model')
    p.add_argument('--wasm-sysroot', type=Path)
    args = p.parse_args()
    admission = read('spi-input-admission.json')
    for name, sha in admission['sourceSha256'].items():
        assert digest(REPO/name, True) == sha, name
    for name, sha in admission['reportSha256'].items():
        assert digest(ROOT/'reports'/name, True) == sha, name
    assert digest(ROOT/'reports/low-final-admission.json', True) == admission['lowRateAdmissionSha256']
    subprocess.run([sys.executable, ROOT/'tests/audit_low_rates.py'], check=True)
    driver = digest(REPO/'Codecs/shared/avr-spi-flash/AvrSpiFlashReader.h', True)
    corpus = {row['profile']: row for row in read('spi-input-corpus.json')['streams']}
    total = 0
    for label, (frames, width) in PROFILES.items():
        report = read('spi-input-'+label+'.json')
        metadata = report['input']
        binding = corpus[label.split('-')[0]]
        assert report['passed'] and report['pwmExact'] and report['fullHistoryWithoutReset']
        assert report['includesInterrupts'] and not report['physicalBoardTested']
        assert report['frames'] == metadata['frames'] == frames
        assert metadata['packetBytes'] == width and metadata['streamBytes'] == frames*width > 32768
        assert metadata['lowRates'] == 7 and metadata['nb4Enabled'] and metadata['backend'] == 'asm'
        assert metadata['driverSha256'] == driver
        assert report['modelWasmSha256'] == admission['modelWasmSha256']
        assert metadata['inputSha256'] == binding['inputSha256']
        assert report['pcmSha256'] == binding['pcmSha256']
        assert report['s16Exact'] == metadata['capturePcm'] == (label != 'wb395-production')
        assert report['underruns'] == 0 and report['minQueuedSamplesBeforeOutput'] > 0
        assert report['flashBytes'] <= 32768 and report['freeSramAtPeak'] > 0
        assert report['staticSramBytes']+report['peakStackBytes']+report['freeSramAtPeak'] == 2048
        period = 1000 if metadata['wideband'] else 2000
        assert report['timerIntervalMinCycles'] >= period-10 and report['timerIntervalMaxCycles'] <= period+10
        assert metadata['flashAddress'] < 65536 < metadata['flashAddress']+metadata['streamBytes']
        assert report['spiWireCycles'] == 16*(metadata['streamBytes']+5)
        assert report['spiBytesWithInterruptsEnabled'] >= metadata['streamBytes']-width
        assert report['spiCompletionMinCycles'] >= 16 and report['spiCompletionMaxCycles'] <= 26
        stats = report['modelStats']
        assert stats['readBytes'] == metadata['streamBytes']
        assert stats['transferCalls'] == stats['selectedBytes'] == metadata['streamBytes']+5
        assert [stats[key] for key in ['commandBytes', 'addressBytes', 'dummyBytes', 'csAssertions', 'csDeassertions']] == [1, 3, 1, 1, 1]
        assert stats['unsupportedCommands'] == stats['resets'] == 0
        if args.corpus:
            folder = args.corpus/label.split('-')[0]
            assert digest(folder/'long.spxraw') == binding['inputSha256']
            assert digest(folder/'long.pcm') == binding['pcmSha256']
        total += frames
    assert total == 14600
    model = read('spi-input-model.json')
    assert model['passed'] and model['wasmSha256'] == admission['modelWasmSha256']
    assert model['payloadBytes'] == 70003 and model['modelStats']['readBytes'] == 70003
    compile_only = read('spi-input-c-compile.json')
    assert compile_only['decoderExecuted'] is False and compile_only['images']
    assert all(row['backend'] == 'c' and row['flashBytes'] <= 32768 for row in compile_only['images'])
    if args.avr_gcc:
        if not args.corpus: p.error('--avr-gcc requires --corpus')
        output = ROOT/'build/spi-rebuild-identity'
        subprocess.run([sys.executable, ROOT/'tests/build_spi_matrix.py', '--avr-gcc', args.avr_gcc,
                        '--corpus', args.corpus, '--out', output], check=True)
        for label in PROFILES:
            assert digest(output/label/'player.bin') == read('spi-input-'+label+'.json')['input']['binarySha256'], label
    if args.wasm_clang:
        sys.path.insert(0, str(ROOT/'tools'))
        import build_spi_player
        output = ROOT/'build/spi-model-rebuild'
        build_spi_player.model(args.wasm_clang, output, args.wasm_sysroot)
        assert digest(output/'model.wasm') == admission['modelWasmSha256']
    print('PASS: source-bound SPI/PWM admission, 14600 continuous frames / zero underruns'
          + ('; six ASM images rebuilt identically' if args.avr_gcc else ''))


if __name__ == '__main__':
    main()
