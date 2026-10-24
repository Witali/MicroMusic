.set BASE_COUNT, 59
.set STREAM_SECOND, 117
.section .text,"ax",@progbits
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
  ldi r19, 0
  ldi r26, 112
  ldi r21, 232
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
  in r17, 29
  brcc wave_nibble
  swap r17
wave_nibble:
  andi r17, 15
  add r21, r17
  cpi r26, 124
  brne rhythm_group
  mov r25, r4
  andi r25, 15
  rcall chord_gain
  mov r20, r17
  ldi r19, 16
  ldi r21, 216
rhythm_group:
  cpi r26, 144
  brne voice_loop
  mov r25, r5
  andi r25, 15
  rcall chord_gain
  asr r17
  add r17, r20
master_gain:
  lsl r17
  lsl r17
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
  ldi r16, 10
  add r12, r16
  ldi r16, 44
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
  subi r26, 252
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
  subi r26, 252
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
  ldi r30, lo8(song_gates)
  ldi r31, hi8(song_gates)
  add r30, r17
  adc r31, r29
  lpm r17, Z
  ldi r20, 143
  ldi r30, lo8(song_shapes)
  ldi r31, hi8(song_shapes)
  add r30, r6
  adc r31, r29
  ldi r26, 112
  ldi r21, 3
  sbrc r19, 0
  ldi r26, 124
  sbrc r19, 0
  ldi r21, 5
  lpm r6, Z+
load_chord:
  st X+, r29
  st X+, r29
  clr r7
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
  dec r21
  brne load_chord
chord_loaded:
  ret
song_shapes:
.byte 1,190,6,2,190,6,90,5,2,37,7,2,6,1,128,4,2,2,6,13,5,1,63,4,2,13,5,63,4,2,90,5,128,4,1,95,3,1,13,5,1,37,7,1,2,6,1,90,5,1,173,2,1,64,2,3,190,6,13,5,63,4,1,201,3,1,176,1,3,13,5,95,3,1,3,3,128,4,95,3,173,2,1,32,1,1,128,1
song_bases:
.byte 0,0,3,0,3,16,8,16,13,0,16,17,21,32,16,0,16,16,24,16,29,0,34,50,21,2,37,2,0,3,40,64,43,0,46,0,37,0,13,3,37,64,40,2,37,16,0,80,13,4,40,0,13,1,13,16,21,16,16,5,0,5,16,22,24,6,29,1,34,0,49,0,52,3,55,81,55,1,34,16,40,96,21,0,0,2,0,116,62,0,34,114,52,1,40,112,0,1,46,2,43,1,46,4,65,49,68,113,65,113,75,113,82,113,85,113,75,112
song_rules:
.byte 0,17,25,16,1,2,0,16,8,7,59,4,3,61,4,60,17,18,65,4,66,25,7,63,16,21,17,16,38,38,59,0,60,69,62,18,71,0,53,54,55,56,78,78,79,79,81,80,55,54,55,57,84,83
song_gaps:
.byte 0,2,4,48,14,12,8,6
song_stream:
.byte 0,61,1,68,68,5,6,7,70,2,70,1,63,9,10,11,12,13,14,15,62,67,19,20,77,22,77,23,18,77,24,75,74,59,76,16,16,72,64,17,4,17,75,74,62,76,72,67,26,27,17,1,61,1,68,68,5,28,18,7,70,29,30,63,8,2,7,31,32,33,4,34,35,36,37,73,73,73,38,64,39,17,26,40,64,17,64,64,41,42,43,67,4,41,44,34,45,34,46,47,16,69,48,49,0,50,13,16,51,75,74,59,76,72,67,4,255,52,78,82,82,85,85,82,82,82,85,85,58,255
song_gates:
.byte 2,6,4,24,12,1,3
