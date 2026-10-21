"""Compact three-primary/two-release AVR engine with a 16-byte PWM ring.

Required hardware fuses are Low 0x7A and High 0xFF. The MCU reset SPL and
clock values are used. Release slots retain full state and mix at half gain.
Only the explicitly checked three-part envelope combinations are supported.
"""
from pathlib import Path
import importlib.util
import re

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('release_assembler', ROOT/'tools/assemble-avr.py')
assembler=importlib.util.module_from_spec(spec);spec.loader.exec_module(assembler)

def assemble_relaxed(path):
    # Generated code may lengthen conditional branches beyond ±64words.
    # Use the ordinary inverse-condition + RJMP sequence on actual AVR.
    inverse={'breq':'brne','brne':'breq','brcs':'brcc','brcc':'brcs','brtc':'brts','brts':'brtc'}
    for serial in range(20):
        try:return assembler.assemble(path)
        except AssertionError as error:
            if not error.args or not isinstance(error.args[0],tuple):raise
            line,at,offset=error.args[0]
            op,target=line.split()
            if op not in inverse or -64<=offset<=63:raise
            label=f'release_long_branch_{serial}'
            source=path.read_text(encoding='utf-8')
            source=source.replace('  '+line+'\n',f'  {inverse[op]} {label}\n  rjmp {target}\n{label}:\n',1)
            path.write_text(source,encoding='utf-8',newline='\n')
    raise RuntimeError('Too many long branches')


