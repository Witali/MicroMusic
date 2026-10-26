#!/usr/bin/env python3
"""Decode existing human-voice fixtures with same-option upstream and AVR images."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import wave

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_frontend as front
import verify_decoder as original
from verify_decoder import metrics
from study_fixed_precision import admissible
from audit_decoder_memory import device_memory

ROOT = front.ROOT
REPO = ROOT.parents[1]
BUILD = REPO / 'build/codec2/existing-speech'


def write_wav(path, pcm):
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(pcm)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', action='store_true')
    parser.add_argument('--host-only', action='store_true')
    args = parser.parse_args()
    if args.record and args.host_only:
        parser.error('--record requires complete AVR execution')
    fixture_path = ROOT / 'fixtures/existing-speech.json'
    fixture = json.loads(fixture_path.read_text(encoding='utf-8'))
    assert [c['id'] for c in fixture['clips']] == ['balloon', 'owl', 'chego', 'otvechaesh']
    assert front.digest(ROOT / 'tools/prepare_existing_speech.py') == fixture['generator_sha256']
    BUILD.mkdir(parents=True, exist_ok=True)
    for clip in fixture['clips']:
        assert front.digest(REPO / clip['source_path']) == clip['source_sha256']
        wav_path = ROOT / clip['source_8k_wav']
        assert front.digest(wav_path) == clip['source_8k_wav_sha256']
        with wave.open(str(wav_path), 'rb') as w:
            assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (1, 2, 8000, clip['frames'] * 160)
            pcm = w.readframes(w.getnframes())
        assert hashlib.sha256(pcm).hexdigest() == clip['input_pcm_sha256']
        packets = b''.join(bytes.fromhex(x) for x in clip['packets_hex'])
        assert len(packets) == clip['frames'] * 8
        assert hashlib.sha256(packets).hexdigest() == clip['packet_sha256']
        (BUILD / (clip['id'] + '.packets')).write_bytes(packets)

    vendor = front.VENDOR / 'src'
    manifest = json.loads((front.VENDOR / 'UPSTREAM.json').read_text())
    for item in manifest['files']:
        assert front.digest(front.VENDOR / item['path']) == item['sha256']
    original.BUILD = BUILD / 'oracle-build'
    selected = original.reference_sources('clang')
    oracle_body = (ROOT / 'tests/upstream_decode.c').read_text()
    assert oracle_body.count('assert(argc == 3);') == 1
    assert oracle_body.count('c2->lpc_pf = c2->bass_boost = 1;') == 1
    oracle_body = oracle_body.replace('assert(argc == 3);', 'assert(argc == 4);')
    oracle_body = oracle_body.replace('c2->lpc_pf = c2->bass_boost = 1;',
        'int pf = atoi(argv[3]); assert(pf == 0 || pf == 1); c2->lpc_pf = c2->bass_boost = pf;')
    oracle_source = BUILD / 'upstream-listening.c'
    oracle_source.write_bytes(oracle_body.encode())
    suffix = '.exe' if os.name == 'nt' else ''
    libm = [] if os.name == 'nt' else ['-lm']
    includes = ['-I' + str(ROOT / 'include'), '-I' + str(ROOT / 'src'), '-I' + str(vendor)]
    oracle = BUILD / ('upstream' + suffix)
    front.run(['clang', '-O2', '-fno-strict-aliasing', '-ffp-contract=off',
        '-D_CRT_SECURE_NO_WARNINGS', '-DCODEC2_MODE_EN_DEFAULT=0', '-DCODEC2_MODE_3200_EN=1',
        *includes, '-I' + str(original.BUILD / 'include'), *selected,
        *[vendor / n for n in ('pack.c', 'codec2_fft.c', 'lsp.c', 'postfilter.c', 'kiss_fft.c', 'kiss_fftr.c')],
        oracle_source, '-o', oracle, *libm])

    profiles = []
    sources_bound = {}
    for name, pf in [('matrix', 1), ('nopost', 0)]:
        baseline_path = ROOT / ('reports/' + name + '-decoder.json')
        baseline = json.loads(baseline_path.read_text())
        assert baseline['avr_execution']['complete']
        for source, wanted in baseline['sources'].items():
            assert front.digest(ROOT / source) == wanted, source
        sources_bound.update(baseline['sources'])
        folder = BUILD / name
        folder.mkdir(exist_ok=True)
        flags = [x for x in baseline['avr_build']['defines'] if '_CHECKS=' not in x]
        checks = ['-DCODEC2_' + n + '_CHECKS=1' for n in ('LPC_MATH', 'ANALYSIS', 'FIXED', 'WEIGHT')]
        source_names = ['src/' + ('canonical_decoder.c' if pf else 'nopost_decoder.c'),
            'src/adaptive_analysis.c', 'src/matrix_analysis.c', 'src/fixed_inverse.c',
            'src/compact_fft.c', 'src/parameters.c', 'src/canonical_lpc.c', 'src/lpc_math.c']
        if pf:
            source_names += ['src/fixed_weight_sums32.c', 'src/fixed_fifth.c']
        program = folder / ('native' + suffix)
        front.run(['clang', '-O2', '-fno-strict-aliasing', '-ffp-contract=off',
            '-D_CRT_SECURE_NO_WARNINGS', *flags, *checks, *includes,
            *[ROOT / n for n in source_names], ROOT / 'tests/hybrid_decode.c', '-o', program, *libm])
        streams = []
        for clip in fixture['clips']:
            ident = clip['id']
            packets = BUILD / (ident + '.packets')
            expected = folder / (ident + '.upstream.pcm')
            output = folder / (ident + '.native.pcm')
            front.run([oracle, packets, expected, str(pf)])
            front.run([program, packets, output], capture_output=True)
            assert len(expected.read_bytes()) == clip['frames'] * 320
            record = {'name': ident, 'frames': clip['frames'], 'packet_sha256': clip['packet_sha256'],
                'oracle_sha256': front.digest(expected), 'native_output_sha256': front.digest(output),
                **metrics(output.read_bytes(), expected.read_bytes())}
            assert admissible(record), record
            streams.append(record)
            write_wav(folder / (ident + '.upstream.wav'), expected.read_bytes())
            write_wav(folder / (ident + '.native.wav'), output.read_bytes())
            print(json.dumps({'profile': name, **record}), flush=True)
        profile = {'name': name, 'lpc_postfilter': bool(pf), 'streams': streams,
            'baseline_report_sha256': front.digest(baseline_path), 'native_binary_sha256': front.digest(program)}
        if not args.host_only:
            memory = device_memory('avr-gcc', 'atmega64a')
            assert memory == baseline['avr_build']['manufacturer_header_memory']
            old_elf = REPO / ('build/codec2/' + name + '/atmega64a/decoder.elf')
            # Reuse the already fully executed machine code, not a new build.
            front.run(['avr-objcopy', '-O', 'binary', old_elf, folder / 'decoder.bin'])
            assert front.digest(folder / 'decoder.bin') == baseline['avr_build']['binary_sha256']
            with (folder / 'symbols.txt').open('wb') as out:
                front.run(['avr-nm', '-n', old_elf], stdout=out)
            profile['avr_image'] = {'binary_sha256': front.digest(folder / 'decoder.bin'),
                'symbols_sha256': front.digest(folder / 'symbols.txt'), 'manufacturer_header_memory': memory}
        profiles.append(profile)
    report = {'fixture_sha256': front.digest(fixture_path), 'profiles': profiles,
        'oracle_binary_sha256': front.digest(oracle), 'oracle_adaptation_sha256': front.digest(oracle_source),
        'upstream_manifest_sha256': front.digest(front.VENDOR / 'UPSTREAM.json'),
        'host_compiler': front.run(['clang', '--version'], capture_output=True, text=True).stdout.splitlines()[0]}
    if not args.host_only:
        front.dump(BUILD / 'host-verification.json', report)
        front.run(['node', ROOT / 'tests/verify_existing_speech_avr.mjs'])
        report['avr_execution'] = json.loads((BUILD / 'avr-execution.json').read_text())
    names = ['tools/prepare_existing_speech.py', 'tools/verify_existing_speech.py',
             'tests/verify_existing_speech_avr.mjs', 'tests/upstream_decode.c', 'tests/hybrid_decode.c']
    report['sources'] = {**sources_bound, **{n: front.digest(ROOT / n) for n in names}}
    report['verified_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    report['scope'] = 'Independent existing human-performance speech snippets, standard 3200 packets. Same-option upstream versus native and original verified ATmega64A images, reset per clip. No TTS, new algorithm tuning, listening score, active IRQ, board or real-time admission.'
    front.dump(ROOT / 'reports/existing-speech.json' if args.record else BUILD / 'verification.json', report)


if __name__ == '__main__':
    main()
