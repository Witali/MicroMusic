/* Smoothed PWM: two future points and their midpoint are prepared in foreground.
 * SRAM[0x60]=noise high, [0x61]=midpoint, [0x62]=next point, [0x63]=music divider, [0x64]=high grid phase; R25=low grid phase.
 * R18 belongs to ISR; R23 swaps 0x01/0x10 without changing arithmetic flags.
 * Sound generation 18.75 kHz; distinct interpolated output values 37.5 kHz.
 * Build-time assignments specialize oscillators and instrument envelopes.
 * Per-sample attack/sustain spectral crossfade omitted to fit 1 KB Flash.
 */
.section .text,"ax",@progbits
.global vectors
.include "config.inc"

vectors:
  rjmp reset
envelope_return:
  clr r0
  ret
  rjmp pwm_irq
update_envelope:
  mov r0, r17
  mov r17, r16
  andi r17, 15
  breq envelope_return
  sbrs r16, 7
  rjmp envelope_release
  cpi r17, 10
  brcc envelope_gate
  lsl r0
  inc r0
  cpi r17, 7
  brcc envelope_gate
  lsl r0
  inc r0
envelope_gate:
  mov r17, r24
  and r17, r0
  brne envelope_return
  dec r16
  rjmp envelope_return
envelope_release:
  dec r16
  breq envelope_return
  sbrc r0, 1
  dec r16
  rjmp envelope_return
reset:
  /* Initialize the stack and switch the internal RC from the factory /8 divider to 9.6 MHz. */
  ldi r16, 159
  out 61, r16
  ldi r16, 128
  out 38, r16
  clr r16
  out 38, r16
  clr r0
  clr r1
  ldi r30, 2
  clr r31
  clr r16
clear_registers:
  /* Clear oscillator and envelope registers without allocating SRAM. R18/R23 are subsequently reserved for the ISR. */
  st Z+, r16
  cpi r30, 26
  brne clear_registers
  ldi r18, 128
  ldi r30, 97
  st Z+, r18
  st Z+, r18
  st Z+, r0
  /* Initialize four sound channels, score cursor, and deterministic percussion noise. */
  ldi r16, 1
  mov r22, r16
  ldi r28, FIRST_PLAYLIST_INDEX
  ldi r16, GRID_INITIAL_HIGH
  sts 100, r16
  ldi r30, lo8(first_section)
  ldi r31, hi8(first_section)
  /* Configure hardware Fast PWM on OC0B/PB1, fixed TOP=255 at 37.5 kHz. */
  sbi 23, 1
  out 41, r18
  ldi r23, 1
  ldi r16, 35
  out 47, r16
  ldi r16, 1
  out 51, r16
  ldi r16, 2
  out 57, r16
  sei
idle:
  brtc idle
  clt
  rcall audio_step
  rjmp idle
pwm_irq:
  /* No arithmetic or temporary-register writes: foreground C/Z flags survive. */
  out 41, r18
  sbrc r23, 0
  lds r18, 97
  sbrs r23, 0
  lds r18, 98
  swap r23
  set
  reti
audio_step:
  /* Foreground tick. Odd ticks produce new four-voice points; envelopes tick every 512 overflows, score uses the fractional sixteenth grid. */
  inc r15
  breq .L064
  sbrs r15, 0
  rjmp hold_sample
  rjmp render_sample
.L064:
  lds r16, 99
  com r16
  sts 99, r16
  breq music_tick
  rjmp hold_sample
music_tick:
  /* Advance envelopes at ~73.24 Hz. Flags in envelope bytes encode attack, sustain and release. */
  inc r24
  mov r16, r1
  ldi r17, 3
  rcall update_envelope
  mov r1, r16
  /* END LEAD ENVELOPE */
.L08e:
  /* Piano and guitar use one shared envelope function with different decay masks. */
  sbrs r19, 7
  rjmp keys_env_release
  mov r16, r19
  subi r16, 254
  cpi r16, 135
  brcs keys_env_attack
  ldi r16, 134
keys_env_attack:
  mov r19, r16
  rjmp keys_env_done
keys_env_release:
  tst r19
  breq keys_env_done
  dec r19
keys_env_done:
  /* END KEYS ENVELOPE */
  /* END PLUCK ENVELOPE */
.L0a8:
  /* R25: low grid phase, SRAM[0x64]: high. One overflow = one sixteenth. */
  lds r16, 100
  ldi r17, GRID_STEP_LOW
  add r25, r17
  ldi r17, GRID_STEP_HIGH
  adc r16, r17
  sts 100, r16
  brcs grid_step
  ret
