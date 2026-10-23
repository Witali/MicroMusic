/* Smoothed PWM: two future points and their midpoint are prepared in foreground.
 * SRAM[0x60] = noise high, [0x61/62] = right midpoint/next,
 * [0x63] = divider, [0x64] = grid high, [0x65/66] = left midpoint/next. R25 = grid low.
 * R18 belongs to ISR; R23 swaps 0x01/0x10 without changing arithmetic flags.
 * Sound generation 18.75 kHz; distinct interpolated output values 37.5 kHz.
 * Piano/guitar use soft sustain spectra with their measured envelopes.
 * Per-sample attack/sustain spectral crossfade omitted to fit 1 KB Flash.
 */
.section .text,"ax",@progbits
.global vectors
.include "../../../../web-player/native/attiny13a-registers.generated.inc"
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
  /* SPL resets to RAMEND=159. Switch the internal RC divider to 9.6 MHz. */
  ldi r16, 128
  out CLKPR, r16
  clr r16
  out CLKPR, r16
  clr r0
  sts 96, r0
  ldi r30, 1
  clr r31
clear_registers:
  /* Clear oscillator and envelope registers without allocating SRAM. R18/R23 are subsequently reserved for the ISR. */
  st Z+, r16
  cpi r30, 30
  brne clear_registers
  ldi r18, 128
  sts 101, r18
  sts 102, r18
  ldi r30, 97
  st Z+, r18
  st Z+, r18
  st Z+, r0
  /* Initialize four sound channels, score cursor, and deterministic percussion noise. */
  ldi r16, 4
  mov r21, r16
  inc r22
  inc r28
  ldi r16, GRID_INITIAL_HIGH
  sts 100, r16
  ldi r29, 7
  ldi r30, lo8(first_section)
  ldi r31, hi8(first_section)
  ldi r16, 167
  mov r14, r16
  /* Configure hardware stereo Fast PWM on OC0A/PB0 and OC0B/PB1, fixed TOP=255 at 37.5 kHz. */
  sbi DDRB, 0
  sbi DDRB, 1
  out OCR0A, r18
  out OCR0B, r18
  ldi r23, 1
  ldi r16, 163
  out TCCR0A, r16
  ldi r16, 1
  out TCCR0B, r16
  ldi r16, 2
  out TIMSK0, r16
  sei
idle:
  brtc idle
  clt
  rcall audio_step
  rjmp idle
pwm_irq:
  /* Read both channels in one ISR; Loads/OUT/skip/SWAP preserve arithmetic flags.
   * Foreground publishes both midpoint/next pairs only after the next-point phase. */
  sbrc r23, 0
  lds r18, 101
  sbrs r23, 0
  lds r18, 102
  out OCR0A, r18
  sbrc r23, 0
  lds r18, 97
  sbrs r23, 0
  lds r18, 98
  out OCR0B, r18
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
  sbrs r1, 7
  rjmp .L084
  mov r16, r1
  subi r16, 252
  cpi r16, 144
  brcs lead_attack_ready
  ldi r16, 143
lead_attack_ready:
  mov r1, r16
  rjmp .L08e
.L084:
  tst r1
  breq .L08e
  dec r1
  sbrc r1, 3
  dec r1
.L08e:
  /* Piano and guitar use one shared envelope function with different decay masks. */
  mov r16, r19
  ldi r17, 3
  rcall update_envelope
  mov r19, r16
  mov r16, r20
  ldi r17, 1
  rcall update_envelope
  mov r20, r16
  /* Percussion decays on alternate ticks, retriggering in a four-beat rhythm. */
  sbrc r24, 0
  rjmp .L0a8
  cpi r21, 4
  brcc .L0a8
  inc r21
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
  inc r29
  andi r29, 7
  sbrc r29, 0
  rjmp .L0ba
drum_trigger:
  clr r21
  ldi r16, 167
  mov r14, r16
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
  sbrc r16, 2
  andi r20, 15
  sbrc r16, 3
  ldi r21, 3
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
  lpm r12, Z+
  lpm r13, Z+
  clr r7
  clr r11
  ldi r16, 143
  mov r19, r16
  mov r20, r16
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
  lsr r16
  lsr r16
  lsr r16
  cpi r16, REST_INDEX
  breq release_lead
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
  mov r16, r1
  andi r16, 15
  lsr r16
  ori r16, 128
lead_commit:
  mov r1, r16
hold_sample:
  ret
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
  out EEARL, r16
  sbi EECR, 0
  in r17, EEDR
  sbrc r0, 4
  swap r17
  andi r17, 15
  subi r17, 8
.L25c:
  /* Four-bit signed scaling, looped to leave Flash for the second output. */
  mov r0, r17
  clr r17
scale_bit:
  sbrc r25, 0
  add r17, r0
  lsl r0
  lsr r25
  brne scale_bit
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
  add r2, r4
  adc r3, r5
  mov r25, r1
  mov r16, r5
  mov r17, r3
  rcall render_tone
  add r26, r17
  mov r27, r17
  asr r27
  add r6, r8
  adc r7, r9
  mov r25, r19
  ori r25, 16
  mov r16, r9
  mov r17, r7
  rcall render_tone
  add r26, r17
  add r27, r17
  add r10, r12
  adc r11, r13
  mov r25, r20
  ori r25, 32
  mov r16, r13
  mov r17, r11
  rcall render_tone
  add r27, r17
  asr r17
  add r26, r17
render_drum:
  /* Add bass drum or band-limited pseudo-random percussion; center the mix on PWM duty 128. */
  cpi r21, 4
  brcc write_pwm
  tst r29
  breq .L280
  rjmp .L298
.L280:
  inc r14
.L28a:
  mov r17, r14
  sbrc r17, 7
  com r17
  subi r17, 61
  asr r17
  asr r17
  rjmp .L2ae
.L298:
  lds r16, 96
  lsl r14
  adc r16, r16
  brcc .L2a0
  ldi r17, 45
  eor r14, r17
.L2a0:
  sts 96, r16
  mov r17, r14
  lsr r17
  andi r17, 63
  mov r16, r14
  andi r16, 63
  sbrc r29, 1
  sub r17, r16
  sbrs r29, 1
  subi r17, 32
  asr r17
  sbrc r29, 1
  asr r17
.L2ae:
  sbrc r21, 0
  asr r17
  sbrc r21, 1
  asr r17
  add r26, r17
  add r27, r17
write_pwm:
  /* Center each mix, interpolate unsigned duties, then publish a complete pair. */
  subi r26, 128
  subi r27, 128
  lds r16, 102
  add r16, r26
  ror r16
  lds r17, 98
  add r17, r27
  ror r17
publish_wait:
  sbrs r23, 0
  rjmp publish_wait
  sts 101, r16
  sts 102, r26
  sts 97, r17
  sts 98, r27
  pop r25
  ret

  /* The duration table, 16-bit DDS increments, chords, playlist and score. */
.include "score.inc"
