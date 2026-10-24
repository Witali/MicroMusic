"""Specialize the compact Mariachi player with its retained kick/hat kit.

Six tonal oscillators retain all three-note chords of each guitar. Persistent
R6/R7/R22 hold the old four-stage drum and 16-bit LFSR. The score uses EEPROM
pitch steps and high-bit-terminated chord shapes to make room for percussion.
"""


def specialize(source,hits):
    # These exact retained generators are implemented below. A changed kit
    # must not silently acquire metadata for an unimplemented waveform.
    assert hits['kick']['generator']==dict(kind='triangle',phaseSource='per-hit R14',
        phaseStep=1,phaseStart=168,phaseOffset=0,triangleBias=61,triangleShift=2)
    assert hits['hat']['generator']==dict(kind='noise',noiseMode='difference',noiseShift=2)
    for role in ('kick','hat'):
        assert hits[role]['gainShift']==3
        assert hits[role]['envelope']['decayShifts']==[0,1,1,2] and hits[role]['envelope']['ticksPerStep']==2
        assert hits[role]['noise']==dict(bits=16,feedbackXor=45,nonzeroSeed=167,period=65535)
    source=source.replace('  cpi r26, 144\n','  cpi r26, 136\n')
    source=source.replace('  mov r22, r30\n','  push r30\n').replace('  mov r30, r22\n','  pop r30\n')
    # R6/R7 become persistent drum state; the decoder saves them during control
    # updates, while synthesis uses its otherwise dead R24/R25 for DDS steps.
    start,end=source.index('render_sample:'),source.index('write_pwm:')
    region=source[start:end].replace('ld r6, X+','ld r24, X+').replace('ld r7, X+','ld r25, X+')
    region=region.replace('add r16, r6','add r16, r24').replace('adc r17, r7','adc r17, r25')
    region=region.replace('  mov r25, r7\n','')
    source=source[:start]+region+source[end:]
    # Direct register-file clearing saves twenty Flash bytes.
    start,end=source.index('  clr r0\n'),source.index('  ldi r16, 1\n')
    source=source[:start]+'''  ldi r26, 0
clear_registers:
  st X+, r16
  cpi r26, 16
  brne clear_registers
'''+source[end:]
    source=source.replace('  mov r1, r16\n','  mov r1, r16\n  sub r6, r16\n',1)
    source=source.replace('  ldi r16, 1\n  mov r1, r16','  ldi r16, 1\n  out 54, r16\n  mov r1, r16')
    source=source.replace('restart_song:\n','restart_song:\n  ldi r16, 15\n  mov r6, r16\n')
    # Absolute stack bases replace repeated conditional address arithmetic.
    old='''  mov r26, r24
  subi r26, 112
  sbrc r19, 0
  subi r26, 252'''
    assert source.count(old)==2
    source=source.replace(old,'  mov r26, r24\n  add r26, r19')
    source=source.replace('  ldi r19, 0\n  rcall part_tick','  ldi r19, 144\n  rcall part_tick')
    source=source.replace('  ldi r19, 1\n  rcall part_tick','  ldi r19, 148\n  rcall part_tick')
    source=source.replace('  sbrc r19, 0\n','  sbrc r19, 2\n')
    source=source.replace('''  mov r21, r7
  swap r21
  andi r21, 7
  ldi r30, lo8(song_gaps)
  ldi r31, hi8(song_gaps)
  add r30, r21
  adc r31, r29
  lpm r17, Z''','''  mov r17, r7
  lsr r17
  lsr r17
  andi r17, 62''')
    source=source.replace('  andi r17, 15\n  ldi r30, lo8(song_gates)','  andi r17, 7\n  ldi r30, lo8(song_gates)')
    start,end=source.index('  ldi r26, 112\n  ldi r21, 3\n'),source.index('chord_loaded:')
    source=source[:start]+'''  ldi r26, 112
  sbrc r19, 2
  ldi r26, 124
  ldi r21, 12
clear_chord:
  st X+, r29
  dec r21
  brne clear_chord
  subi r26, 12
load_chord:
  lpm r6, Z+
  mov r25, r6
  andi r25, 127
  out 30, r25
  sbi 28, 0
  in r7, 29
  subi r26, 254
  st X+, r7
  inc r25
  out 30, r25
  sbi 28, 0
  in r7, 29
  st X+, r7
  sbrs r6, 7
  rjmp load_chord
'''+source[end:]
    source=source.replace('music_tick:\n  inc r14\n','''music_tick:
  inc r14
  sbrc r14, 0
  rjmp drum_envelope_done
  sbrc r6, 2
  dec r6
drum_envelope_done:
''')
    # OCR0A is unused in Fast PWM TOP=255: COM0A=0 and OCIE0A=0.
    # Counter updates are a full grid tick apart, far longer than the PWM
    # double-buffer update at BOTTOM. OCR0B remains the audio output.
    source=source.replace('music_step:\n','''music_step:
  in r16, 54
  dec r16
  brne drum_count_saved
  ldi r16, 3
  ldi r21, 8
  eor r6, r21
  ldi r21, 7
  or r6, r21
drum_trigger:
  ldi r22, 167
drum_count_saved:
  out 54, r16
  push r6
  push r7
''')
    source=source.replace('music_return:\n  ret','  pop r7\n  pop r6\nmusic_return:\n  ret')
    marker='master_gain:' if 'master_gain:' in source else 'write_pwm:'
    source=source.replace(marker,'''render_drum:
  clr r17
  sbrs r6, 2
  rjmp drum_mixed
  sbrc r6, 3
  rjmp render_hat
render_kick:
  inc r22
  mov r17, r22
  sbrc r17, 7
  com r17
  subi r17, 61
  asr r17
  asr r17
  rjmp drum_gain
render_hat:
  lsl r22
  adc r7, r7
  brcc noise_advanced
  ldi r25, 45
  eor r22, r25
noise_advanced:
  mov r17, r22
  lsr r17
  andi r17, 63
  mov r25, r22
  andi r25, 63
  sub r17, r25
  asr r17
  asr r17
drum_gain:
  sbrs r6, 0
  asr r17
  sbrs r6, 1
  asr r17
  subi r17, 252
  asr r17
  asr r17
  asr r17
drum_mixed:
  add r17, r20
'''+marker)
    source=source.replace('  add r17, r20\nrender_drum:\n','  add r20, r17\nrender_drum:\n')
    return source