grid_step:
.L0ba:
  dec r22
  breq read_event
  rjmp hold_sample
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
  /* NOTE-OFF bitmask: bit0 violin, bit1 piano, bit2 guitar, bit3 percussion. No oscillator resets. */
  sbrc r16, 0
  rcall release_lead
  sbrc r16, 1
  andi r19, 15
  rjmp read_event
release_lead:
  /* Change lead from attack/sustain into release without resetting DDS phase. */
  mov r17, r1
  andi r17, 15
  mov r1, r17
  ret
chord_event:
  /* Decode chord index; load two independent DDS frequencies and restart their envelopes. */
  movw r26, r30
  andi r16, 15
  lsl r16
  lsl r16
  ldi r30, lo8(chord_steps)
  ldi r31, hi8(chord_steps)
  add r30, r16
  adc r31, r0
  lpm r8, Z+
  lpm r9, Z+
  mov r16, r19
  andi r16, 15
  lsr r16
  ori r16, 128
  mov r19, r16
  /* END COMPANION TRIGGERS */
  movw r30, r26
  rjmp read_event
melodic_event:
  /* Decode compact note/duration; load 16-bit DDS increment or signal lead release. */
  movw r26, r30
  mov r17, r16
  andi r17, 7
  ldi r30, lo8(durations)
  ldi r31, hi8(durations)
  add r30, r17
  adc r31, r0
  lpm r22, Z
  movw r30, r26
  /* BEGIN LEAD FREQUENCY */
  lsr r16
  lsr r16
  lsr r16
  cpi r16, REST_INDEX
  breq note_rest
  cpi r16, HOLD_INDEX
  breq hold_sample
  movw r26, r30
  lsl r16
  ldi r30, lo8(note_steps)
  ldi r31, hi8(note_steps)
  add r30, r16
  adc r31, r0
  lpm r4, Z+
  lpm r5, Z+
  movw r30, r26
  ldi r16, 143
lead_commit:
  mov r1, r16
  rjmp hold_sample
note_rest:
  rjmp release_lead
next_section:
  /* Playlist contains direct section offsets: no second lookup table. */
  ldi r30, lo8(playlist)
  ldi r31, hi8(playlist)
  add r30, r28
  adc r31, r0
  lpm r16, Z
  inc r28
  cpi r28, PLAYLIST_LEN
  brne .L15c
  clr r28
.L15c:
  ldi r30, lo8(melody_data)
  ldi r31, hi8(melody_data)
  add r30, r16
  adc r31, r0
  rjmp read_event
hold_sample:
  ret
render_tone:
  /* Choose a register-dependent 16-step sustain wavetable and apply its amplitude envelope. */
  mov r0, r25
  andi r25, 15
  breq voice_silent
  cpi r16, 4
  ldi r16, 0
  brcs .L216
  ldi r16, 8
.L216:
  sbrc r0, 4
  subi r16, 240
  sbrc r0, 5
  subi r16, 224
  mov r0, r17
  swap r17
  andi r17, 15
  lsr r17
  add r16, r17
  out 30, r16
  sbi 28, 0
  in r17, 29
  sbrc r0, 4
  swap r17
  andi r17, 15
  subi r17, 8
.L25c:
  mov r16, r25
  mov r0, r17
  clr r17
  sbrc r16, 0
  add r17, r0
  lsl r0
  sbrc r16, 1
  add r17, r0
  lsl r0
  sbrc r16, 2
  add r17, r0
  lsl r0
  sbrc r16, 3
  add r17, r0
  asr r17
  asr r17
  clr r0
  ret
voice_silent:
  clr r0
  clr r17
  ret
render_sample:
  /* Accumulate three pitch oscillators with independent phases and envelopes. */
  push r25
  clr r26
  /* BEGIN LEAD RENDER */
  add r2, r4
  adc r3, r5
  mov r25, r1
  mov r16, r5
  mov r17, r3
  rcall render_tone
  add r26, r17
  /* END LEAD RENDER */
  /* BEGIN KEYS RENDER */
  add r6, r8
  adc r7, r9
  mov r25, r19
  ori r25, 16
  mov r16, r9
  mov r17, r7
  rcall render_tone
  add r26, r17
  /* END KEYS RENDER */
  /* END PLUCK RENDER */
write_pwm:
  /* Convert the bipolar mix to unsigned PWM; publish the next pair after a safe handoff. */
  subi r26, 128
  lds r16, 98
  add r16, r26
  ror r16
publish_wait:
  /* The midpoint IRQ must first copy the old next point into R18. */
  sbrs r23, 0
  rjmp publish_wait
  sts 97, r16
  sts 98, r26
  pop r25
  ret

  /* The duration table, 16-bit DDS increments, chords, playlist and score. */
.include "score.inc"
