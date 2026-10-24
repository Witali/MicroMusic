"""Four independent sustained instruments with a bounded shared event grammar.

This engine retains every supplied Note On/Off. Commands select one of four
parts and a shared pitch; waits share a sixteenth grid. Re-Pair dictionaries
compress commands without changing their order or the musical arrangement.
"""
from pathlib import Path
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
import math
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / file)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def encode(parts, end_unit, depth=8):
    pitches = sorted({n['pitch'] for part in parts for n in part['notes']})
    assert len(parts) == 4
    pitch_bits = 5
    assert len(pitches) < 1 << pitch_bits
    timeline = defaultdict(list)
    for voice, part in enumerate(parts):
        previous = 0
        for note in part['notes']:
            assert previous <= note['on'] < note['off'] <= end_unit
            previous = note['off']
            timeline[note['on']].append((1, voice, (voice << pitch_bits) | (pitches.index(note['pitch']) + 1)))
            timeline[note['off']].append((0, voice, voice << pitch_bits))
    commands = []
    position = 0
    for unit, events in sorted(timeline.items()):
        remaining = unit - position
        while remaining:
            wait = min(remaining, 64)
            commands.append(127 + wait)
            remaining -= wait
        commands.extend(event[2] for event in sorted(events))
        position = unit
    remaining = end_unit + 1 - position
    while remaining:
        wait = min(remaining, 64)
        commands.append(127 + wait)
        remaining -= wait
    stream, rules, depths = list(commands), [], [0]*192
    while len(rules)<63:
        candidates=[]
        for pair, approximate in Counter(zip(stream,stream[1:])).items():
            d=1+max(depths[pair[0]],depths[pair[1]])
            if approximate<3 or d>depth:continue
            count=at=0
            while at+1<len(stream):
                if tuple(stream[at:at+2])==pair:count+=1;at+=2
                else:at+=1
            if count>2:candidates.append((2-count,pair,d))
        if not candidates:break
        _,pair,d=min(candidates);out=[];at=0;code=192+len(rules)
        while at<len(stream):
            if tuple(stream[at:at+2])==pair:out.append(code);at+=2
            else:out.append(stream[at]);at+=1
        rules.append(pair);depths.append(d);stream=out
    maximum=max(depths)
    assert len(rules) <= 63 and maximum <= depth
    decoded = []
    for code in stream:
        pending = [code]
        while pending:
            symbol = pending.pop()
            if symbol < 192:
                decoded.append(symbol)
            else:
                a, b = rules[symbol - 192]
                pending.extend((b, a))
    assert decoded == commands
    return dict(parts=parts, pitches=pitches, pitchBits=pitch_bits, commands=commands, stream=stream + [255],
                rules=rules, maximumDepth=maximum, pendingBytes=depth,
                endUnit=end_unit, playbackUnits=end_unit + 1,
                noteCounts=[len(part['notes']) for part in parts],
                decodedCommandsSha256=hashlib.sha256(bytes(commands)).hexdigest(),
                verifiedLossless=True)