def specialize(data, original):
    """Concrete five-state SRAM architecture, with an MCU-side PWM ring."""
    roles=('lead','keys','pluck');banks=(0,16,32)
    models=tuple(data[role] for role in ('lead_envelope_model','accompaniment_envelope_model','pluck_envelope_model'))
    if models not in (('bowed','piano','pluck'),('sustain','bowed','bowed'),('piano','piano','off'),('piano','pluck','off'),('piano','off','off')):
        raise ValueError('Unsupported release-slot instrument combination')
    if data.get('keys_rest_check') or data.get('pluck_rest_check'):
        raise ValueError('Release-slot profile requires nonzero companion DDS tables')
    if any(data[role+'_attack_step'] != 4 for role, model in zip(roles,models) if model in ('bowed','sustain')):
        raise ValueError('Release-slot sustained attack must be four levels per envelope tick')
    if any(data.get(role+'_'+phase+'_mask',0) for role in roles for phase in ('attack','release')):
        raise ValueError('This release-slot engine does not support gated attack/release masks; use a compatible native engine')
    addresses=(101,106,111)
    models=(data['lead_envelope_model'],data['accompaniment_envelope_model'],data['pluck_envelope_model'])
    caps=[data[role+'_max_level'] for role in roles]
    descriptors=[bank|(64 if model=='piano' else 0) for bank,model in zip(banks,models)]
    percussion=data.get('percussion_enabled',False)
    trigger=lambda voice:(f'  lds r16, {addresses[voice]}\n  andi r16, 15\n  lsr r16\n  ori r16, {128+descriptors[voice]}\n'
                          if data.get(roles[voice]+'_retrigger')!='full' else f'  ldi r16, {128+descriptors[voice]+caps[voice]}\n')+f'  sts {addresses[voice]}, r16\n'
    header='''.section .text,"ax",@progbits
.global vectors
.include "config.inc"
vectors:
  rjmp reset
envelope_return:
  asr r17
  ret
  rjmp pwm_irq
reset:
  /* Requiredfuses7A/FF: CLKPRreset0; SPLresetRAMEND(9F). */
  clr r29
  clr r2
  clr r15
  clr r24
  ldi r30, 96
  clr r31
clear_ram:
  st Z+, r29
  cpi r30, 144
  brne clear_ram
  ldi r18, 128
  ldi r30, 128
fill_ring:
  st Z+, r18
  cpi r30, 144
  brne fill_ring
  mov r23, r18
  ldi r28, 128
  ldi r22, 142
  ldi r16, 1
  mov r1, r16
  ldi r16, FIRST_PLAYLIST_INDEX
  mov r4, r16
  ldi r16, GRID_INITIAL_HIGH
  mov r3, r16
'''
    if percussion:header+='  clr r5\n  ldi r19, 7\n  ldi r20, 4\n  ldi r16, 167\n  mov r14, r16\n'
    header+='''  ldi r30, lo8(first_section)
  ldi r31, hi8(first_section)
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
  mov r16, r22
  sub r16, r28
  andi r16, 15
check_space:
  cpi r16, 13
  brcc idle
audio_step:
  inc r15
  breq producer_music_tick
  rjmp render_sample
producer_music_tick:
  rcall music_tick
  rjmp render_sample
pwm_irq:
  out 41, r18
ring_read:
  ld r18, Y+
  sbrc r28, 4
  ldi r28, 128
irq_restore:
  reti
music_tick:
  inc r24
  ldi r26, 101
  clr r27
envelope_loop:
  ld r16, X+
  mov r17, r16
  andi r17, 15
  sbrs r16, 7
  rjmp state_release
'''
    held=[i for i,model in enumerate(models) if model in ('bowed','sustain')]
    if held and len(held)!=3:
        header+='  mov r25, r16\n  andi r25, 48\n  brne state_plucked\n'
    if len(held)==3:
        header+=f'  ldi r25, {128+caps[0]+descriptors[0]}\n  sbrc r16, 4\n  ldi r25, {128+caps[1]+descriptors[1]}\n  sbrc r16, 5\n  ldi r25, {128+caps[2]+descriptors[2]}\n  subi r16, 252\n  mov r0, r16\n  sub r0, r25\n  brcs envelope_store\n  mov r16, r25\n  rjmp envelope_store\n'
    elif held:header+='  subi r16, 252\n  sbrc r16, 4\n  ldi r16, 143\n  rjmp envelope_store\n'
    if len(held)!=3:
        header+='''state_plucked:
  tst r17
  breq envelope_store
  ldi r25, 15
  cpi r17, 7
  brcs state_mask
  ldi r25, 7
  cpi r17, 10
  brcs state_mask
  ldi r25, 3
state_mask:
'''
        if held:header+='  sbrs r16, 4\n  lsr r25\n'
        if data.get('dds_fast_decay_roles'):
            header+='''  subi r26, 253
  ld r0, X+
  subi r26, 4
  sbrc r0, 7
  lsr r25
  sbrc r0, 7
  lsr r25
'''
        header+='''state_gate:
  and r25, r24
  brne envelope_store
  dec r16
  rjmp envelope_store
'''
    header+='state_release:\n  tst r17\n  breq envelope_store\n'
    # Bowed mains now use the bank's ordinary releaseStep1, as do their tails.
    # This intentionally replaces01's legacy fast-above-8 release special case.
    header+='''  dec r16
  cpi r17, 1
  breq envelope_store
  sbrc r16, 6
  dec r16
envelope_store:
'''+'''
  subi r26, 1
  st X+, r16
  subi r26, 252
  cpi r26, 126
  brne envelope_loop
'''
    if percussion:header+='  sbrc r24, 0\n  rjmp .L0a8\n  cpi r20, 4\n  brcc .L0a8\n  inc r20\n'
    header+='''.L0a8:
  ldi r17, GRID_STEP_LOW
  add r2, r17
  ldi r17, GRID_STEP_HIGH
  adc r3, r17
  brcs grid_step
  ret
grid_step:
'''
    if percussion:header+='  inc r19\n  andi r19, 7\n  sbrc r19, 0\n  rjmp .L0ba\ndrum_trigger:\n  sbrc r20, 7\n  rjmp .L0ba\n  clr r20\n  ldi r16, 167\n  mov r14, r16\n'
    header+='.L0ba:\n  dec r1\n  breq read_event\n  ret\n'
    decoder=original[original.index('read_event:'):original.index('render_tone:')]
    start,end=decoder.index('note_off:'),decoder.index('release_lead:')
    decoder=decoder[:start]+'''note_off:
  ldi r26, 101
  clr r27
note_off_loop:
  ld r17, X+
  sbrc r16, 0
  andi r17, 127
  subi r26, 1
  st X+, r17
  subi r26, 252
  lsr r16
  cpi r26, 116
  brne note_off_loop
'''+('  sbrc r16, 0\n  ldi r20, 132\n' if percussion else '')+'  rjmp read_event\n'+decoder[end:]
    start,end=decoder.index('release_lead:'),decoder.index('chord_event:')
    decoder=decoder[:start]+'''release_lead:
  lds r17, 101
  andi r17, 127
  sts 101, r17
  ret
'''+decoder[end:]
    trigger_bits=[128+descriptors[i]+(caps[i] if data.get(roles[i]+'_retrigger')=='full' else 0) for i in range(3)]
    # Both chord generators and lead share one physical note initializer.
    # For current full-retrigger instruments cap15 OR half-old is exactly15.
    full_only=all(data.get(roles[i]+'_retrigger')=='full' for i in range(3) if models[i]!='off')
    if not full_only:assert all(data.get(roles[i]+'_retrigger')!='full' or caps[i]==15 for i in range(3))
    start,end=decoder.index('chord_event:'),decoder.index('melodic_event:')
    decoder=decoder[:start]+'''chord_event:
'''+('  andi r20, 127\n' if percussion else '')+f'''
  movw r12, r30
  andi r16, 15
  lsl r16
  lsl r16
  ldi r30, lo8(chord_steps)
  ldi r31, hi8(chord_steps)
  add r30, r16
  adc r31, r0
  ldi r26, 106
  ldi r25, {trigger_bits[1]}
  rcall initialize_voice
  ldi r26, 111
  ldi r25, {trigger_bits[2]}
  rcall initialize_voice
  movw r30, r12
  rjmp read_event
'''+decoder[end:]
    decoder=decoder.replace('  lpm r22, Z','  lpm r1, Z')
    marker='  movw r26, r30\n  lsl r16\n  ldi r30, lo8(note_steps)'
    decoder=decoder.replace(marker,'  movw r12, r30\n  lsl r16\n  ldi r30, lo8(note_steps)',1)
    start,end=decoder.index('  lpm r4, Z+'),decoder.index('note_rest:')
    decoder=decoder[:start]+f'''  ldi r26, 101
  ldi r25, {trigger_bits[0]}
  rcall initialize_voice
lead_commit:
  movw r30, r12
  rjmp hold_sample
'''+decoder[end:]
    decoder=decoder.replace('  add r30, r28\n','  add r30, r4\n').replace('  inc r28\n','  inc r4\n').replace('  cpi r28, PLAYLIST_LEN\n','  mov r17, r4\n  cpi r17, PLAYLIST_LEN\n').replace('  clr r28\n','  clr r4\n')
    decoder=decoder.replace('  ldi r21, 3\n','  ldi r20, 3\n')
    release_start,release_end=decoder.index('release_lead:'),decoder.index('chord_event:')
    release_body=decoder[release_start:release_end]
    decoder=decoder[:release_start]+decoder[release_end:]
    decoder=decoder.replace('note_rest:\n  rjmp release_lead\n','note_rest:\n'+release_body)
    for i in (1,2):
        if models[i]=='off':
            decoder=decoder.replace(f'  ldi r26, {addresses[i]}\n  ldi r25, {trigger_bits[i]}\n  rcall initialize_voice\n','')
    if models[1]==models[2]=='off':
        a,b=decoder.index('chord_event:'),decoder.index('melodic_event:')
        decoder=decoder[:a]+'chord_event:\n  rjmp read_event\n'+decoder[b:]
    tone=original[original.index('render_tone:'):original.index('render_sample:')]
    a,b=tone.index('  cpi r16, 4'),tone.index('  mov r0, r17')
    tone=tone[:a]+'''  cpi r16, 4
  mov r16, r0
  andi r16, 48
  brcs .L216
  ori r16, 8
.L216:
'''+tone[b:]
    piano=[i for i,m in enumerate(models) if m=='piano']
    if piano:
        # A compile-time primary-role predicate excludes both release slots.
        if len(piano)==1:gate=f'  cpi r26, {addresses[piano[0]]+5}\n  brne piano_attack_done\n'
        elif piano==[0,1]:gate=f'  cpi r26, {addresses[1]+6}\n  brcc piano_attack_done\n'
        else:raise ValueError('Unsupported piano transient roles')
        tone=tone.replace('.L216:\n','.L216:\n'+gate+'''  cpi r25, 14
  brcs piano_attack_done
  ori r16, 48
piano_attack_done:
''',1)
    tone=tone.replace('  clr r0\n  ret\n','  rjmp envelope_return\n').replace('  clr r0\n  clr r17\n  ret\n','  clr r17\n  rjmp envelope_return\n')
    tone=tone.replace('  mov r16, r25\n','').replace('  sbrc r16, ','  sbrc r25, ')
    tone=tone.replace('  asr r17\n  asr r17\n  rjmp envelope_return','  asr r17\n  rjmp envelope_return')
    tone=tone.replace('  mov r0, r17\n  swap r17\n','  swap r17\n',1)
    tone=tone.replace('  add r16, r17\n','  or r16, r17\n',1)
    tone=tone.replace('  sbrc r0, 4\n  swap r17\n','  brcc eeprom_low_nibble\n  swap r17\neeprom_low_nibble:\n',1)
    render_loop='''render_sample:
  ldi r26, 101
  clr r27
  clr r21
voice_loop:
  ld r25, X+
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
  mov r16, r7
  rcall render_tone
  sbrc r26, 4
  asr r17
primary_gain:
  add r21, r17
  cpi r26, 126
  brne voice_loop
'''
    if data.get('dds_fast_decay_roles'):
        render_loop=render_loop.replace('  ld r17, X+\n  ld r6, X+\n  ld r7, X+\n',
            '  ld r7, X+\n  ld r6, X+\n  ld r17, X+\n  andi r17, 127\n')
        render_loop=render_loop.replace('  adc r17, r7\n','  adc r7, r17\n').replace('  st X+, r17\n','  st X+, r7\n')
        render_loop=render_loop.replace('  mov r16, r7\n','  mov r16, r17\n  mov r17, r7\n')
    drums=''
    if percussion:
        drums=original[original.index('render_drum:'):original.index('write_pwm:')]
        mapping={'r26':'r21','r29':'r19','r21':'r20'}
        drums=re.sub(r'\br(?:26|29|21)\b',lambda m:mapping[m[0]],drums)
        drums=drums.replace('  mov r27, r15\n  subi r27, 64','  mov r27, r15\n  lsl r27\n  subi r27, 65')
        drums=drums.replace('  lds r27, 96','  mov r27, r5').replace('  sts 96, r27','  mov r5, r27')
        drums=re.sub(r'\br27\b','r25',drums)
    publish='''write_pwm:
  subi r21, 128
  mov r16, r23
  add r16, r21
  ror r16
  mov r26, r22
  st X+, r16
  st X+, r21
  mov r22, r26
  andi r22, 143
ring_published:
  mov r23, r21
  rjmp idle
initialize_voice:
  rcall capture_ram_tail
  andi r16, 15
  lsr r16
  or r16, r25
  subi r26, 1
  st X+, r16
  subi r26, 254
  lpm r16, Z+
  st X+, r16
  lpm r16, Z+
  st X+, r16
voice_initialized:
  ret
capture_ram_tail:
  movw r10, r30
  clr r27
  lds r16, 116
  andi r16, 15
  lds r17, 121
  andi r17, 15
  sub r16, r17
  ldi r30, 116
  brcs ram_tail_destination
  ldi r30, 121
ram_tail_destination:
  ld r16, X+
  andi r16, 127
  mov r17, r16
  andi r17, 15
  breq no_ram_tail
  clr r31
  st Z+, r16
  ldi r17, 4
ram_tail_copy:
  ld r0, X+
  st Z+, r0
  dec r17
  brne ram_tail_copy
  subi r26, 4
no_ram_tail:
  movw r30, r10
  rjmp envelope_return
.include "score.inc"
'''
    if full_only:publish=publish.replace('  andi r16, 15\n  lsr r16\n  or r16, r25\n','  mov r16, r25\n',1)
    before_producer=header[:header.index('audio_step:')]
    after_producer=header[header.index('pwm_irq:'):]
    publish_body,initializers=publish.split('initialize_voice:',1)
    source=before_producer+'''audio_step:
  inc r15
  brne render_sample
  rcall music_tick
'''+render_loop+drums+publish_body+after_producer+decoder+tone+'initialize_voice:'+initializers
    # Main record ends101/106/111 havebit4clear; tailends116/121 havebit4set.
    # This permits a flag-preserving one-bit half-gain decision per voice.
    def move_pointer(match):
        value=int(match[2]);return match[1]+str(value-5 if 101<=value<=126 else value)
    source=re.sub(r'(?m)^(  (?:ldi r(?:26|30), |cpi r26, |lds r(?:16|17), ))(\d+)$',move_pointer,source)
    source=re.sub(r'(?m)^(  sts )(10[1-9]|11\d|12[0-6])(?=,)',lambda m:m[1]+str(int(m[2])-5),source)
    source=source.replace('  adc r31, r0\n','  adc r31, r29\n')
    # Keep XH permanently zero. The score's temporary Flash cursor belongs
    # in R12:R13, so its high byte cannot leak into SRAM addressing on REST.
    source=source.replace('  movw r26, r30\n','  movw r12, r30\n').replace('  movw r30, r26\n','  movw r30, r12\n')
    source=source.replace('  clr r27\n','')
    source=source.replace('  clr r29\n','  clr r29\n  clr r27\n',1)
    if models[1]==models[2]=='off' and not data.get('timed_controls'):
        # The compiler proves this bytecode contains only lead/rest/HOLD and
        # FF. No companion decoder or NoteOff-mask loop can be reached.
        a,b=source.index('read_event:'),source.index('melodic_event:')
        source=source[:a]+'''read_event:
  lpm r16, Z+
  cpi r16, 255
  breq next_section
'''+source[b:]
        source=source.replace('  lds r16, 111\n  andi r16, 15\n  lds r17, 116\n  andi r17, 15\n',
            '  lds r16, 111\n  lds r17, 116\n')
    # Share one authoritative Flash cursor through duration/DDS lookups.
    source=source.replace('  lpm r1, Z\n  movw r30, r12\n','  lpm r1, Z\n',1)
    source=source.replace('  movw r12, r30\n  lsl r16\n  ldi r30, lo8(note_steps)',
                          '  lsl r16\n  ldi r30, lo8(note_steps)',1)
    source=source.replace('lead_commit:\n  movw r30, r12\n','lead_commit:\n',1)
    source=source.replace('hold_sample:\n  ret\n','',1)
    source=source.replace('  sts 96, r17\n  ret\n',
                          '  sts 96, r17\nhold_sample:\n  movw r30, r12\n  ret\n',1)
    # Horner form gives the same signed sample times four-bit envelope level.
    old='''  mov r0, r17
  clr r17
  sbrc r25, 0
  add r17, r0
  lsl r0
  sbrc r25, 1
  add r17, r0
  lsl r0
  sbrc r25, 2
  add r17, r0
  lsl r0
  sbrc r25, 3
  add r17, r0
'''
    new='''  mov r0, r17
  sbrs r25, 3
  clr r17
  lsl r17
  sbrc r25, 2
  add r17, r0
  lsl r17
  sbrc r25, 1
  add r17, r0
  lsl r17
  sbrc r25, 0
  add r17, r0
'''
    if source.count(old)!=1:
        raise ValueError('Expected one amplitude multiplier in the release-slot kernel')
    return source.replace(old,new,1)

