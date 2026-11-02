"""Build and admit real ATmega328P speech images for the browser catalog.

No encoding or network access occurs here. Inputs are completed LPX streams
and optional raw Speex packets. Generated source, logs, oracles and ELF files
remain in a fresh ignored build directory. --export-web copies only admitted
HEX files and their small public catalog into the local website checkout.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
LPX = REPO / 'Codecs/LPX/01_ACTIVE_Q0_CODEC'
SPEEX = REPO / 'Codecs/Speex/AVR'


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8', newline='\n')


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def invoke(command, log):
    result = subprocess.run([str(v) for v in command], capture_output=True)
    log.write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError('Build/admission failed; inspect ignored log: ' + log.name)
    return result.stdout.decode('utf-8')


def web_admission(node, folder, codec, oracle):
    invoke([node, REPO / 'web-player/scripts/verify-arduino-firmware.mjs',
            '--firmware', folder, '--codec', codec, '--oracle', oracle], folder / 'web-admission-private.log')
    report = json.loads((folder / 'web-core-verification.json').read_text(encoding='utf-8'))
    if not report['passed'] or report['underruns'] or report['lostInterrupts']:
        raise ValueError('Real-time browser firmware admission failed')
    return report


def entry(identity, order, title, codec, stream, hex_path, program, static, report):
    name = identity + '.hex'
    return dict(id=identity, order=order, title=title,
        description='«И того, и другого, и можно без хлеба» · Arduino Uno / Nano, ATmega328P · 16 МГц',
        kind='speech', codec=codec, device='atmega328p', board='arduino-16mhz',
        executionEngine='avr8js', supportedEngines=['avr8js'],
        cpuHz=16000000, sampleHz=8000, pwmHz=62500, audioChannels=1, playOnce=True,
        phraseSamples=report['samples'], playbackCycles=report['playbackCycles'],
        flashHex=hex_path.read_text(encoding='ascii'), source='firmware-atmega328p/' + name,
        flashBytes=report['flashBytes'], flashSha256=report['flashSha256'],
        programFlashBytes=program, encodedBytes=len(stream), staticRamBytes=static,
        peakStackBytes=report['peakStackBytes'], freeSramAtPeak=report['freeSramAtPeak'],
        eepromBytes=0, pwmOutput=report['pwmOutput'],
        outputPin='D3' if report['pwmOutput'] == 'OC2B' else 'D9',
        bitrateBps=len(stream)*8*8000/report['samples'],
        originalAudioUrl='audio/lpx-bread/original.wav')


def build_lpx(args, output):
    sys.path.insert(0, str(LPX / 'tools'))
    import build_release_player as player
    import speech_compact
    import speech_sparse80
    from standard_metrics import pwm_duties
    rows = []
    for rate, path in [(2, args.lpx2), (3, args.lpx3)]:
        stream = path.read_bytes()
        if (stream[:6] != (b'L4HY\x08\x0f' if rate == 2 else b'L4HY\x05\x04')):
            raise ValueError('Expected sparse80 version8/mode15 at 2k or ordinary v5/P4 at 3k')
        pcm = speech_compact.decode_model(speech_sparse80.expand(stream) if rate == 2 else stream)
        if len(stream)*8*8000 > rate*1000*len(pcm):
            raise ValueError('Complete LPX stream exceeds its advertised rate cap')
        folder = output / ('lpx-' + str(rate) + 'k')
        with (output / ('lpx-' + str(rate) + 'k-build-private.log')).open('w', encoding='utf-8') as log, contextlib.redirect_stdout(log):
            verification = player.simulate([stream], folder, args.avr_bin, args.observer,
                queue=256, assembly=True, sparse80=rate == 2,
                lib=args.simavr_lib, wsl=args.wsl, expected_pwm=pwm_duties(pcm).tobytes())
        cost = verification['cost']
        report = web_admission(args.node, folder, 'lpx', folder / 'valid.pcm8')
        if cost['flash_bytes'] != report['flashBytes']:
            raise ValueError('ELF and browser HEX Flash accounting disagree')
        rows.append(entry('lpx-bread-' + str(rate) + 'k-arduino', rate-1,
            'LPX · ' + str(rate) + ' кбит/с', 'lpx-sparse80' if rate == 2 else 'lpx-v5', stream, folder / 'player.hex',
            cost['program_flash_bytes'], cost['static_sram_bytes'], report))
    return rows


def build_speex(args, output):
    if args.speex2 is None:
        return []
    sys.path.insert(0, str(SPEEX / 'tools'))
    build = load_module('arduino_speex_build', SPEEX / 'tools/build.py')
    # This oracle uses the untouched pinned upstream fixed-point NB decoder,
    # separate from the specialized AVR arithmetic and the browser emulator.
    with (output / 'speex-oracle-prepare-private.log').open('w', encoding='utf-8') as log, contextlib.redirect_stdout(log):
        _, reference = build.prepare('reference')
    oracle = output / ('speex-oracle.exe' if os.name == 'nt' else 'speex-oracle')
    command = [args.host_cc, '-x', 'c', '-std=c11', '-O2', '-fwrapv', '-fno-strict-aliasing',
        '-Wno-pointer-to-int-cast', '-D_CRT_SECURE_NO_WARNINGS', *['-D'+d for d in build.DEFINES],
        '-I'+str(reference/'include'), '-I'+str(reference/'libspeex'),
        *[reference/'libspeex'/(s+'.c') for s in build.SOURCES],
        SPEEX/'tests/decode_nb_packets.c', '-o', oracle]
    if os.name != 'nt':
        command.append('-lm')
    invoke(command, output / 'speex-oracle-build-private.log')
    rows = []
    for order, label, width, low_rates, path in [(3, 'compact', 6, 4, args.speex2), (4, 'quality', 20, 0, args.speex8)]:
        folder = output / ('speex-' + label)
        folder.mkdir()
        invoke([sys.executable, SPEEX/'tools/build.py', '--avr-gcc',
            args.avr_bin / ('avr-gcc.exe' if os.name == 'nt' else 'avr-gcc'),
            '--backend', 'asm', '--player', path, '--packet-bytes', width,
            '--low-rates', low_rates, '--out', folder], folder/'build-private.log')
        pcm = folder / 'upstream-oracle.pcm'
        invoke([oracle, width, path, pcm], folder / 'oracle-private.log')
        report = web_admission(args.node, folder, 'speex', pcm)
        stream, binary = path.read_bytes(), (folder/'speex-player.bin').read_bytes()
        nm = args.avr_bin / ('avr-nm.exe' if os.name == 'nt' else 'avr-nm')
        symbols = invoke([nm, '-S', '--defined-only', folder/'speex-player.elf'], folder/'symbols-private.log')
        samples = [tuple(int(v, 16) for v in match) for match in re.findall(
            r'^([0-9a-f]+)\s+([0-9a-f]+)\s+\w\s+sample_data(?:\.[^\r\n]*)?\r?$', symbols, re.M)]
        if len(samples) != 1 or samples[0][1] != len(stream) or binary[samples[0][0]:samples[0][0]+len(stream)] != stream or binary.count(stream) != 1:
            raise ValueError('Cannot prove unique exact embedded Speex audio')
        size = args.avr_bin / ('avr-size.exe' if os.name == 'nt' else 'avr-size')
        sections = invoke([size, folder/'speex-player.elf'], folder/'size-private.log')
        text, data, bss = map(int, re.search(r'^\s*(\d+)\s+(\d+)\s+(\d+)\s+', sections, re.M).groups())
        if text+data != len(binary) or len(binary) != report['flashBytes']:
            raise ValueError('Speex ELF, binary and browser HEX Flash accounting disagree')
        rows.append(entry('speex-bread-' + label + '-arduino', order,
            'Speex · ' + ('2' if width == 6 else '8') + ' кбит/с', 'speex-nb',
            stream, folder/'speex-player.hex', text+data-len(stream), data+bss, report))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['lpx2', 'lpx3', 'avr-bin', 'observer', 'simavr-lib', 'output']:
        parser.add_argument('--'+name, required=True, type=Path)
    parser.add_argument('--wsl')
    parser.add_argument('--node', default='node')
    parser.add_argument('--host-cc', default='clang')
    parser.add_argument('--speex2', type=Path)
    parser.add_argument('--speex8', type=Path)
    parser.add_argument('--export-web', action='store_true', help='Copy admitted files into the local website checkout; does not publish')
    args = parser.parse_args()
    if bool(args.speex2) != bool(args.speex8):
        parser.error('Supply both Speex streams, or neither')
    for name in ['lpx2', 'lpx3', 'avr_bin', 'observer', 'simavr_lib', 'output', 'speex2', 'speex8']:
        value = getattr(args, name)
        if value is not None:
            setattr(args, name, value.resolve())
    if args.output.exists() or not args.output.is_relative_to((REPO/'build').resolve()):
        raise ValueError('Use a fresh directory under repository ignored build/')
    args.output.mkdir(parents=True)
    rows = build_lpx(args, args.output) + build_speex(args, args.output)
    catalog = dict(schemaVersion=1, defaultId=rows[0]['id'], entries=rows)
    save(args.output/'firmware-atmega328p.json', catalog)
    for row in rows:
        (args.output/(row['id']+'.hex')).write_text(row['flashHex'], encoding='ascii', newline='\n')
    if args.export_web:
        destination = REPO/'web-player/firmware-atmega328p'
        destination.mkdir(exist_ok=True)
        for row in rows:
            shutil.copyfile(args.output/(row['id']+'.hex'), destination/(row['id']+'.hex'))
        shutil.copyfile(args.output/'firmware-atmega328p.json', REPO/'web-player/firmware-atmega328p.json')
    for row in rows:
        print(json.dumps({key:row[key] for key in ['id', 'encodedBytes', 'flashBytes', 'programFlashBytes', 'staticRamBytes', 'peakStackBytes', 'playbackCycles']}))


if __name__ == '__main__':
    main()