SOURCE = r'''.section .text,"ax",@progbits
.global vectors
vectors:
  rjmp reset
  nop
  nop
  rjmp pwm_irq
reset:
  clr r27
  clr r29
  clr r31
  ldi r30, 96
  ldi r18, 128
fill_ring:
  st Z+, r18
  cpi r30, 112
  brne fill_ring
  clr r16
clear_states:
  st Z+, r16
  cpi r30, 140
  brne clear_states
  clr r4
  clr r5
  clr r8
  clr r9
  clr r10
  ldi r16, lo8(song_stream)
  mov r2, r16
  ldi r16, hi8(song_stream)
  mov r3, r16
  mov r23, r18
  ldi r28, 96
  rcall read_events
  ldi r30, 110
  clr r31
  out 41, r18
  ldi r16, 35
  out 47, r16
  sbi 23, 1
  ldi r16, 1
  out 51, r16
  ldi r16, 2
  out 57, r16
  sei
idle:
  mov r16, r30
  sub r16, r28
  andi r16, 15
  cpi r16, 13
  brcc idle
audio_step:
  inc r10
  brne render_sample
  mov r14, r30
  rcall music_tick
  mov r30, r14
  clr r31
render_sample:
  ldi r26, 112
  clr r19
  clr r22
voice_loop:
  ld r20, X+
  ld r16, X+
  ld r17, X+
  ld r6, X+
  ld r7, X+
  add r16, r6
  adc r17, r7
  subi r26, 4
  st X+, r16
  st X+, r17
  subi r26, 254
  mov r16, r19
  mov r25, r7
  cpi r25, 4
  brcs wave_register
  ori r16, 8
wave_register:
  swap r17
  andi r17, 15
  lsr r17
  or r16, r17
  out 30, r16
  sbi 28, 0
  in r21, 29
  brcc wave_nibble
  swap r21
wave_nibble:
  andi r21, 15
  subi r21, 8
  mov r25, r20
  andi r25, 15
  rcall voice_gain
  add r22, r17
  subi r19, 240
  cpi r26, 132
  brne voice_loop
master_gain:
  lsl r22
  lsl r22
  mov r17, r22
write_pwm:
  subi r17, 128
  add r23, r17
  ror r23
  st Z+, r23
  st Z+, r17
  andi r30, 111
  mov r23, r17
ring_published:
  rjmp idle
pwm_irq:
  out 41, r18
ring_read:
  ld r18, Y+
  sbrc r28, 4
  ldi r28, 96
  reti
voice_gain:
  clr r17
  ldi r24, 4
  lsr r25
gain_loop:
  brcc gain_no_add
  add r17, r21
gain_no_add:
  asr r17
  ror r25
  dec r24
  brne gain_loop
  lsl r25
  adc r17, r17
  ret
music_tick:
  ldi r26, 112
  ldi r30, lo8(part_levels)
  ldi r31, hi8(part_levels)
envelope_loop:
  ld r20, X+
  mov r21, r20
  andi r21, 15
  lpm r16, Z+
  sbrs r20, 7
  rjmp release_voice
  mov r25, r21
  sub r25, r16
  brcc store_envelope
  inc r20
  rjmp store_envelope
release_voice:
  tst r21
  breq store_envelope
  dec r20
store_envelope:
  subi r26, 1
  st X+, r20
  subi r26, 252
  cpi r26, 132
  brne envelope_loop
  ldi r16, GRID_LOW
  add r8, r16
  ldi r16, GRID_HIGH
  adc r9, r16
  brcc music_return
  dec r4
  brne music_return
read_events:
next_symbol:
  tst r5
  breq read_stream
  dec r5
  mov r26, r5
  subi r26, 124
  ld r21, X+
  rjmp classify_symbol
read_stream:
  movw r30, r2
  lpm r21, Z+
  movw r2, r30
  cpi r21, 255
  brne classify_symbol
restart_song:
  ldi r16, lo8(song_stream)
  mov r2, r16
  ldi r16, hi8(song_stream)
  mov r3, r16
  rjmp read_stream
classify_symbol:
  cpi r21, 192
  brcs event_leaf
  subi r21, 192
  lsl r21
  ldi r30, lo8(song_rules)
  ldi r31, hi8(song_rules)
  add r30, r21
  adc r31, r29
  lpm r6, Z+
  lpm r7, Z
  mov r26, r5
  subi r26, 124
  st X+, r7
  inc r5
  mov r21, r6
  rjmp classify_symbol
event_leaf:
  cpi r21, 128
  brcs note_event
  subi r21, 127
  mov r4, r21
music_return:
  ret
note_event:
  mov r16, r21
  lsr r16
  lsr r16
  lsr r16
  lsr r16
  lsr r16
  mov r26, r16
  lsl r26
  lsl r26
  add r26, r16
  subi r26, 144
  andi r21, 31
  brne note_on
note_off:
  ld r20, X+
  andi r20, 127
  subi r26, 1
  st X+, r20
note_released:
  rjmp next_symbol
note_on:
  ldi r20, 129
  st X+, r20
  subi r26, 254
  dec r21
  lsl r21
  ldi r30, lo8(pitch_steps)
  ldi r31, hi8(pitch_steps)
  add r30, r21
  adc r31, r29
  lpm r6, Z+
  lpm r7, Z
  st X+, r6
  st X+, r7
note_committed:
  rjmp next_symbol
'''


