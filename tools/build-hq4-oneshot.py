"""Build and verify a retained or explicitly experimental one-shot HQ4 image.

The real AVR emits one complete phrase, followed by midpoint PWM forever.
An explicit --stream candidate never replaces the retained release stream.
The verification EEPROM is erased test scaffolding; this firmware uses no EEPROM.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT/'ATtiny13A/Sound/codec/oneshot/hq4.S'
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from hq4_core import decode, unpack_stream
from output_level import choose_gain, scale_pcm, describe_level

_spec = importlib.util.spec_from_file_location('tiny_build_helpers', ROOT/'tools/build-tiny-speech.py')
_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helpers)
run, parse_symbols, intel_hex = _helpers.run, _helpers.parse_symbols, _helpers.intel_hex


def sha(data):
    return hashlib.sha256(data).hexdigest()


def validate_stream(payload):
    """Reject incomplete frames and EOF bytes before the permissive legacy reader.

    The assembly appends its own EOF. The first frame must initialize all lattice
    coefficients because the firmware only clears filter state on startup.
    """
    offset = 0
    frames = 0
    while offset < len(payload):
        header = payload[offset]
        offset += 1
        if header == 255:
            raise ValueError('HQ4 input stream must omit the EOF marker and trailing data')
        if header & 0xc0 == 0xc0:
            if header & 0x3c:
                raise ValueError('Invalid extended HQ4 duration header')
            if offset >= len(payload):
                raise ValueError('Truncated HQ4 pitch byte')
            if payload[offset] > 126:
                raise ValueError('HQ4 pitch must be between 0 and 126')
            offset += 1
        if offset >= len(payload):
            raise ValueError('Truncated HQ4 spectral header')
        spectral = payload[offset] >> 6
        offset += 1
        if not frames and spectral != 0:
            raise ValueError('First HQ4 frame must initialize all four coefficient bytes')
        count = (4, 0, 2, 2)[spectral]
        if offset+count > len(payload):
            raise ValueError('Truncated HQ4 coefficient update')
        offset += count
        frames += 1
    if not frames:
        raise ValueError('HQ4 speech stream must contain at least one frame')
    return unpack_stream(payload)


def load_stream(clip, stream=None, expected_samples=None):
    """Load and validate a candidate against the retained phrase duration."""
    if not re.fullmatch(r'[a-z0-9_-]+', clip):
        raise ValueError('Invalid retained HQ4 clip name')
    retained_source = CODEC/'release'/clip/'speech.hq'
    if expected_samples is None:
        retained_payload = retained_source.read_bytes()
        _, retained_durations = validate_stream(retained_payload)
        required_samples = int(np.sum(retained_durations))
    else:
        if (stream is None or isinstance(expected_samples, bool)
                or not isinstance(expected_samples, int) or expected_samples <= 0
                or expected_samples % 64):
            raise ValueError('A new recording requires an explicit stream and positive multiple-of-64 sample count')
        required_samples = expected_samples
    source = Path(stream).resolve() if stream is not None else retained_source
    payload = source.read_bytes()
    if stream is not None:
        match = re.search(r'^\.set VOICE_ADDR,(0x[0-9a-fA-F]+|[0-9]+)\s*$',
                          TEMPLATE.read_text(encoding='utf-8'), re.MULTILINE)
        if not match:
            raise ValueError('One-shot HQ4 template must expose its stream address')
        capacity = 1024-int(match[1], 0)-1
        if len(payload) > capacity:
            raise ValueError(f'Experimental HQ4 stream exceeds the {capacity}-byte Flash budget')
    frames, durations = validate_stream(payload)
    if int(np.sum(durations)) != required_samples:
        raise ValueError('HQ4 candidate must preserve the retained complete phrase duration')
    phrase = decode(frames, durations, 0)
    prefix_sha = sha(phrase.tobytes())
    frozen_prefix_sha = None
    if stream is None and clip == 'vinni':
        retained = json.loads((ROOT/'ATtiny13A/Sound/research/speech-showcase/vinni/retained-prefix.json').read_text(encoding='utf-8'))
        frozen_prefix_sha = retained['firstLoopPcmSha256']
        if len(phrase) != retained['phraseSamples'] or sha(payload) != retained['streamSha256']:
            raise ValueError('HQ4 retained stream or complete phrase duration differs')
        if prefix_sha != frozen_prefix_sha:
            raise ValueError('HQ4 numerical prefix differs from the retained real AVR recording')
    return source, payload, phrase, frozen_prefix_sha


def build(clip, output, avr_bin=None, node='node', stream=None, expected_samples=None, maximize_output=False):
    source, payload, phrase, frozen_prefix_sha = load_stream(clip, stream, expected_samples)
    source_phrase = phrase.copy()
    gain, gain_shift = choose_gain(phrase, 'shift') if maximize_output else (1, 0)
    phrase = scale_pcm(phrase, gain, gain_shift)
    phrase_samples = len(phrase)
    prefix_sha = sha(phrase.tobytes())
    expected = np.concatenate((phrase, np.full(phrase_samples*2, 128, dtype=np.uint8)))
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    for name in ('firmware.elf', 'firmware.bin', 'firmware.hex', 'verification.json', 'actual.raw', 'build.json'):
        (output/name).unlink(missing_ok=True)
    shutil.copyfile(TEMPLATE, output/'firmware.S')
    if maximize_output:
        firmware = (output/'firmware.S').read_text(encoding='utf-8')
        (output/'firmware.S').write_text(f'.set OUTPUT_SHIFT,{gain.bit_length()-1}\n'+firmware, encoding='utf-8', newline='\n')
    (output/'speech.hq').write_bytes(payload)
    (output/'expected.raw').write_bytes(expected.tobytes())
    erased = b'\xff'*64
    (output/'verification-eeprom.bin').write_bytes(erased)
    suffix = '.exe' if os.name == 'nt' else ''

    def executable(name):
        return Path(avr_bin).resolve()/(name+suffix) if avr_bin else name

    compiler = executable('avr-gcc')
    compiler_version = run([compiler, '--version'], output).stdout.splitlines()[0]
    run([compiler, '-mmcu=attiny13', '-nostdlib', '-x', 'assembler', '-c',
         'firmware.S', '-o', 'firmware.o'], output)
    symbols = parse_symbols(run([executable('avr-nm'), '-n', 'firmware.o'], output).stdout)
    sections = run([executable('avr-objdump'), '-h', 'firmware.o'], output).stdout
    (output/'sections.txt').write_text(sections, encoding='utf-8', newline='\n')
    match = re.search(r'^\s*\d+\s+\.text\s+([0-9a-fA-F]+)\b', sections, re.MULTILINE)
    if not match or not all(name in symbols for name in ('code_end', 'voice_data', 'STACK_FLOOR', 'wait_slot')):
        raise ValueError('One-shot HQ4 source must expose code/data, SRAM and wait-loop symbols')
    object_bytes = int(match[1], 16)
    code_bytes, voice_start = symbols['code_end'], symbols['voice_data']
    if voice_start < code_bytes or object_bytes != voice_start+len(payload)+1:
        raise ValueError('Unexpected HQ4 code, stream or EOF layout')
    flash_bytes = (object_bytes+1) & ~1
    inputs = (TEMPLATE, Path(__file__), ROOT/'tools/build-tiny-speech.py',
              CODEC/'hq4_core.py', CODEC/'model.py', ROOT/'tools/verify-tiny-speech.mjs',
              ROOT/'tools/lib/tiny-work-profile.mjs', CODEC/'output_level.py')
    report = dict(schema='micromusic-hq4-oneshot-build-v1', clip=clip,
                  status='oversized' if flash_bytes > 1024 else 'pending', playbackMode='once',
                  hardwareTested=False, cpuHz=9600000, sampleHz=7500, flashLimitBytes=1024,
                  flashBytes=flash_bytes, objectTextBytes=object_bytes,
                  codeBytes=code_bytes, dataBytes=len(payload)+1, streamBytes=len(payload), eofBytes=1,
                  linkerPaddingBytes=flash_bytes-object_bytes, codePaddingBytes=voice_start-code_bytes,
                  eepromLimitBytes=64, eepromBytes=0, eepromUsedBytes=0, eepromSha256=None,
                  phraseSamples=phrase_samples, verifiedLoops=0, silenceSamplesVerified=0,
                  compiler=compiler_version, symbols=symbols, streamSha256=sha(payload),
                  frozenPrefixPcmSha256=frozen_prefix_sha, phrasePcmSha256=prefix_sha,
                  expectedPcmSha256=sha(expected.tobytes()), verificationEepromSha256=sha(erased),
                  imageSha256=None, verification=None,
                  normalizedSourceSha256={str(path.relative_to(ROOT)).replace('\\', '/'):
                    sha(path.read_text(encoding='utf-8').encode('utf-8')) for path in inputs})
    if maximize_output:
        report['outputLevel'] = describe_level(source_phrase, gain, gain_shift)
    if stream is None:
        report['normalizedSourceSha256'][source.relative_to(ROOT).as_posix()] = sha(payload)
    else:
        # Stable fingerprints never contain an absolute scratch path or machine name.
        label = source.relative_to(ROOT).as_posix() if source.is_relative_to(ROOT) else 'external/'+source.name
        report.update(experimental=True, streamInput=dict(sourcePath=label, copiedPath='speech.hq',
                      sha256=sha(payload)), retainedStreamSha256=(
                          sha((CODEC/'release'/clip/'speech.hq').read_bytes()) if expected_samples is None else None))
        if expected_samples is not None:
            report.update(newRecording=True, expectedPhraseSamples=expected_samples)
        report['normalizedSourceSha256']['input/speech.hq'] = sha(payload)
    if flash_bytes <= 1024:
        run([compiler, '-mmcu=attiny13', '-nostdlib', '-Wl,--defsym=__TEXT_REGION_LENGTH__=1024',
             '-Wl,-Ttext=0', '-x', 'assembler', 'firmware.S', '-o', 'firmware.elf'], output)
        run([executable('avr-objcopy'), '-O', 'binary', 'firmware.elf', 'firmware.bin'], output)
        image = (output/'firmware.bin').read_bytes()
        if (len(image) != flash_bytes or image[voice_start:object_bytes] != payload+b'\xff' or
                image[object_bytes:] not in (b'', b'\x00')):
            raise ValueError('Linked HQ4 image changed the input stream or its EOF byte')
        (output/'firmware.hex').write_text(intel_hex(image), encoding='ascii', newline='\n')
        (output/'disassembly.txt').write_text(run([executable('avr-objdump'), '-d', 'firmware.elf'], output).stdout,
                                              encoding='utf-8', newline='\n')
        report['imageSha256'] = sha(image)
        command = [node, ROOT/'tools/verify-tiny-speech.mjs', output/'firmware.bin', output/'expected.raw',
                   output/'verification.json', '--eeprom', output/'verification-eeprom.bin',
                   '--phrase-samples', phrase_samples, '--loops', 3, '--playback', 'once',
                   '--minimum-sp', symbols['STACK_FLOOR'], '--wait-pc', symbols['wait_slot'],
                   '--actual-raw', output/'actual.raw']
        checked = run(command, ROOT, check=False)
        if (output/'verification.json').exists():
            verification = json.loads((output/'verification.json').read_text(encoding='utf-8'))
            report.update(verification=verification,
                          status='verified' if verification['pass'] else 'verification-failed',
                          verifiedLoops=verification['verifiedLoops'],
                          silenceSamplesVerified=verification['silenceSamplesVerified'])
        else:
            report.update(status='verification-failed', verificationError=(checked.stdout+checked.stderr).strip())
    (output/'build.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clip', default='vinni')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--avr-bin', type=Path)
    parser.add_argument('--node', default='node')
    parser.add_argument('--stream', type=Path,
                        help='Experimental HQ4 stream; preserve retained phrase duration and fit 1024-byte Flash')
    parser.add_argument('--samples', type=int,
                        help='New recording: expected complete phrase samples; requires --stream and a multiple of 64')
    parser.add_argument('--maximize-output', action='store_true', help='select a non-clipping power-of-two firmware gain')
    args = parser.parse_args()
    report = build(args.clip, args.output, args.avr_bin, args.node, args.stream, args.samples, args.maximize_output)
    print(json.dumps(report, indent=2))
    return 1 if report['status'] == 'verification-failed' or (args.stream is not None and report['status'] != 'verified') else 0


if __name__ == '__main__':
    raise SystemExit(main())
