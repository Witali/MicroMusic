.section .text,"ax",@progbits
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
  clr r27
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
  clr r5
  ldi r19, 7
  ldi r20, 4
  ldi r16, 167
  mov r14, r16
  ldi r19, 6
  ldi r16, 1
  mov r8, r16
  ldi r30, lo8(first_section)
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
  brne render_sample
  rcall music_tick
render_sample:
  ldi r26, 96
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
  cpi r26, 121
  brne voice_loop
render_drum:
  /* Compact measured kit; parameters from percussion-bank.py. */
  cpi r20, 4
  brcc write_pwm
  cpi r19, 2
  brcs .L280
  rjmp .L298
.L280:
  ldi r17, 1
  add r14, r17
.L28a:
  mov r17, r14
  sbrc r17, 7
  com r17
  subi r17, 61
  asr r17
  asr r17
  rjmp .L2ae
.L298:
  mov r25, r5
  lsl r14
  adc r25, r25
  brcc .L2a0
  ldi r17, 45
  eor r14, r17
.L2a0:
  mov r5, r25
  mov r17, r14
  lsr r17
  andi r17, 63
  mov r25, r14
  andi r25, 63
  sbrc r19, 1
  sub r17, r25
  sbrs r19, 1
  subi r17, 32
  asr r17
  sbrc r19, 1
  asr r17
  sbrc r19, 1
  rjmp .L2ae
  asr r17
  mov r25, r15
  lsl r25
  subi r25, 65
  sbrc r25, 7
  com r25
  subi r25, 61
  asr r25
  asr r25
  add r17, r25
.L2ae:
  sbrc r20, 0
  asr r17
  sbrc r20, 1
  asr r17
  asr r17
  asr r17
  add r21, r17
write_pwm:
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
  ldi r26, 96
envelope_loop:
  ld r16, X+
  mov r17, r16
  andi r17, 15
  sbrs r16, 7
  rjmp state_release
state_plucked:
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
  mov r17, r16
  andi r17, 48
  brne state_gate
  lsr r25
state_gate:
  and r25, r24
  brne envelope_store
  dec r16
  rjmp envelope_store
state_release:
  tst r17
  breq envelope_store
  dec r16
  cpi r17, 1
  breq envelope_store
  sbrc r16, 6
  dec r16
envelope_store:

  subi r26, 1
  st X+, r16
  subi r26, 252
  cpi r26, 121
  brne envelope_loop
  sbrc r24, 0
  rjmp .L0a8
  cpi r20, 4
  brcc .L0a8
  inc r20
.L0a8:
  ldi r17, GRID_STEP_LOW
  add r2, r17
  ldi r17, GRID_STEP_HIGH
  adc r3, r17
  brcs grid_step
  ret
grid_step:
  dec r8
  brne .L0ba
  ldi r16, 3
  mov r8, r16
  subi r19, 254
  andi r19, 7
drum_trigger:
  sbrc r20, 7
  rjmp .L0ba
  clr r20
  ldi r16, 167
  mov r14, r16
.L0ba:
  dec r1
  breq read_event
  ret
read_event:
  /* Read packed score tokens. F0..FF are control events; E0..EF update accompaniment harmony. */
  lpm r16, Z+
  cpi r16, 255
  brne .L0c8
  rjmp next_section
.L0c8:
  cpi r16, 224
  brcs melodic_event
  cpi r16, 240
  brcs chord_event
note_off:
  ldi r26, 96
note_off_loop:
  ld r17, X+
  sbrc r16, 0
  andi r17, 127
  subi r26, 1
  st X+, r17
  subi r26, 252
  lsr r16
  cpi r26, 111
  brne note_off_loop
  sbrc r16, 0
  ldi r20, 132
  rjmp read_event
chord_event:
  andi r20, 127

  movw r12, r30
  andi r16, 15
  lsl r16
  lsl r16
  ldi r30, lo8(chord_steps)
  ldi r31, hi8(chord_steps)
  add r30, r16
  adc r31, r29
  ldi r26, 101
  ldi r25, 215
  rcall initialize_voice
  ldi r26, 106
  ldi r25, 170
  rcall initialize_voice
  movw r30, r12
  rjmp read_event
melodic_event:
  /* Decode compact note/duration; load 16-bit DDS increment or signal lead release. */
  movw r12, r30
  mov r17, r16
  andi r17, 7
  ldi r30, lo8(durations)
  ldi r31, hi8(durations)
  add r30, r17
  adc r31, r29
  lpm r1, Z
  /* BEGIN LEAD FREQUENCY */
  lsr r16
  lsr r16
  lsr r16
  cpi r16, REST_INDEX
  breq note_rest
  cpi r16, HOLD_INDEX
  breq hold_sample
  lsl r16
  ldi r30, lo8(note_steps)
  ldi r31, hi8(note_steps)
  add r30, r16
  adc r31, r29
  ldi r26, 96
  ldi r25, 143
  rcall initialize_voice
lead_commit:
  rjmp hold_sample
note_rest:
release_lead:
  lds r17, 96
  andi r17, 127
  sts 96, r17
hold_sample:
  movw r30, r12
  ret
next_section:
  /* Playlist contains direct section offsets: no second lookup table. */
  ldi r30, lo8(playlist)
  ldi r31, hi8(playlist)
  add r30, r4
  adc r31, r29
  lpm r16, Z
  tst r4
  brne drum_loop_continues
  clr r19
  clr r20
  ldi r17, 3
  mov r8, r17
  ldi r17, 167
  mov r14, r17
drum_loop_continues:
  inc r4
  mov r17, r4
  cpi r17, PLAYLIST_LEN
  brne .L15c
  clr r4
.L15c:
  ldi r30, lo8(melody_data)
  ldi r31, hi8(melody_data)
  add r30, r16
  adc r31, r29
  rjmp read_event
render_tone:
  /* Choose a register-dependent 16-step sustain wavetable and apply its amplitude envelope. */
  mov r0, r25
  andi r25, 15
  breq voice_silent
  cpi r16, 4
  mov r16, r0
  andi r16, 48
  brcs .L216
  ori r16, 8
.L216:
  cpi r26, 106
  brne piano_attack_done
  cpi r25, 14
  brcs piano_attack_done
  ori r16, 48
piano_attack_done:
  swap r17
  andi r17, 15
  lsr r17
  or r16, r17
  out 30, r16
  sbi 28, 0
  in r17, 29
  brcc eeprom_low_nibble
  swap r17
eeprom_low_nibble:
  andi r17, 15
  subi r17, 8
.L25c:
  mov r0, r17
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
  asr r17
  rjmp envelope_return
voice_silent:
  clr r17
  rjmp envelope_return
initialize_voice:
  rcall capture_ram_tail
  mov r16, r25
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
  lds r16, 111
  andi r16, 15
  lds r17, 116
  andi r17, 15
  sub r16, r17
  ldi r30, 111
  brcs ram_tail_destination
  ldi r30, 116
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