def build(folder, score, normalization=None):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    codec = encode(score['parts'], score['endUnit'])
    grid = round(score['tempo_bpm'] * 4 / 60 / (18750 / 256) * 65536)
    source = f'.set GRID_LOW, {grid & 255}\n.set GRID_HIGH, {grid >> 8}\n' + SOURCE
    voice_count = len(score['parts'])
    voice_end = 112 + 5*voice_count
    source = source.replace('cpi r30, 140',f'cpi r30, {voice_end+8}')
    source = source.replace('cpi r26, 132',f'cpi r26, {voice_end}')
    source = source.replace('subi r26, 124',f'subi r26, {256-voice_end}')
    source = source.replace('andi r21, 31',f'andi r21, {(1<<codec["pitchBits"])-1}')
    source=source.replace('master_gain:\n  lsl r22\n  lsl r22\n  mov r17, r22\nwrite_pwm:\n  subi r17, 128',
        '''master_gain:
  mov r12, r30
  ldi r30, lo8(output_gain)
  ldi r31, hi8(output_gain)
  subi r22, GAIN_MINIMUM
  add r30, r22
  adc r31, r29
  lpm r17, Z
  mov r30, r12
  clr r31
write_pwm:''' if normalization else 'master_gain:\n  mov r17, r22\nwrite_pwm:\n  subi r17, 128')
    if normalization:source=f'.set GAIN_MINIMUM, {normalization["minimum"]&255}\n'+source
    data = [('part_levels', [part['level'] for part in score['parts']]),
            ('pitch_steps', [b for pitch in codec['pitches'] for b in
                             (round(440 * 2 ** ((pitch - 69) / 12) * 65536 / 18750) & 255,
                              round(440 * 2 ** ((pitch - 69) / 12) * 65536 / 18750) >> 8)]),
            ('song_rules', [b for pair in codec['rules'] for b in pair]), ('song_stream', codec['stream'])]
    if normalization:data.append(('output_gain',normalization['table']))
    for label, values in data:
        source += label + ':\n.byte ' + ','.join(map(str, values)) + '\n'
    (folder / 'synth.S').write_text(source, encoding='utf-8', newline='\n')
    assembler = module('four_assembler', 'build-release-engine.py')
    rom, labels = assembler.assemble_relaxed(folder / 'synth.S')
    assert len(rom) <= 1024, len(rom)
    bank = module('four_bank', 'instrument-bank.py')
    profiles = bank.load_bank()
    ep = b''.join(bank.pack_wave(profiles['instruments'][part['instrument']]['waves'][register])
                  for part in score['parts'] for register in ('low', 'high'))
    ep += bytes([0x88])*(64-len(ep))
    assert len(ep) == 64
    hexer = module('four_hex', 'build-mariachi-lossless.py').ihex
    for name, binary in [('synth', rom), ('eeprom', ep)]:
        (folder / (name + '.bin')).write_bytes(binary)
        (folder / (name + '.hex')).write_text(hexer(binary), encoding='ascii', newline='\n')
    report = dict(engine=score['engine'], flashBytes=len(rom), codeBytes=labels['part_levels'],
                  tableBytes=len(rom)-labels['part_levels'], eepromBytes=64, labels=labels,
                  flashSha256=hashlib.sha256(rom).hexdigest(), eepromSha256=hashlib.sha256(ep).hexdigest(),
                  instrumentBankSha256=hashlib.sha256(bank.BANK_PATH.read_bytes()).hexdigest(),
                  instrumentAssignments={part['name']:dict(instrument=part['instrument'], gmProgram=profiles['instruments'][part['instrument']]['gmProgram'],
                      level=part['level'], eepromOffset=index*16) for index, part in enumerate(score['parts'])},
                  score=dict(noteCounts=codec['noteCounts'], sourceNotes=sum(codec['noteCounts']),
                      endUnit=score['endUnit'], playbackUnits=codec['playbackUnits'],
                      maximumGrammarDepth=codec['maximumDepth'], pendingBytes=codec['pendingBytes'],
                      commandBytes=len(codec['commands']), streamBytes=len(codec['stream']), ruleBytes=2*len(codec['rules']),
                      verifiedLossless=True, decodedCommandsSha256=codec['decodedCommandsSha256']),
                  timing=dict(tempoBpm=score['tempo_bpm'], phaseStep=grid, phaseBits=16,
                      actualTempoBpm=grid/65536*(18750/256)*60/4, envelopeTickCycles=131072),
                  voices=dict(primaryVoices=voice_count, voiceAddresses=list(range(112,voice_end,5)), voiceStateBytes=5*voice_count,
                      pwmRingBytes=16, pendingAddress=voice_end, pendingBytes=8, isrCycles=15,
                      envelope='Independent linear attack/release; phase continuous; no voice stealing'),
                  outputNormalization=({**normalization,'implementation':'linear-flash-table','midpoint':128}
                                       if normalization else dict(gain=1,implementation='none',midpoint=128)))
    for name, obj in [('score.json',score),('compiled-score.json',codec),('build-report.json',report)]:
        (folder/name).write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n',encoding='utf-8',newline='\n')
    (folder/'avr_core.js').write_text((ROOT/'web-player/lib/hex.js').read_text(encoding='utf-8').replace('export function parseHex','function parseHex')+'\n'+(ROOT/'web-player/lib/avr-reference.js').read_text(encoding='utf-8').replace('export class AVRCore','class AVRCore')+'\nAVRCore.fromHex=(flash,eeprom)=>new AVRCore(parseHex(flash),eeprom?parseHex(eeprom,64):null);\nif(typeof module!==\"undefined\")module.exports={AVRCore};\n',encoding='utf-8',newline='\n')
    shutil.copyfile(ROOT/'ATtiny13A/Music/instruments/FluidR3-MIT.txt',folder/'FluidR3-MIT.txt')
    html=(ROOT/'tools/player-template.html').read_text(encoding='utf-8')
    for key, value in [('AVR_CORE',(folder/'avr_core.js').read_text(encoding='utf-8')),
                       ('FIRMWARE_HEX',hexer(rom)),('EEPROM_HEX',hexer(ep))]:
        html=html.replace('/*'+key+'*/',value)
    html=html.replace('ATtiny13A — проигрыватель AVR-прошивки',score['title'])
    html=html.replace('мелодия, пианино, гитара и ударные.',score['description'])
    (folder/'player.html').write_text(html,encoding='utf-8',newline='\n')
    print(json.dumps({key:report[key] for key in ('flashBytes','codeBytes','tableBytes')},ensure_ascii=False))
    return report


