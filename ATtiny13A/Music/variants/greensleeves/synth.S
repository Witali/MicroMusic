.set GAIN_MINIMUM, 223
.set GRID_LOW, 251
.set GRID_HIGH, 13
.section .text,"ax",@progbits
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
  mov r12, r30
  ldi r30, lo8(output_gain)
  ldi r31, hi8(output_gain)
  subi r22, GAIN_MINIMUM
  add r30, r22
  adc r31, r29
  lpm r17, Z
  mov r30, r12
  clr r31
write_pwm:
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
part_levels:
.byte 15,12,11,10
pitch_steps:
.byte 128,1,176,1,201,1,1,2,32,2,64,2,135,2,173,2,1,3,95,3,146,3,201,3,2,4,63,4,128,4,13,5,90,5,2,6,190,6,37,7,146,7,5,8
song_rules:
.byte 64,96,0,32,193,192,129,194,0,192,42,72,197,102,130,193,128,196,15,198,131,194,43,73,45,73,100,195,195,17,14,42,71,98,207,208,13,71,16,203,16,204,18,48,19,49,74,98,77,100,77,104,100,130,195,213,200,15,205,210,206,198,212,221,219,216,223,218,0,15,101,222,128,194,133,194,199,20,200,211,209,195,224,129,225,226
song_stream:
.byte 201,206,47,74,102,202,18,204,103,195,19,45,72,230,128,0,64,214,74,104,233,64,77,195,234,231,227,202,201,195,15,41,73,99,199,14,220,70,99,129,196,16,46,215,229,10,215,131,196,201,206,47,74,102,202,18,204,103,195,19,45,72,230,128,0,64,214,74,104,233,96,205,234,231,103,222,199,16,220,203,97,195,209,199,12,200,232,201,229,201,202,129,22,48,74,133,193,64,22,51,217,199,21,50,228,214,217,224,202,234,231,227,202,201,195,15,41,73,99,199,14,220,70,99,129,196,16,46,215,202,232,10,215,131,196,129,22,48,74,133,193,64,22,51,217,230,50,228,214,217,233,96,205,225,47,228,211,227,199,16,220,203,97,195,209,199,12,200,232,201,229,201,202,128,255
output_gain:
.byte 0,4,8,12,16,19,23,27,31,35,39,43,47,50,54,58,62,66,70,74,78,81,85,89,93,97,101,105,109,112,116,120,124,128,132,136,140,144,147,151,155,159,163,167,171,175,178,182,186,190,194,198,202,206,209,213,217,221,225,229,233,237,240,244
