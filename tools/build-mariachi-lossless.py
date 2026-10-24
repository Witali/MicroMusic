"""Fit the complete two-guitar excerpt, including every chord tone, on ATtiny13A.

The host compiles shared shapes to DDS steps and shares whole musical-event
phrases. No source notes are selected away. The independent AVR audit checks
every original chord and gate, physical PWM output, timing and memory bounds.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import argparse
import shutil

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'ATtiny13A/Music/reference/cancion-del-mariachi/source-events.json'


def module(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'tools'/file)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


def compile_score():
    p=module('poly_events','pack-musical-events.py')
    doc=json.loads(SOURCE.read_text(encoding='utf-8'))
    parts=p.extract(doc,58*480,121*480)
    assert len(parts)==2 and len(p.records(parts))==1027
    assert [max(len(g['pitches']) for g in part['groups']) for part in parts]==[2,6]
    assert all(g['velocity']==80 for part in parts for g in part['groups'])
    assert all(part['program']==24 and part['offVelocity']==64 for part in parts)
    unit=160
    shapes=[];bases=[];rules=[];streams=[];gap_values=[];stats=[]
    shape_notes=[];base_notes=[]
    for track,part in enumerate(parts):
        local_shapes=[];local_bases=[];symbols=[];end=0
        for g in part['groups']:
            assert g['on']%unit==g['off']%unit==0
            shape=tuple(g['pitches'])
            if shape not in local_shapes:local_shapes.append(shape)
            gap=(g['on']-end)//unit;gate=(g['off']-g['on'])//unit;end=g['off']
            assert 1<=gate<=15
            if gap not in gap_values:gap_values.append(gap)
            value=(local_shapes.index(shape),gap,gate)
            if value not in local_bases:local_bases.append(value)
            symbols.append(local_bases.index(value))
        encoded,local_rules,depth=p.grammar(symbols,len(local_bases))
        assert depth<=(2 if track==0 else 5)
        stats.append(dict(track=track,groups=len(symbols),notes=sum(len(g['pitches']) for g in part['groups']),
                          baseCount=len(local_bases),ruleCount=len(local_rules),depth=depth))
        shape_offsets=[]
        for shape in local_shapes:
            shape_offsets.append(len(shapes))
            padded=shape+(None,)*((2 if track==0 else 6)-len(shape))
            shape_notes.append(dict(offset=len(shapes),track=track,pitches=list(shape)))
            for pitch in padded:
                step=0 if pitch is None else round(440*2**((pitch-69)/12)*65536/18750)
                shapes.extend([step&255,step>>8])
        bases.extend((shape_offsets[shape],gap_values.index(gap)*16+gate) for shape,gap,gate in local_bases)
        base_notes.extend(dict(track=track,pitches=list(local_shapes[shape]),gap=gap,gate=gate)
                          for shape,gap,gate in local_bases)
        rules.append(local_rules);streams.append(encoded)
    assert len(gap_values)<=8
    base_count=len(bases)
    rule_maps=[];base_at=rule_at=0
    for track,st in enumerate(stats):
        rule_maps.append([base_at+i for i in range(st['baseCount'])]
                         +[base_count+rule_at+i for i in range(st['ruleCount'])])
        base_at+=st['baseCount'];rule_at+=st['ruleCount']
    combined_rules=[];combined_stream=[];stream_offsets=[]
    for track in range(2):
        remap=rule_maps[track];stream_offsets.append(len(combined_stream))
        combined_rules.extend((remap[a],remap[b]) for a,b in rules[track])
        combined_stream.extend(remap[code] for code in streams[track]);combined_stream.append(255)
    # Verify every reconstructed event, including original ordered chord pitches.
    decoded=[]
    for track in range(2):
        groups=[];at=stream_offsets[track];end=0
        while combined_stream[at]!=255:
            pending=[combined_stream[at]];at+=1
            while pending:
                code=pending.pop()
                if code>=base_count:
                    a,b=combined_rules[code-base_count];pending.extend([b,a]);continue
                n=base_notes[code];assert n['track']==track
                on=end+n['gap']*unit;end=on+n['gate']*unit
                groups.append(dict(on=on,off=end,pitches=n['pitches'],velocity=80))
        decoded.append({**parts[track],'groups':groups})
    assert p.records(decoded)==p.records(parts)
    normalized=json.dumps(p.records(parts),separators=(',',':')).encode()
    return dict(parts=parts,shapes=shapes,bases=bases,rules=combined_rules,stream=combined_stream,
                gaps=gap_values,streamOffsets=stream_offsets,stats=stats,shapeNotes=shape_notes,
                baseNotes=base_notes,baseCount=base_count,
                decodedNotesSha256=hashlib.sha256(normalized).hexdigest(),verifiedLossless=True,
                scoreBytes=len(shapes)+2*len(bases)+2*len(combined_rules)+len(combined_stream)+len(gap_values))


def ihex(data):
    lines=[]
    for address in range(0,len(data),16):
        block=data[address:address+16];r=bytes([len(block),address>>8,address&255,0])+bytes(block)
        lines.append(':'+r.hex().upper()+f'{(-sum(r))&255:02X}')
    return '\n'.join(lines+[':00000001FF'])+'\n'


def build(folder):
    codec=compile_score();base_count=codec['baseCount']
    folder.mkdir(parents=True,exist_ok=True)
    source='''.section .text,"ax",@progbits
.global vectors
vectors:
  rjmp reset
gain_finish:
  adc r17, r17
gain_return:
  ret
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
clear_voices:
  st Z+, r16
  cpi r30, 152
  brne clear_voices
  clr r0
  clr r1
  clr r2
  clr r3
  clr r4
  clr r5
  clr r8
  clr r9
  clr r10
  clr r11
  clr r12
  clr r13
  clr r14
  clr r15
  ldi r16, 1
  mov r1, r16
  mov r9, r16
  ldi r16, STREAM_SECOND
  mov r8, r16
  mov r23, r18
  ldi r28, 96
  rcall music_step
  ldi r30, 110
  clr r31
  sbi 23, 1
  out 41, r18
  ldi r16, 35
  out 47, r16
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
  inc r15
  brne render_sample
  mov r22, r30
  rcall music_tick
  mov r30, r22
  clr r31
render_sample:
  ldi r26, 112
  ldi r21, 240
voice_loop:
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
  ldi r16, 0
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
  in r17, 29
  brcc wave_nibble
  swap r17
wave_nibble:
  andi r17, 15
  add r21, r17
  cpi r26, 120
  brne rhythm_group
  mov r25, r4
  andi r25, 15
  rcall chord_gain
  mov r20, r17
  ldi r21, 208
rhythm_group:
  cpi r26, 144
  brne voice_loop
  mov r25, r5
  andi r25, 15
  rcall chord_gain
  add r17, r20
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
chord_gain:
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
  rjmp gain_finish
music_tick:
  inc r14
  mov r20, r4
  rcall envelope
  mov r4, r20
  mov r20, r5
  rcall envelope
  mov r5, r20
  mov r16, r1
  or r16, r9
  brne song_running
  mov r16, r4
  or r16, r5
  brne music_return
  tst r2
  brne pause_count
  ldi r16, 74
  mov r2, r16
pause_count:
  dec r2
  brne music_return
restart_song:
  clr r0
  ldi r16, 1
  mov r1, r16
  mov r9, r16
  ldi r16, STREAM_SECOND
  mov r8, r16
  clr r3
  clr r10
  clr r11
  clr r12
  clr r13
  rjmp music_step
song_running:
  ldi r16, 5
  add r12, r16
  ldi r16, 22
  adc r13, r16
  brcc music_return
music_step:
  movw r16, r0
  movw r24, r2
  mov r20, r4
  ldi r19, 0
  rcall part_tick
  movw r0, r16
  movw r2, r24
  mov r4, r20
  movw r16, r8
  movw r24, r10
  mov r20, r5
  ldi r19, 1
  rcall part_tick
  movw r8, r16
  movw r10, r24
  mov r5, r20
music_return:
  ret
envelope:
  mov r21, r20
  andi r21, 15
  breq envelope_return
  sbrs r20, 7
  rjmp envelope_decay
  ldi r25, 1
  cpi r21, 10
  brcc envelope_mask
  ldi r25, 3
  cpi r21, 7
  brcc envelope_mask
  ldi r25, 7
envelope_mask:
  and r25, r14
  brne envelope_return
envelope_decay:
  dec r20
envelope_return:
  ret
part_tick:
  tst r17
  breq part_return
  dec r17
  brne part_return
  sbrc r25, 7
  rjmp read_base
  andi r20, 127
next_symbol:
  tst r24
  breq read_stream
  dec r24
  mov r26, r24
  subi r26, 112
  sbrc r19, 0
  subi r26, 254
  ld r21, X+
  rjmp classify_symbol
read_stream:
  ldi r30, lo8(song_stream)
  ldi r31, hi8(song_stream)
  add r30, r16
  adc r31, r29
  lpm r21, Z
  inc r16
  cpi r21, 255
  breq part_return
classify_symbol:
  cpi r21, BASE_COUNT
  brcs symbol_base
  subi r21, BASE_COUNT
  lsl r21
  ldi r30, lo8(song_rules)
  ldi r31, hi8(song_rules)
  add r30, r21
  adc r31, r29
  lpm r6, Z+
  lpm r7, Z
  mov r26, r24
  subi r26, 112
  sbrc r19, 0
  subi r26, 254
  st X+, r7
  inc r24
  mov r21, r6
  rjmp classify_symbol
symbol_base:
  mov r25, r21
read_base:
  mov r21, r25
  andi r21, 127
  lsl r21
  ldi r30, lo8(song_bases)
  ldi r31, hi8(song_bases)
  add r30, r21
  adc r31, r29
  lpm r6, Z+
  lpm r7, Z
  sbrc r25, 7
  rjmp note_start
  mov r21, r7
  swap r21
  andi r21, 7
  ldi r30, lo8(song_gaps)
  ldi r31, hi8(song_gaps)
  add r30, r21
  adc r31, r29
  lpm r17, Z
  tst r17
  breq note_start
  ori r25, 128
part_return:
  ret
note_start:
  andi r25, 127
  mov r17, r7
  andi r17, 15
  ldi r20, 143
  ldi r30, lo8(song_shapes)
  ldi r31, hi8(song_shapes)
  add r30, r6
  adc r31, r29
  ldi r26, 112
  ldi r21, 2
  sbrc r19, 0
  ldi r26, 120
  sbrc r19, 0
  ldi r21, 6
load_chord:
  st X+, r29
  st X+, r29
  lpm r7, Z+
  st X+, r7
  lpm r7, Z+
  st X+, r7
  dec r21
  brne load_chord
chord_loaded:
  ret
'''
    source=f'.set BASE_COUNT, {base_count}\n.set STREAM_SECOND, {codec["streamOffsets"][1]}\n'+source
    for name,data in [('song_shapes',codec['shapes']),('song_bases',[b for pair in codec['bases'] for b in pair]),
                      ('song_rules',[b for pair in codec['rules'] for b in pair]),('song_gaps',codec['gaps']),('song_stream',codec['stream'])]:
        source+=name+':\n.byte '+','.join(map(str,data))+'\n'
    (folder/'synth.S').write_text(source,encoding='utf-8',newline='\n')
    assembler=module('poly_assembler','build-release-engine.py')
    rom,labels=assembler.assemble_relaxed(folder/'synth.S')
    assert len(rom)<=1024,f'Complete image exceeds ATtiny13A Flash: {len(rom)} bytes'
    (folder/'synth.bin').write_bytes(rom);(folder/'synth.hex').write_text(ihex(rom),encoding='ascii',newline='\n')
    bank=json.loads((ROOT/'ATtiny13A/Music/instruments/bank.json').read_text(encoding='utf-8'))
    profile=bank['instruments']['acoustic-guitar-nylon'];ep=bytearray(64)
    waves={}
    for index,register in enumerate(('low','high')):
        wave=profile['waves'][register][:]
        if register=='low':
            zero=wave.index(0);wave=wave[zero:]+wave[:zero]
        waves[register]=wave
        ep[index*8:index*8+8]=bytes((wave[n]+8)|((wave[n+1]+8)<<4) for n in range(0,16,2))
    assert waves['low'][0]==0,'A zero DDS step/phase contributes exact silence'
    (folder/'eeprom.bin').write_bytes(ep);(folder/'eeprom.hex').write_text(ihex(ep),encoding='ascii',newline='\n')
    report=dict(engine='mariachi-polyphonic',experimental=False,flashBytes=len(rom),codeBytes=labels['song_shapes'],
        tableBytes=len(rom)-labels['song_shapes'],eepromBytes=64,labels=labels,scoreBytes=codec['scoreBytes'],
        sourceSha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),flashSha256=hashlib.sha256(rom).hexdigest(),
        eepromSha256=hashlib.sha256(ep).hexdigest(),decodedNotesSha256=codec['decodedNotesSha256'],
        sourceNotes=1027,sourceParts=2,maximumSimultaneousSourceNotes=7,oscillators=8,
        cpuHz=9600000,pwmHz=37500,synthesisHz=18750,unitTicks=160,ppqn=480,tempoMicroseconds=476190,
        gridStep=5637,envelopeEverySamples=256,voiceAddresses=list(range(112,144,4)),
        pendingSymbolAddresses=[[144,145],[146,147,148,149,150]],waves=waves,
        sourceSelection=dict(firstBeat=58,lastBeat=121),verifiedLosslessScore=True)
    report['activePrimaryVoices']=8
    report['instrumentAssignments']={role:dict(instrument='acoustic-guitar-nylon',
        label='Акустическая гитара с нейлоновыми струнами',gmProgram=24,sourceVelocity=80,level=15)
        for role in ('leadGuitar','rhythmGuitar')}
    report['instrumentBankSha256']=hashlib.sha256((ROOT/'ATtiny13A/Music/instruments/bank.json').read_bytes()).hexdigest()
    report['articulation']='Shared plucked envelope for each common-gate source chord; phases reset on picking; no additional release slots.'
    (folder/'build-report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    (folder/'compiled-score.json').write_text(json.dumps(codec,indent=2)+'\n',encoding='utf-8',newline='\n')
    shutil.copyfile(ROOT/'ATtiny13A/Music/variants/rhythmic/avr_core.js',folder/'avr_core.js')
    shutil.copyfile(ROOT/'ATtiny13A/Music/instruments/FluidR3-MIT.txt',folder/'FluidR3-MIT.txt')
    html=(ROOT/'tools/player-template.html').read_text(encoding='utf-8')
    for key,value in [('AVR_CORE',(folder/'avr_core.js').read_text(encoding='utf-8')),
                      ('FIRMWARE_HEX',ihex(rom)),('EEPROM_HEX',ihex(ep))]:
        html=html.replace('/*'+key+'*/',value)
    html=html.replace('ATtiny13A: четырёхголосный плеер — эмулятор HEX','Canción del Mariachi · все 1027 нот')
    html=html.replace('ATtiny13A — проигрыватель AVR-прошивки','Canción del Mariachi · две гитары, все ноты')
    html=html.replace('мелодия, пианино, гитара и ударные.','две нейлоновые гитары, все 1027 исходных нот и 8 тональных генераторов.')
    html=html.replace('lp.frequency.value=4000','lp.frequency.value=9000')
    html=html.replace('Файл preview.wav должен находиться рядом с player.html (он есть в ZIP).',
                      'Файл preview.wav находится рядом с player.html.')
    (folder/'player.html').write_text(html,encoding='utf-8',newline='\n')
    print(json.dumps({k:report[k] for k in ('flashBytes','codeBytes','tableBytes','sourceNotes')}))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'build/mariachi-lossless')
    args=parser.parse_args();build(args.output)