def build_normalized(folder, score):
    baseline=ROOT/'build'/('level-calibration-'+Path(folder).name)
    result=build(baseline,score)
    seconds=(score['endUnit']+1)/4*60/score['tempo_bpm']+.5
    raw=subprocess.run(['node',str(ROOT/'tools/calibrate-firmware-level.mjs'),str(baseline),str(seconds)],
                       check=True,capture_output=True,text=True)
    normalization=json.loads(raw.stdout)
    assert normalization['calibrationFlashSha256']==result['flashSha256']
    bank=module('four_bounds_bank','instrument-bank.py').load_bank()
    bounds=[]
    for part in score['parts']:
        profile=bank['instruments'][part['instrument']]
        waves=profile['waves']['low']+profile['waves']['high']
        bounds.append((math.floor(min(waves)*part['level']/8),math.floor(max(waves)*part['level']/8)))
    minimum=sum(min(0,pair[0]) for pair in bounds)
    maximum=sum(max(0,pair[1]) for pair in bounds)
    assert minimum<=normalization['minimum']<=0<=normalization['maximum']<=maximum
    normalization['observedMinimum']=normalization['minimum']
    normalization['observedMaximum']=normalization['maximum']
    normalization['minimum']=minimum;normalization['maximum']=maximum
    gain=min(128/-minimum,127/maximum)
    normalization['gain']=gain;normalization['gainDb']=20*math.log10(gain)
    normalization['table']=[math.floor(128+x*gain+.5) for x in range(minimum,maximum+1)]
    normalization['domain']='Sum of every instrument low/high-wave extremum at its maximum envelope level, with the exact signed floor division used by AVR. Covers every phase alignment and every playback loop.'
    normalization['instrumentMixBounds']=bounds
    return build(folder,score,normalization)
