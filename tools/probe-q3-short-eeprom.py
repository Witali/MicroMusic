"""Assemble and compare exact short-table EEPROM layouts including speech prefixes.

Research profiles inherit the qualified 368-byte ordinary floor Q3 core.
No source fitting, quantization, duration change or public-firmware replacement.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from hq4_core import pack_stream
from q3_pulsebook import validate, render
from q3_short_eeprom import split_storage, code_bytes, candidates, decode_book


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


compaction = module('qualified_q3_compaction', ROOT/'tools/probe-q3-core-compaction.py')
replace_once, sha = compaction.replace_once, compaction.sha
helpers = compaction.builder


def source_for(layout):
    frozen = (CODEC/'q3-pulsebook-compact/hq4-floor.S').read_text(encoding='utf-8')
    _, source, _, base_size = list(compaction.variants(frozen))[-1]
    assert base_size == 368
    width, packing = layout['width'], layout['packing']
    source = replace_once(source, ' cpi r18,16', f' cpi r18,{width}')
    old = (' mov r16,r14\n andi r16,48\n or r16,r18\n out 0x1e,r16\n'
           ' sbi 0x1c,0\n in r21,0x1d')
    shifts = {4:2, 8:1, 16:0}[width]
    address = ' mov r16,r14\n andi r16,48\n'
    if packing == 'nibble':
        address += ' lsr r16\n'*(shifts+1)+' lsr r18\n'
    else:
        address += ' lsr r16\n'*shifts
    address += ('pulse_address_ready:\n or r16,r18\n out 0x1e,r16\n'
                ' sbi 0x1c,0\n in r21,0x1d')
    if packing == 'nibble':
        address += ('\n /* Signed nibble -> signed tap*8; C still holds lag parity. */\n'
                    ' brcs pulse_high_nibble\n swap r21\npulse_high_nibble:\n'
                    ' andi r21,240\n asr r21')
    source = replace_once(source, old, address)
    source = replace_once(source, '.set VOICE_ADDR,0x188', '.set VOICE_ADDR,voice_data')
    source = replace_once(source, '.org VOICE_ADDR\nvoice_data:', 'voice_data:')
    source = replace_once(source, '.incbin "speech.hq"', '.incbin "flash-suffix.hq"')
    if layout['prefix_bytes']:
        if source.count(' lpm r16,Z+') != 5:
            raise ValueError('Frozen stream-reader sites changed')
        source = source.replace(' lpm r16,Z+', ' rcall read_byte')
        source = replace_once(source, ' ldi r30,lo8(VOICE_ADDR)\n ldi r31,hi8(VOICE_ADDR)',
            f' ldi r30,{layout["prefix_start"]}\n ldi r31,0')
        reader = f'''/* ZH=0 marks an EEPROM speech prefix; EOF always remains in Flash. */
read_byte:
 tst r31
 breq read_prefix
 lpm r16,Z+
 ret
read_prefix:
 out 0x1e,r30
 sbi 0x1c,0
 in r16,0x1d
prefix_advance:
 inc r30
 cpi r30,{layout['prefix_end']}
 brne read_byte_done
 ldi r30,lo8(VOICE_ADDR)
 ldi r31,hi8(VOICE_ADDR)
read_byte_done:
 ret
'''
        source = replace_once(source, '\nirq:', '\n'+reader+'\nirq:')
    return source


def build(payload, book, width, packing, prefix, output, avr_bin, node):
    payload = bytes(payload)
    frames, durations = helpers.helpers.validate_stream(payload)
    validate(frames, durations, book)
    layout = split_storage(book, payload, width, packing, prefix)
    np.testing.assert_array_equal(decode_book(layout['eeprom'][:layout['book_bytes']], width, packing), book)
    code = code_bytes(width, packing, layout['prefix_bytes'])
    expected_flash = (code+len(layout['flash_suffix'])+2) & ~1
    if expected_flash > 1024:
        raise ValueError('Complete core plus full speech stream exceeds 1024 Flash bytes')
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    for name in ('build.json', 'verification.json', 'actual.raw', 'firmware.elf', 'firmware.bin',
                 'firmware.hex', 'eeprom.hex'):
        (output/name).unlink(missing_ok=True)
    source = source_for(layout)
    (output/'firmware.S').write_text(source, encoding='utf-8', newline='\n')
    (output/'speech.hq').write_bytes(payload)
    (output/'flash-suffix.hq').write_bytes(layout['flash_suffix'])
    (output/'eeprom.bin').write_bytes(layout['eeprom'])
    (output/'eeprom.hex').write_text(helpers.intel_hex(layout['eeprom']), encoding='ascii', newline='\n')
    phrase, wraps = render(frames, durations, np.asarray(book, np.int8), tilt_shift=1, nearest=False)
    expected = np.r_[phrase, np.full(len(phrase)*2, 128, np.uint8)]
    (output/'expected.raw').write_bytes(expected.tobytes())
    suffix = '.exe' if os.name == 'nt' else ''
    executable = lambda name:Path(avr_bin)/(name+suffix)
    helpers.run([executable('avr-gcc'), '-mmcu=attiny13', '-nostdlib',
        '-Wl,--defsym=__TEXT_REGION_LENGTH__=1024', '-Wl,-Ttext=0', '-x', 'assembler',
        'firmware.S', '-o', 'firmware.elf'], output)
    symbols = helpers.parse_symbols(helpers.run([executable('avr-nm'), '-n', 'firmware.elf'], output).stdout)
    helpers.run([executable('avr-objcopy'), '-O', 'binary', 'firmware.elf', 'firmware.bin'], output)
    image = (output/'firmware.bin').read_bytes()
    assert symbols['code_end'] == symbols['voice_data'] == code
    assert len(image) == expected_flash
    assert image[code:code+len(layout['flash_suffix'])+1] == layout['flash_suffix']+b'\xff'
    (output/'firmware.hex').write_text(helpers.intel_hex(image), encoding='ascii', newline='\n')
    checked = helpers.run([node, ROOT/'tools/verify-tiny-speech.mjs', output/'firmware.bin',
        output/'expected.raw', output/'verification.json', '--eeprom', output/'eeprom.bin',
        '--phrase-samples', len(phrase), '--loops', 3, '--playback', 'once',
        '--minimum-sp', symbols['STACK_FLOOR'], '--wait-pc', symbols['wait_slot'],
        '--actual-raw', output/'actual.raw'], ROOT, check=False)
    verification = json.loads((output/'verification.json').read_text(encoding='utf-8'))
    report = dict(schema='q3-short-eeprom-build-v1', status='verified' if verification['pass'] else 'failed',
        width=width, packing=packing, code_bytes=code, flash_bytes=len(image), eeprom_image_bytes=64,
        waveform_bytes=layout['book_bytes'], speech_prefix_bytes=layout['prefix_bytes'],
        prefix_start=layout['prefix_start'], prefix_end=layout['prefix_end'],
        unused_eeprom_bytes=layout['free_eeprom_bytes'], flash_speech_bytes=len(layout['flash_suffix']),
        maximum_stream_bytes=1024-code-1+layout['prefix_bytes'],
        phrase_samples=len(phrase), intermediate_wraps=wraps.tolist(),
        phrase_pcm_sha256=sha(phrase.tobytes()), logical_stream_sha256=sha(payload),
        flash_suffix_sha256=sha(layout['flash_suffix']), eeprom_sha256=sha(layout['eeprom']),
        firmware_sha256=sha(image), asm_sha256_normalized_lf=sha(source.encode()),
        symbols=symbols, verification=verification)
    (output/'build.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
    if checked.returncode or not verification['pass']:
        raise RuntimeError('Generated short EEPROM profile failed: '+str(verification.get('error')))
    return report


def load_model(path):
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    if (value.get('schema') != 'hq4-q3-pulsebook-v1' or value.get('nearest') is not False
            or value.get('sample_rate') != 7500 or value.get('tilt_shift') != 1):
        raise ValueError('Only ordinary floor Q3 at 7500 Hz with T1 is supported')
    frames, durations, book = np.asarray(value['frames']), np.asarray(value['durations']), np.asarray(value['pulsebook'])
    payload = validate(frames, durations, book, samples=value['samples'])
    return payload, book.astype(np.int8)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--avr-bin', type=Path, required=True)
    p.add_argument('--node', type=Path, required=True)
    p.add_argument('--output', type=Path, default=ROOT/'build/q3-short-eeprom')
    p.add_argument('--retain', type=Path)
    args = p.parse_args()
    payload, book = load_model(args.model)
    results, skipped = [], []
    for candidate in candidates(book, payload):
        width, packing, prefix = candidate['width'], candidate['packing'], candidate['prefix_bytes']
        name = f'{width}-{packing}-prefix-{prefix}'
        if candidate['flash_bytes'] > 1024:
            skipped.append(dict(name=name, reason='complete Flash budget', flash_bytes=candidate['flash_bytes']))
            continue
        report = build(payload, book, width, packing, prefix, args.output/name, args.avr_bin, args.node)
        if results:
            assert report['phrase_pcm_sha256'] == results[0]['phrase_pcm_sha256']
        results.append(dict(name=name, **report))
        print(json.dumps(dict(name=name, code=report['code_bytes'], flash=report['flash_bytes'],
            wave_bytes=report['waveform_bytes'], speech_prefix=report['speech_prefix_bytes'],
            slack=report['verification']['foregroundTiming']['minimumSlackCycles'])), flush=True)
    if not results:
        raise ValueError('No exact short-table profile fits the complete recording')
    best = min(results, key=lambda result:(result['flash_bytes'], result['code_bytes']))
    report = dict(schema='q3-short-eeprom-study-v1', model=str(args.model),
        model_sha256_normalized_lf=sha(args.model.read_text(encoding='utf-8').encode()),
        source_sha256_normalized_lf={str(path):sha((ROOT/path).read_text(encoding='utf-8').encode())
            for path in ('tools/probe-q3-short-eeprom.py', 'tools/probe-q3-core-compaction.py',
                         'ATtiny13A/Sound/codec/q3_short_eeprom.py', 'ATtiny13A/Sound/codec/q3_pulsebook.py',
                         'ATtiny13A/Sound/codec/hq4_core.py',
                         'ATtiny13A/Sound/codec/q3-pulsebook-compact/hq4-floor.S',
                         'tools/verify-tiny-speech.mjs', 'tools/lib/tiny-work-profile.mjs')},
        selected=best['name'], results=results, skipped=skipped, hardware_tested=False,
        scope='Lossless storage experiment; public firmware unchanged; use paired Flash and EEPROM images')
    text = json.dumps(report, indent=2)+'\n'
    (args.output/'report.json').write_text(text, encoding='utf-8', newline='\n')
    if args.retain:
        args.retain.parent.mkdir(parents=True, exist_ok=True)
        args.retain.write_text(text, encoding='utf-8', newline='\n')
    print(json.dumps(dict(selected=best['name'], flash_bytes=best['flash_bytes'],
        code_bytes=best['code_bytes'], maximum_stream_bytes=best['maximum_stream_bytes'])))


if __name__ == '__main__':
    main()
