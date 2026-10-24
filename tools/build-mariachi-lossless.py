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
import subprocess

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
    return compile_parts(parts)


def compile_parts(parts,*,compact=False,unit=160,voices=(2,6),pending=(2,5),percussion=False):
    """Encode supplied parts exactly; arrangement policy belongs to the caller."""
    p=module('poly_events','pack-musical-events.py')
    assert len(parts)==2
    assert sum(voices)==(6 if percussion else 8) and sum(pending)==7
    assert not percussion or (compact and voices==(3,3) and pending==(4,3) and unit==80)
    assert all(1<=len(g['pitches'])<=voices[i] for i,part in enumerate(parts) for g in part['groups'])
    assert all(g['velocity']==80 for part in parts for g in part['groups'])
    assert all(part['program']==24 and part['offVelocity']==64 for part in parts)
    shapes=[];bases=[];rules=[];streams=[];gap_values=[];gate_values=[];stats=[]
    shape_notes=[];base_notes=[]
    palette=sorted({pitch for part in parts for g in part['groups'] for pitch in g['pitches']}) if percussion else []
    assert len(palette)<=16
    for track,part in enumerate(parts):
        local_shapes=[];local_bases=[];symbols=[];end=0
        for g in part['groups']:
            assert g['on']%unit==g['off']%unit==0
            shape=tuple(g['pitches'])
            if shape not in local_shapes:local_shapes.append(shape)
            gap=(g['on']-end)//unit;gate=(g['off']-g['on'])//unit;end=g['off']
            assert 1<=gate<=255 and (compact or gate<=15)
            if gate not in gate_values:gate_values.append(gate)
            if gap not in gap_values:gap_values.append(gap)
            value=(local_shapes.index(shape),gap,gate)
            if value not in local_bases:local_bases.append(value)
            symbols.append(local_bases.index(value))
        if compact:p.MAX_DEPTH=pending[track]
        encoded,local_rules,depth=p.grammar(symbols,len(local_bases))
        assert depth<=pending[track]
        stats.append(dict(track=track,groups=len(symbols),notes=sum(len(g['pitches']) for g in part['groups']),
                          baseCount=len(local_bases),ruleCount=len(local_rules),depth=depth))
        shape_offsets=[]
        for shape in local_shapes:
            shape_offsets.append(len(shapes))
            padded=shape if compact else shape+(None,)*(voices[track]-len(shape))
            shape_notes.append(dict(offset=len(shapes),track=track,pitches=list(shape)))
            if compact and not percussion:shapes.append(len(shape))
            for index,pitch in enumerate(padded):
                step=0 if pitch is None else round(440*2**((pitch-69)/12)*65536/18750)
                if percussion:shapes.append(32+2*palette.index(pitch)+(128 if index==len(shape)-1 else 0))
                else:shapes.extend([step&255,step>>8])
        bases.extend((shape_offsets[shape],gap//2*8+gate_values.index(gate) if percussion else gap_values.index(gap)*16+(gate_values.index(gate) if compact else gate)) for shape,gap,gate in local_bases)
        base_notes.extend(dict(track=track,pitches=list(local_shapes[shape]),gap=gap,gate=gate)
                          for shape,gap,gate in local_bases)
        rules.append(local_rules);streams.append(encoded)
    assert len(gap_values)<=8 and max(gap_values)<=255
    assert not compact or len(gate_values)<=16
    assert not percussion or (len(gate_values)<=8 and all(gap%2==0 and 0<=gap<=62 for gap in gap_values))
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
            to_expand=[combined_stream[at]];at+=1
            while to_expand:
                code=to_expand.pop()
                if code>=base_count:
                    a,b=combined_rules[code-base_count];to_expand.extend([b,a]);continue
                n=base_notes[code];assert n['track']==track
                on=end+n['gap']*unit;end=on+n['gate']*unit
                groups.append(dict(on=on,off=end,pitches=n['pitches'],velocity=80))
        decoded.append({**parts[track],'groups':groups})
    assert p.records(decoded)==p.records(parts)
    normalized=json.dumps(p.records(parts),separators=(',',':')).encode()
    result=dict(parts=parts,shapes=shapes,bases=bases,rules=combined_rules,stream=combined_stream,
                gaps=gap_values,streamOffsets=stream_offsets,stats=stats,shapeNotes=shape_notes,
                baseNotes=base_notes,baseCount=base_count,
                decodedNotesSha256=hashlib.sha256(normalized).hexdigest(),verifiedLossless=True,
                scoreBytes=len(shapes)+2*len(bases)+2*len(combined_rules)+len(combined_stream)+len(gap_values))
    assert len(shapes)<=256 and len(bases)<128 and len(combined_stream)<=256
    if compact:
        result['gates']=gate_values
        result['formatOptions']=dict(compactShapes=True,unitTicks=unit,voices=list(voices),pending=list(pending))
        result['scoreBytes']+=len(gate_values)
    if percussion:
        result['formatOptions'].update(percussion=True,pitchEeprom=True,rawGaps=True)
        result['pitchPalette']=palette
        result['pitchSteps']=[round(440*2**((pitch-69)/12)*65536/18750) for pitch in palette]
        result['scoreBytes']-=len(gap_values)
    return result


def ihex(data):
    lines=[]
    for address in range(0,len(data),16):
        block=data[address:address+16];r=bytes([len(block),address>>8,address&255,0])+bytes(block)
        lines.append(':'+r.hex().upper()+f'{(-sum(r))&255:02X}')
    return '\n'.join(lines+[':00000001FF'])+'\n'


def build(folder,codec=None,arrangement=None,normalization=None):
    codec=compile_score() if codec is None else codec
    base_count=codec['baseCount']
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
  cpi r26, 121
  brcs guitar_bank
  ldi r16, 16
guitar_bank:
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
  asr r17
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
    options=codec.get('formatOptions')
    if options:
        lead,back=options['voices'];lead_end=112+4*lead
        source=source.replace('ldi r21, 240',f'ldi r21, {256-8*lead}')
        source=source.replace('ldi r21, 208',f'ldi r21, {256-8*back}')
        source=source.replace('cpi r26, 121',f'cpi r26, {lead_end+1}')
        source=source.replace('cpi r26, 120',f'cpi r26, {lead_end}')
        source=source.replace('ldi r26, 120',f'ldi r26, {lead_end}')
        source=source.replace('ldi r21, 2\n',f'ldi r21, {lead}\n')
        source=source.replace('ldi r21, 6\n',f'ldi r21, {back}\n')
        source=source.replace('sbrc r19, 0\n  subi r26, 254',f'sbrc r19, 0\n  subi r26, {256-options["pending"][0]}')
        grid_step=round(65536/(options['unitTicks']/480*.476190*18750/256))
        source=source.replace('ldi r16, 5\n  add r12',f'ldi r16, {grid_step&255}\n  add r12')
        source=source.replace('ldi r16, 22\n  adc r13',f'ldi r16, {grid_step>>8}\n  adc r13')
        source=source.replace('andi r17, 15\n  ldi r20, 143','''andi r17, 15
  ldi r30, lo8(song_gates)
  ldi r31, hi8(song_gates)
  add r30, r17
  adc r31, r29
  lpm r17, Z
  ldi r20, 143''')
        source=source.replace('load_chord:\n','  lpm r6, Z+\nload_chord:\n')
        source=source.replace('''  lpm r7, Z+
  st X+, r7
  lpm r7, Z+
  st X+, r7
  dec r21''','''  clr r7
  tst r6
  breq shape_low
  lpm r7, Z+
shape_low:
  st X+, r7
  tst r6
  breq shape_high
  lpm r7, Z+
  dec r6
shape_high:
  st X+, r7
  dec r21''')
    if normalization:
        if normalization['gain'] in (1,2,4,8,16):
            exponent={1:0,2:1,4:2,8:3,16:4}[normalization['gain']]
            source=source.replace('write_pwm:\n  subi r17, 128',
                'master_gain:\n'+''.join('  lsl r17\n' for _ in range(exponent))+'write_pwm:\n  subi r17, 128')
            normalization={**normalization,'implementation':'constant-shifts'}
        else:
            source=source.replace('write_pwm:\n  subi r17, 128',f'''master_gain:
  mov r22, r30
  ldi r30, lo8(output_gain)
  ldi r31, hi8(output_gain)
  subi r17, {normalization['minimum']&255}
  add r30, r17
  adc r31, r29
  lpm r17, Z
  mov r30, r22
  clr r31
write_pwm:''')
            normalization={**normalization,'implementation':'linear-flash-table'}
    if options or normalization:
        # The decoder's part selector is dead during synthesis. Reuse it for
        # the EEPROM bank, avoiding a comparison/branch in all eight voices.
        lead_end=112+4*(options['voices'][0] if options else 2)
        source=source.replace('render_sample:\n','render_sample:\n  ldi r19, 0\n')
        source=source.replace(f'''  ldi r16, 0
  cpi r26, {lead_end+1}
  brcs guitar_bank
  ldi r16, 16
guitar_bank:
''','  mov r16, r19\n')
        source=source.replace('  mov r20, r17\n','  mov r20, r17\n  ldi r19, 16\n',1)
    drums=bool(options and options.get('percussion'))
    if drums:
        drum_bank=module('mariachi_drum_bank','percussion-bank.py')
        drum_bank.verify_source()
        hits=drum_bank.select_kit('natural-kit',3)
        source=module('mariachi_drums','mariachi-percussion.py').specialize(source,hits)
    source=f'.set BASE_COUNT, {base_count}\n.set STREAM_SECOND, {codec["streamOffsets"][1]}\n'+source
    for name,data in [('song_shapes',codec['shapes']),('song_bases',[b for pair in codec['bases'] for b in pair]),
                      ('song_rules',[b for pair in codec['rules'] for b in pair]),('song_gaps',codec['gaps']),('song_stream',codec['stream'])]:
        if drums and name=='song_gaps':continue
        source+=name+':\n.byte '+','.join(map(str,data))+'\n'
    if options:source+='song_gates:\n.byte '+','.join(map(str,codec['gates']))+'\n'
    if normalization and normalization['implementation']=='linear-flash-table':
        source+='output_gain:\n.byte '+','.join(map(str,normalization['table']))+'\n'
    (folder/'synth.S').write_text(source,encoding='utf-8',newline='\n')
    assembler=module('poly_assembler','build-release-engine.py')
    rom,labels=assembler.assemble_relaxed(folder/'synth.S')
    assert len(rom)<=1024,f'Complete image exceeds ATtiny13A Flash: {len(rom)} bytes'
    (folder/'synth.bin').write_bytes(rom);(folder/'synth.hex').write_text(ihex(rom),encoding='ascii',newline='\n')
    bank=json.loads((ROOT/'ATtiny13A/Music/instruments/bank.json').read_text(encoding='utf-8'))
    profile=bank['instruments']['acoustic-guitar-nylon'];ep=bytearray(64)
    part_waves=[]
    for part in range(2):
        waves={}
        for index,register in enumerate(('low','high')):
            wave=profile['waves'][register][:]
            if part:
                # Circular binomial smoothing keeps the measured nylon profile,
                # reducing upper harmonics without adding a runtime audio filter.
                kernel=(1,4,6,4,1)
                wave=[round(sum(k*wave[(i+j-2)%16] for j,k in enumerate(kernel))/16) for i in range(16)]
            if register=='low' or part:
                zero=wave.index(0);wave=wave[zero:]+wave[:zero]
            waves[register]=wave
            offset=part*16+index*8
            ep[offset:offset+8]=bytes((wave[n]+8)|((wave[n+1]+8)<<4) for n in range(0,16,2))
        assert waves['low'][0]==0,'A zero DDS step/phase contributes exact silence'
        part_waves.append(waves)
    if drums:
        for index,step in enumerate(codec['pitchSteps']):ep[32+2*index:34+2*index]=bytes([step&255,step>>8])
    (folder/'eeprom.bin').write_bytes(ep);(folder/'eeprom.hex').write_text(ihex(ep),encoding='ascii',newline='\n')
    report=dict(engine='mariachi-polyphonic',experimental=False,flashBytes=len(rom),codeBytes=labels['song_shapes'],
        tableBytes=len(rom)-labels['song_shapes'],eepromBytes=64,labels=labels,scoreBytes=codec['scoreBytes'],
        sourceSha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),flashSha256=hashlib.sha256(rom).hexdigest(),
        eepromSha256=hashlib.sha256(ep).hexdigest(),decodedNotesSha256=codec['decodedNotesSha256'],
        sourceNotes=1027,sourceParts=2,maximumSimultaneousSourceNotes=7,oscillators=8,
        cpuHz=9600000,pwmHz=37500,synthesisHz=18750,unitTicks=160,ppqn=480,tempoMicroseconds=476190,
        gridStep=5637,envelopeEverySamples=256,voiceAddresses=list(range(112,144,4)),
        pendingSymbolAddresses=[[144,145],[146,147,148,149,150]],waves=part_waves[0],
        partWaves=part_waves,partWaveOffsets=[0,16],partGainShifts=[0,1],
        sourceSelection=dict(firstBeat=58,lastBeat=121),verifiedLosslessScore=arrangement is None)
    if arrangement:
        report['arrangement']=arrangement
        report['playedNotes']=sum(st['notes'] for st in codec['stats'])
        report['verifiedCodecRoundTrip']=True
        report['sourceSelection']=dict(firstBeat=arrangement['firstBeat'],lastBeat=arrangement['lastBeat'])
        report['sourceNotes']=sum(arrangement.get('sourceNotesByPart',[117,910]))
        if 'sourceMaximumSimultaneousNotes' in arrangement:
            report['maximumSimultaneousSourceNotes']=arrangement['sourceMaximumSimultaneousNotes']
            report['maximumSimultaneousPlayedNotes']=arrangement['playedMaximumSimultaneousNotes']
    if options:
        report['partVoiceCounts']=options['voices']
        report['pendingSymbolAddresses']=[list(range(144,144+options['pending'][0])),list(range(144+options['pending'][0],151))]
        report['unitTicks']=options['unitTicks'];report['gridStep']=grid_step
    if drums:
        report.update(oscillators=6,voiceAddresses=list(range(112,136,4)),decoderPartSelectors=[144,148],
            percussionProfile=dict(kit='natural-kit',hits={role:hits[role] for role in ('kick','hat')},
                bankSha256=hashlib.sha256(drum_bank.BANK_PATH.read_bytes()).hexdigest(),attenuationShift=3,
                pattern=['kick','hat'],gridUnitsPerHit=3,quarterBeatsPerHit=.5,
                stageRegister=6,phaseRegister=22,noiseHighRegister=7,countdownIo=54,
                countdownStorage='Unused OCR0A compare register; Fast PWM TOP=255, COM0A=0, OCIE0A=0',
                attenuationRounding='Add 4 before final ASR3; nearest integer after the original decay, ties toward positive infinity',
                stageEncoding='kick7..4, hat15..12; descending every two envelope ticks; active bit2; decay shifts 0,1,1,2',
                sourceVariant='cancion-del-mariachi',independentDrumVoices=1))
    if normalization:report['outputNormalization']=normalization
    report['activePrimaryVoices']=6 if drums else 8
    report['instrumentAssignments']={role:dict(instrument='acoustic-guitar-nylon',
        label='Акустическая гитара с нейлоновыми струнами',gmProgram=24,sourceVelocity=80,level=15)
        for role in ('leadGuitar','rhythmGuitar')}
    report['instrumentAssignments']['rhythmGuitar'].update(
        label='Мягкая нейлоновая гитара сопровождения',mixGain=0.5,mixGainDb=-6.020599913,
        waveDerivation='Circular [1,4,6,4,1]/16 smoothing of the measured nylon waves, rounded to 4-bit samples; both registers start at zero.')
    if drums:report['instrumentAssignments']['percussion']=dict(instrument='natural-kit',gmNotes=[35,42],level=2,
        label='Тихий бас-барабан и закрытый хай-хэт из прежней аранжировки')
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
    html=html.replace('мелодия, пианино, гитара и ударные.',
                      'две нейлоновые гитары, мягкое сопровождение на 6 дБ тише, все 1027 исходных нот и 8 тональных генераторов.')
    html=html.replace('lp.frequency.value=4000','lp.frequency.value=9000')
    html=html.replace('Файл preview.wav должен находиться рядом с player.html (он есть в ZIP).',
                      'Файл preview.wav находится рядом с player.html.')
    if arrangement:
        html=html.replace('Canción del Mariachi · все 1027 нот',arrangement['title'])
        html=html.replace('Canción del Mariachi · две гитары, все ноты',arrangement['title'])
        html=html.replace('две нейлоновые гитары, мягкое сопровождение на 6 дБ тише, все 1027 исходных нот и 8 тональных генераторов.',
                          'соло нейлоновой гитары, редкие басовые опоры и короткие аккордовые ответы. Сопровождение переработано.')
    if drums:html=html.replace('Сопровождение переработано.','Тихие бас-барабан и хай-хэт поддерживают ритм.')
    (folder/'player.html').write_text(html,encoding='utf-8',newline='\n')
    print(json.dumps({k:report[k] for k in ('flashBytes','codeBytes','tableBytes','sourceNotes')}))
    return report


def build_normalized(folder,codec=None,arrangement=None):
    """Calibrate the exact unscaled AVR, then compile its fixed master gain."""
    calibration=ROOT/'build'/('level-calibration-'+folder.name)
    baseline=build(calibration,codec=codec,arrangement=arrangement)
    end=max(g['off'] for part in (codec or compile_score())['parts'] for g in part['groups'])
    seconds=end/480*.476190+2
    result=subprocess.run(['node',str(ROOT/'tools/calibrate-firmware-level.mjs'),str(calibration),str(seconds)],
                          check=True,capture_output=True,text=True)
    normalization=json.loads(result.stdout)
    assert normalization['calibrationFlashSha256']==baseline['flashSha256']
    return build(folder,codec=codec,arrangement=arrangement,normalization=normalization)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'build/mariachi-lossless')
    parser.add_argument('--normalize-output',action='store_true',help='Measure the AVR loop and normalize real PWM peaks around midpoint 128')
    args=parser.parse_args();(build_normalized if args.normalize_output else build)(args.output)
