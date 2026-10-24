.set BASE_COUNT, 35
.set STREAM_SECOND, 71
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
song_shapes:
.byte 190,6,0,0,190,6,90,5,37,7,2,6,128,4,0,0,2,6,13,5,63,4,0,0,13,5,63,4,90,5,128,4,95,3,0,0,13,5,0,0,37,7,0,0,2,6,0,0,90,5,0,0,13,5,95,3,1,3,32,2,176,1,0,0,128,4,95,3,173,2,1,2,128,1,0,0,128,4,95,3,173,2,64,2,176,1,32,1,128,4,95,3,173,2,1,2,128,1,32,1,128,4,95,3,173,2,64,2,176,1,0,0,128,4,146,3,1,3,64,2,128,1,0,0
song_bases:
.byte 0,1,4,1,4,17,8,17,12,1,16,19,20,33,16,1,16,17,24,17,28,1,32,50,20,2,36,2,0,12,40,65,44,1,48,1,36,1,12,12,36,65,40,2,36,17,0,81,12,6,40,1,12,3,52,98,52,2,52,1,64,1,76,1,88,1,100,1,112,1
song_rules:
.byte 0,16,0,17,25,16,1,2,8,7,16,21,40,0,31,31,29,29,43,29,42,42,30,43,44,46,31,32,42,48,43,47,49,42,34,34,45,45,43,43,54,50
song_gaps:
.byte 0,1,2,24,7,6,20
song_stream:
.byte 0,38,1,3,38,4,3,38,4,5,6,7,7,39,2,7,39,1,39,9,10,11,12,13,14,15,35,17,18,19,20,41,22,41,23,18,41,24,37,4,37,25,36,0,36,35,18,16,16,17,16,36,4,17,4,17,37,4,37,25,36,0,35,35,18,17,16,17,18,26,255,27,28,47,55,53,48,53,51,44,33,50,55,53,48,53,51,44,33,50,55,45,42,52,34,30,52,51,47,51,52,34,30,52,51,47,42,31,255
