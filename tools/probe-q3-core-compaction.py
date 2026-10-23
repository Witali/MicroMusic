"""Measure isolated, PCM-preserving compactions of the ordinary floor Q3 core.

This is a reproducible research probe, not a replacement production builder.
The final variant changes physical EEPROM encoding; program its paired image.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from hq4_core import pack_stream


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


builder = module('frozen_compact_builder', ROOT/'tools/build-q3-pulsebook-compact.py')
fixtures = module('frozen_compact_fixtures', ROOT/'tools/test-q3-pulsebook-compact-avr.py')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Frozen source changed; review transformation: '+repr(old))
    return source.replace(old, new, 1)


def variants(source):
    yield 'baseline', source, False, 392
    if re.search(r'\br(?:12|14)\b', source):
        raise ValueError('Proposed reserved registers are already live')
    source = re.sub(r'\br22\b', 'r14', source)  # Frame mode can live in a low register.
    source = re.sub(r'\br9\b', 'r22', source)  # IRQ countdown gets its own high register.
    source = replace_once(source, ' ldi r19,5\n mov r22,r19', ' ldi r22,5')
    source = replace_once(source, ' push r16\n in r16,SREG\n push r16', ' in r12,SREG')
    source = replace_once(source, ' ldi r16,5\n mov r22,r16', ' ldi r22,5')
    source = replace_once(source, ' pop r16\n out SREG,r16\n pop r16', ' out SREG,r12')
    yield 'reserved-irq-registers', source, False, 380
    source = replace_once(source, 'vbr_read_coeffs:\n clr r29', 'vbr_read_coeffs:')
    yield 'invariant-pointer-high-byte', source, False, 378
    source = replace_once(source, '__vectors:\n rjmp reset', '__vectors:\n cli\n clt\n rjmp reset')
    source = replace_once(source, 'reset:\n cli\n clt', 'reset:')
    yield 'reset-vector-space', source, False, 374
    source = replace_once(source, ' in r23,0x1d', ' in r21,0x1d')
    source = replace_once(source,
        ' /* gain<<3 <=120, so signed NEG and Q3 product are exact gain*table. */\n'
        ' mov r21,r3\n lsl r21\n lsl r21\n lsl r21',
        ' /* EEPROM stores tap*8; gain is the nonnegative loop coefficient. */\n mov r23,r3')
    yield 'scaled-eeprom', source, True, 368


def run(command, cwd):
    result = subprocess.run(list(map(str, command)), cwd=cwd, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    return result


def qualify(source, scaled, code, payload, table, output, avr, node):
    output.mkdir(parents=True, exist_ok=True)
    # Preserve byte addresses while allowing each shorter body to place data immediately after code.
    source = replace_once(source, '.set VOICE_ADDR,0x188', '.set VOICE_ADDR,voice_data')
    source = replace_once(source, '.org VOICE_ADDR\nvoice_data:', 'voice_data:')
    (output/'firmware.S').write_text(source, encoding='utf-8', newline='\n')
    (output/'speech.hq').write_bytes(payload)
    table_path = output/'logical-table.json'
    table_path.write_text(json.dumps(table.tolist()), encoding='utf-8')
    if not 1 <= len(payload) <= 1024-code-1:
        raise ValueError('Complete stream exceeds the measured code/data budget')
    frames, durations = builder.helpers.validate_stream(payload)
    if np.any((frames[:, 2:] & 15) == 0) or np.any((frames[:, 2:] >> 4) == 0):
        raise ValueError('Ordinary Q3 excludes coefficient nibble zero')
    phrase, wraps = builder.regular_render(frames, durations, table, tilt_shift=1, nearest=False)
    eeprom = (table.astype(np.int16)*(8 if scaled else 1)).astype(np.int8).tobytes()
    (output/'eeprom.bin').write_bytes(eeprom)
    expected = np.r_[phrase, np.full(len(phrase)*2, 128, np.uint8)]
    (output/'expected.raw').write_bytes(expected.tobytes())
    run([avr/'avr-gcc', '-mmcu=attiny13', '-nostdlib',
         '-Wl,--defsym=__TEXT_REGION_LENGTH__=1024', '-Wl,-Ttext=0', '-x', 'assembler',
         'firmware.S', '-o', 'firmware.elf'], output)
    symbols = builder.parse_symbols(run([avr/'avr-nm', '-n', 'firmware.elf'], output).stdout)
    run([avr/'avr-objcopy', '-O', 'binary', 'firmware.elf', 'firmware.bin'], output)
    image = (output/'firmware.bin').read_bytes()
    assert symbols['code_end'] == symbols['voice_data'] == code
    assert len(image) == (code+len(payload)+2) & ~1
    assert image[code:code+len(payload)+1] == payload+b'\xff'
    assert len(image) <= 1024 and len(eeprom) == 64
    run([node, ROOT/'tools/verify-tiny-speech.mjs', output/'firmware.bin', output/'expected.raw',
         output/'verification.json', '--eeprom', output/'eeprom.bin', '--phrase-samples', len(phrase),
         '--loops', 3, '--playback', 'once', '--minimum-sp', symbols['STACK_FLOOR'],
         '--wait-pc', symbols['wait_slot'], '--actual-raw', output/'actual.raw'], ROOT)
    verification = json.loads((output/'verification.json').read_text())
    assert verification['pass'] and verification['mismatches'] == 0
    assert verification['missedSamples'] == verification['lostOverflows'] == 0
    report = dict(code_bytes=code, flash_bytes=len(image), eeprom_bytes=64,
        eeprom_encoding='signed tap*8' if scaled else 'signed tap',
        phrase_samples=len(phrase), pcm_sha256=sha(phrase.tobytes()), stream_sha256=sha(payload),
        image_sha256=sha(image), eeprom_sha256=sha(eeprom),
        asm_sha256_normalized_lf=sha(source.encode()), intermediate_wraps=wraps.tolist(),
        symbols=symbols, verification=verification)
    (output/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    return report


def check_excitation(output, report, node):
    script = '''import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {AVRCore as Reference} from REFERENCE;
import {AVRCore as Wasm} from WASM;
const image=readFileSync(IMAGE),ee=readFileSync(EEPROM),entry=ENTRY,end=END,irq=IRQ;
let checked=0;
for(const cpu of [new Reference(image,ee),new Wasm(image,ee),new Wasm(image,ee,{fastIdle:false,fastBlocks:false})])
 for(let tap=0;tap<64;tap++)for(let gain=0;gain<16;gain++)for(const flags of [0,0x35,0xff]){
  cpu.pc=entry/2;cpu.sp=0x9f;cpu.sreg=flags;cpu.r[3]=gain;cpu.r[14]=(tap>>4)<<4;
  cpu.r[18]=tap&15;cpu.r[22]=5;cpu.r[27]=0;
  let steps=0;while(cpu.pc!==end/2&&steps++<200)cpu.step();
  assert.equal(cpu.pc,end/2);assert.equal(cpu.r[18],((tap%15)-7)*gain&255);
  assert.equal(cpu.r[22],5);assert.equal(cpu.sreg&64,flags&64);assert.equal(cpu.sp,0x9f);checked++;
 }
assert.equal(checked,9216);
let irqCases=0;
for(const cpu of [new Reference(image,ee),new Wasm(image,ee),new Wasm(image,ee,{fastIdle:false,fastBlocks:false})])
 for(let flags=0;flags<128;flags++)for(const countdown of [1,5])for(const ready of [0,1]){
  const before=Array.from({length:32},(_,i)=>(i*37+flags*13)&255);
  before[22]=countdown;before[8]=ready;cpu.r.set(before);cpu.pc=irq/2;cpu.sp=0x9f;
  cpu.sreg=flags;cpu.io[0x29]=19;cpu.pending=false;cpu.irqDelay=0;cpu.pushPC(511);
  let steps=0;while(cpu.pc!==511&&steps++<32)cpu.step();
  assert.equal(cpu.pc,511);assert.equal(cpu.sp,0x9f);assert.equal(cpu.sreg,flags|128);
  for(let i=0;i<32;i++)if(![8,12,22].includes(i))assert.equal(cpu.r[i],before[i],`IRQ clobbers r${i}`);
  assert.equal(cpu.r[8],countdown===1&&ready?0:ready);
  assert.equal(cpu.r[22],countdown===1?5:countdown-1);
  assert.equal(cpu.io[0x29],countdown===1&&ready?before[7]:19);irqCases++;
 }
assert.equal(irqCases,1536);console.log(JSON.stringify({checked,irq_cases:irqCases,pass:true}));
'''
    for key, value in (('REFERENCE', (ROOT/'web-player/lib/avr-reference.js').as_uri()),
                       ('WASM', (ROOT/'web-player/lib/avr-core.js').as_uri()),
                       ('IMAGE', str(output/'firmware.bin')), ('EEPROM', str(output/'eeprom.bin')),
                       ('ENTRY', report['symbols']['pulse_lookup']), ('END', report['symbols']['filter']),
                       ('IRQ', report['symbols']['irq'])):
        script = script.replace(key, json.dumps(value))
    (output/'excitation-check.mjs').write_text(script, encoding='utf-8', newline='\n')
    return json.loads(run([node, output/'excitation-check.mjs'], ROOT).stdout)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    inputs = p.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--model', type=Path, help='Retained ordinary floor Q3 model; no ignored inputs needed')
    inputs.add_argument('--stream', type=Path)
    p.add_argument('--table', type=Path, help='Logical signed tap table, required with --stream')
    p.add_argument('--avr-bin', type=Path, required=True)
    p.add_argument('--node', type=Path, required=True)
    p.add_argument('--output', type=Path, default=ROOT/'build/q3-core-compaction')
    p.add_argument('--retain', type=Path)
    args = p.parse_args()
    args.output = args.output.resolve()
    template = CODEC/'q3-pulsebook-compact/hq4-floor.S'
    source = template.read_text(encoding='utf-8')
    if args.model:
        if args.table:
            p.error('--table cannot override a retained model')
        value = json.loads(args.model.read_text(encoding='utf-8'))
        if (value.get('schema') != 'hq4-q3-pulsebook-v1' or value.get('nearest') is not False
                or value.get('sample_rate') != 7500 or value.get('tilt_shift') != 1):
            p.error('Only ordinary floor Q3 at 7500 Hz with T1 is supported')
        payload = pack_stream(np.asarray(value['frames']), np.asarray(value['durations']))
        if int(np.asarray(value['durations']).sum()) != value['samples']:
            p.error('Model duration does not preserve its declared full recording')
        table = builder.load_table(args.model)
    else:
        if not args.table:
            p.error('--stream requires --table')
        payload, table = args.stream.read_bytes(), builder.load_table(args.table)
    stages, records = list(variants(source)), []
    for name, asm, scaled, code in stages:
        report = qualify(asm, scaled, code, payload, table, args.output/name, args.avr_bin, args.node)
        if records:
            assert report['pcm_sha256'] == records[0]['pcm_sha256']
        records.append(dict(name=name, **report))
        print(json.dumps(dict(stage=name, code_bytes=code, flash_bytes=report['flash_bytes'],
            slack=report['verification']['foregroundTiming']['minimumSlackCycles'])), flush=True)
    name, asm, scaled, code = stages[-1]
    table = ((np.arange(64).reshape(4, 16)%15)-7).astype(np.int8)
    frames, durations = fixtures.mixed_fixture(False)
    mixed = qualify(asm, scaled, code, pack_stream(frames, durations), table,
        args.output/'mixed-parser', args.avr_bin, args.node)
    excitation = check_excitation(args.output/'mixed-parser', mixed, args.node)
    frames = np.array([[[0, 1, 4, 63, 64, 126][gain%6], mode*16+gain, 0x88, 0x88, 0x88, 0x88]
        for mode in range(4) for gain in range(16)], np.uint8)
    durations = np.full(len(frames), 64, np.uint16)
    gains = qualify(asm, scaled, code, pack_stream(frames, durations), table,
        args.output/'all-gains', args.avr_bin, args.node)
    capacity = 1024-code-1
    frames, durations = fixtures.maximum_fixture(capacity, False)
    maximum_payload = pack_stream(frames, durations)
    assert len(maximum_payload) == capacity
    maximum = qualify(asm, scaled, code, maximum_payload, np.zeros((4, 16), np.int8),
        args.output/'maximum', args.avr_bin, args.node)
    assert maximum['flash_bytes'] == 1024
    report = dict(schema='q3-core-compaction-probe-v1', hardware_tested=False,
        scope='Ordinary floor Q3 only; public firmware and production builder unchanged',
        source_sha256_normalized_lf=sha(source.encode()),
        probe_sha256_normalized_lf=sha(Path(__file__).read_text(encoding='utf-8').encode()),
        compiler=run([args.avr_bin/'avr-gcc', '--version'], ROOT).stdout.splitlines()[0],
        dependencies_sha256_normalized_lf={str(path):sha((ROOT/path).read_text(encoding='utf-8').encode())
            for path in ('tools/build-q3-pulsebook-compact.py', 'tools/test-q3-pulsebook-compact-avr.py',
                         'ATtiny13A/Sound/codec/hq4_core.py', 'ATtiny13A/Sound/codec/q3_pulsebook.py',
                         'tools/verify-tiny-speech.mjs', 'tools/lib/tiny-work-profile.mjs')},
        stages=records, mixed_parser=mixed, all_gains=gains, maximum=maximum,
        maximum_stream_bytes=capacity, excitation=excitation,
        warnings=['New EEPROM encoding must be paired with its firmware',
                  'Timing measured for retained inputs, not a universal stream bound',
                  'Mixed/all-gains inputs exercise arithmetic, not speech-quality acceptance'])
    data = json.dumps(report, indent=2)+'\n'
    (args.output/'report.json').write_text(data, encoding='utf-8')
    if args.retain:
        args.retain.parent.mkdir(parents=True, exist_ok=True)
        args.retain.write_text(data, encoding='utf-8', newline='\n')
    print(json.dumps(dict(pass_=True, saved_code_bytes=392-code,
        new_code_bytes=code, new_flash_bytes=records[-1]['flash_bytes'], excitation_cases=excitation['checked'])))


if __name__ == '__main__':
    main()
