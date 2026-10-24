.section .text,"ax",@progbits
.global vectors
.include "config.inc"
vectors:
  rjmp reset
voice_silent:
  clr r17
envelope_return:
  ret
  rjmp pwm_irq
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
  cpi r26, 108
  brcc piano_attack_done
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
  asr r17
  ret
reset:
  /* Requiredfuses7A/FF: CLKPRreset0; SPLresetRAMEND(9F). */
  clr r29
  clr r27
  clr r2
  clr r15
  clr r24
  ldi r16, 255
  mov r8, r16
  ldi r16, 128
  mov r14, r16
  ldi r30, 97
  clr r31
clear_ram:
  st Z+, r29
  cpi r30, 128
  brne clear_ram
  ldi r18, 128
fill_ring:
  st Z+, r18
  cpi r30, 144
  brne fill_ring
  mov r23, r18
  ldi r28, 128
  ldi r22, 142
  ldi r16, 1
  mov r1, r16
  mov r4, r16
  ldi r16, GRID_INITIAL_HIGH
  mov r3, r16
  ldi r30, lo8(first_section)
  ldi r31, hi8(first_section)
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
  ldi r26, 97
  clr r21
voice_loop:
  ld r25, X+
  ld r16, X+
  ld r7, X+
  ld r6, X+
  ld r17, X+
  andi r17, 127
  add r16, r6
  adc r7, r17
  subi r26, 4
  st X+, r16
  st X+, r7
  subi r26, 254
  mov r16, r17
  mov r17, r7
  rcall render_tone
  sbrc r26, 4
  asr r17
primary_gain:
  add r21, r17
  cpi r26, 127
  brne voice_loop
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
  ldi r26, 97
envelope_loop:
  ld r16, X+
  mov r17, r16
  andi r17, 15
  sbrs r16, 7
  rjmp state_release
  sbrs r16, 5
  rjmp state_plucked
  sbrc r24, 0
  rjmp envelope_store
  cpi r17, 7
  breq envelope_store
  inc r16
  rjmp envelope_store
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
  subi r26, 253
  ld r0, X+
  subi r26, 4
  sbrc r0, 7
  lsr r25
  sbrc r0, 7
  lsr r25
state_gate:
  and r25, r24
  brne envelope_store
  dec r16
  rjmp envelope_store
state_release:
  sbrs r16, 5
  rjmp ordinary_release
  mov r25, r24
  andi r25, 7
  brne envelope_store
ordinary_release:
  subi r17, 1
  brcs envelope_store
  breq release_last_level
  sbrc r16, 6
  dec r16
release_last_level:
  dec r16
envelope_store:
  st -X, r16
  subi r26, 251
  cpi r26, 127
  brne envelope_loop
.L0a8:
  ldi r17, GRID_STEP_LOW
  add r2, r17
  ldi r17, GRID_STEP_HIGH
  adc r3, r17
  brcs grid_step
  ret
grid_step:
  inc r8
  mov r16, r8
  andi r16, 15
  brne bar_clock_done
  inc r9
bar_clock_done:
.L0ba:
  dec r1
  breq read_event
  rjmp companion_grid
next_section:
  /* Playlist contains direct section offsets: no second lookup table. */
  ldi r30, lo8(playlist)
  ldi r31, hi8(playlist)
  add r30, r4
  lpm r16, Z
  inc r4
  mov r17, r4
  cpi r17, PLAYLIST_LEN
  brne .L15c
  clr r4
.L15c:
  ldi r30, lo8(melody_data)
  ldi r31, hi8(melody_data)
  add r30, r16
  rjmp read_event
read_event:
  /* Read packed score tokens. F0..FF are control events; E0..EF update accompaniment harmony. */
  lpm r16, Z+
  cpi r16, 255
  breq next_section
.L0c8:
  cpi r16, 151
  brcs melodic_event
  cpi r16, 254
  breq all_parts_off
chord_event:
  sbrs r14, 7
  rjmp macro_already_running
  clr r9
macro_already_running:
  subi r16, 142
  mov r14, r16
  rjmp read_event
all_parts_off:
  ldi r26, 97
all_parts_off_loop:
  ld r16, X
  andi r16, 127
  st X, r16
  subi r26, 251
  cpi r26, 117
  brne all_parts_off_loop
  ldi r16, 128
  mov r14, r16
  rjmp read_event
melodic_event:
  /* Decode compact note/duration; load 16-bit DDS increment or signal lead release. */
  movw r12, r30
  mov r17, r16
  andi r17, 7
  ldi r30, lo8(durations)
  ldi r31, hi8(durations)
  add r30, r17
  lpm r1, Z
  /* BEGIN LEAD FREQUENCY */
  lsr r16
  lsr r16
  lsr r16
  cpi r16, REST_INDEX
  breq note_rest
  brcc hold_sample
  ldi r26, 97
  ldi r25, 207
  rcall macro_note
lead_commit:
  rjmp hold_sample
note_rest:
release_lead:
  ldi r26, 97
  ld r17, X
  andi r17, 127
  st X, r17
  rjmp companion_grid
hold_sample:
companion_grid:
  mov r16, r9
  subi r16, 112
  cpi r16, 28
  brcc continuation_done
  ldi r16, 10
  ldi r26, 97
  ldi r25, 167
  rcall macro_note
continuation_done:
  movw r30, r12
  sbrc r14, 7
  ret
  mov r16, r8
  andi r16, 3
  breq companion_quarter
  cpi r16, 2
  brne companion_done
  ldi r26, 102
  ld r16, X
  andi r16, 127
  st X, r16
  rjmp companion_done
companion_quarter:
  mov r16, r14
  andi r16, 15
  cpi r16, 15
  breq companion_bass
  ldi r26, 102
  ldi r25, 199
  rcall macro_note
companion_bass:
  sbrc r14, 6
  rjmp companion_bass_on
  mov r16, r8
  andi r16, 15
  brne companion_done
companion_bass_on:
  mov r16, r14
  swap r16
  andi r16, 3
  cpi r16, 3
  breq companion_strings
  subi r16, 239
  ldi r26, 107
  ldi r25, 151
  rcall macro_note
companion_strings:
  mov r16, r8
  andi r16, 15
  brne companion_done
  mov r16, r9
  cpi r16, 8
  brcs companion_done
  mov r16, r14
  swap r16
  andi r16, 3
  cpi r16, 3
  brne companion_pad_pitch
  ldi r16, 2
companion_pad_pitch:
  ldi r26, 112
  ldi r25, 160
  rcall macro_note
companion_done:
  movw r30, r12
  ret
macro_note:
  lsl r16
  ldi r30, lo8(note_steps)
  ldi r31, hi8(note_steps)
  add r30, r16
  adc r31, r29
  rjmp initialize_voice
initialize_voice:
  rcall capture_ram_tail
  andi r16, 15
  lsr r16
  or r16, r25
  st -X, r16
  subi r26, 253
  lpm r16, Z+
  st X+, r16
  lpm r16, Z+
  st X+, r16
voice_initialized:
  ret
capture_ram_tail:
  movw r10, r30
  lds r16, 117
  andi r16, 15
  lds r17, 122
  andi r17, 15
  sub r16, r17
  ldi r30, 117
  brcs ram_tail_destination
  ldi r30, 122
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
