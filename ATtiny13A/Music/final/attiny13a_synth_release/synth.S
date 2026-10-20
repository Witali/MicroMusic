/* ATtiny13A: 4-voice spectral DDS player, smoothed envelopes and per-voice note-off.
 * REPRODUCIBLE SOURCE: reconstructed as GNU AVR mnemonics from the 1KB
 * ATtiny13A release binary; running build.py reassembles and byte-compares it.
 * All addresses, and every opcode, are retained. A general purpose source
 * patcher can modify notes and wavetables using score/EEPROM utilities.
 *
 * Clock: 9.6MHz internal RC, CKDIV8 OFF (low fuse 0x7A).
 * PWM: OC0B/PB1, Timer0 Fast PWM 8 bit /1 = 37500Hz;
 * DDS outputs: 18750 samples/s (one new duty each two periods).
 * EEPROM: 64 bytes, packed 4-bit spectra selected by pitch and attack age.
 *
 * The interrupt owns the full register file and uses the hardware PC stack;
 * the foreground does not modify registers while interrupts are enabled.
 * This player intentionally depends on these register allocations.
 *
 * NOTES ABOUT THE RECOVERED SOURCE:
 * Instructions are genuine GNU AVR mnemonics (not opaque .word directives).
 * Numeric byte-address constants identify Flash data tables and can be
 * kept stable by the assembler; add or remove instructions only after
 * reviewing the absolute pointers and checking memory/timing.
 * Avoid blanket per-instruction commentary: headings describe algorithms.
 */
.section .text,"ax",@progbits
.global vectors
.include "config.inc"

vectors:
  rjmp reset
  nop
  nop
  rjmp audio_irq
  nop
  nop
  nop
  nop
  nop
  nop
reset:
  /* Initialize the stack and switch the internal RC from the factory /8 divider to 9.6 MHz. */
  cli
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
  /* Clear oscillator and envelope registers without allocating SRAM. The ISR owns the register file. */
  st Z+, r16
  cpi r30, 26
  brne clear_registers
  /* Initialize four sound channels, score cursor, and deterministic percussion noise. */
  ldi r16, 4
  mov r21, r16
  ldi r16, 1
  mov r22, r16
  mov r28, r16
  ldi r30, lo8(melody_data)
  ldi r31, hi8(melody_data)
  ldi r16, 167
  mov r14, r16
  /* Configure hardware Fast PWM on OC0B/PB1, fixed TOP=255 at 37.5 kHz. */
  sbi 23, 1
  ldi r18, 128
  out 41, r18
  ldi r16, 35
  out 47, r16
  ldi r16, 1
  out 51, r16
  ldi r16, 2
  out 57, r16
  sei
idle:
  rjmp idle
audio_irq:
  /* Timer0 overflow. Even samples run the four-voice mixer; score events are decoded every 512 overflows. */
  inc r15
  breq .L064
  sbrc r15, 0
  rjmp hold_sample
  rjmp render_sample
.L064:
  com r23
  breq music_tick
  rjmp render_sample
music_tick:
  /* Advance envelopes at ~73.24 Hz. Flags in envelope bytes encode attack, sustain and release. */
  inc r24
  sbrs r1, 7
  rjmp .L084
  mov r16, r1
  andi r16, 15
  cpi r16, 13
  brcc .L07e
  ldi r16, 3
  add r1, r16
  rjmp .L08e
.L07e:
  ldi r16, 143
  mov r1, r16
  rjmp .L08e
.L084:
  tst r1
  breq .L08e
  dec r1
  breq .L08e
  dec r1
.L08e:
  /* Piano and guitar use one shared envelope function with different decay masks. */
  mov r16, r19
  ldi r17, 3
  rcall update_envelope
  mov r19, r16
  mov r16, r20
  ldi r17, 7
  rcall update_envelope
  mov r20, r16
  /* Percussion decays on alternate ticks, retriggering in a four-beat rhythm. */
  sbrc r24, 0
  rjmp .L0a8
  cpi r21, 4
  brcc .L0a8
  inc r21
.L0a8:
  inc r25
  cpi r25, 27
  brcs .L0ba
  clr r25
  inc r29
  andi r29, 3
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
  breq note_rest
  movw r26, r30
  lsl r16
  ldi r30, lo8(note_steps)
  ldi r31, hi8(note_steps)
  add r30, r16
  adc r31, r0
  lpm r4, Z+
  lpm r5, Z+
  movw r30, r26
  clr r3
  ldi r16, 130
  mov r1, r16
  rjmp hold_sample
note_rest:
  rcall release_lead
  rjmp hold_sample
next_section:
  /* Follow the 15-entry playlist; repeated musical phrases point to one copy in Flash. */
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
  ldi r30, lo8(section_offsets)
  ldi r31, hi8(section_offsets)
  add r30, r16
  adc r31, r0
  lpm r16, Z
  ldi r30, lo8(melody_data)
  ldi r31, hi8(melody_data)
  add r30, r16
  adc r31, r0
  rjmp read_event
hold_sample:
  out 41, r18
  reti
update_envelope:
  /* Approximate piecewise linear envelopes via small integer increments, including note-off. */
  mov r0, r17
  mov r17, r16
  andi r17, 15
  breq .L198
  sbrs r16, 7
  rjmp .L192
  cpi r17, 12
  brcs .L188
  dec r16
  rjmp .L198
.L188:
  mov r17, r24
  and r17, r0
  brne .L198
  dec r16
  rjmp .L198
.L192:
  dec r16
  breq .L198
  dec r16
.L198:
  clr r0
  ret
eeprom_wave:
  /* Get a packed pair of 4-bit wave samples from EEPROM, with the documented read wait. */
  swap r17
  andi r17, 15
  lsr r17
  add r16, r17
  out 30, r16
  sbi 28, 0
  in r17, 29
  ret
scale_wave:
  /* Scale signed sample by a four-bit envelope using shift-add, with no MUL instruction. */
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
render_sample:
  /* Accumulate three pitch oscillators with independent phases and envelopes. */
  mov r26, r25
  clr r18
  add r2, r4
  adc r3, r5
  mov r25, r1
  mov r16, r5
  mov r17, r3
  rcall render_tone
  add r18, r17
  add r6, r8
  adc r7, r9
  mov r25, r19
  ori r25, 16
  mov r16, r9
  mov r17, r7
  rcall render_tone
  add r18, r17
  add r10, r12
  adc r11, r13
  mov r25, r20
  ori r25, 32
  mov r16, r13
  mov r17, r11
  rcall render_tone
  add r18, r17
  rjmp render_drum
render_tone:
  /* Choose register-dependent 16-step wavetable and blend attack to sustain over ~55 ms. */
  mov r0, r25
  andi r25, 15
  breq voice_silent
  mov r25, r0
  clr r0
  cpi r16, 4
  brcs .L214
  ldi r16, 8
  rjmp .L216
.L214:
  clr r16
.L216:
  sbrc r25, 4
  subi r16, 240
  sbrc r25, 5
  subi r16, 224
  mov r0, r17
  sbrc r17, 4
  ori r25, 64
  rcall eeprom_wave
  sbrc r25, 6
  swap r17
  andi r17, 15
  subi r17, 8
  mov r27, r17
  mov r16, r25
  andi r16, 48
  breq .L25c
  mov r16, r25
  andi r16, 15
  cpi r16, 12
  brcs .L25c
  ldi r16, 48
  sbrc r25, 5
  subi r16, 248
  mov r17, r0
  rcall eeprom_wave
  sbrc r25, 6
  swap r17
  andi r17, 15
  subi r17, 8
  sub r17, r27
  mov r16, r25
  andi r16, 15
  subi r16, 11
  rcall scale_wave
  add r27, r17
.L25c:
  mov r17, r27
  mov r16, r25
  andi r16, 15
  rcall scale_wave
  ret
voice_silent:
  clr r0
  clr r17
  ret
render_drum:
  /* Add bass drum or band-limited pseudo-random percussion; center the mix on PWM duty 128. */
  cpi r21, 4
  brcc write_pwm
  mov r17, r29
  andi r17, 3
  breq .L280
  cpi r17, 2
  breq .L298
  cpi r21, 2
  brcc write_pwm
  rjmp .L298
.L280:
  sbrc r15, 0
  rjmp .L28a
  ldi r17, 4
  sub r17, r21
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
  lsl r14
  brcc .L2a0
  ldi r17, 29
  eor r14, r17
.L2a0:
  mov r17, r14
  lsl r17
  lsl r17
  eor r17, r14
  andi r17, 63
  subi r17, 32
  asr r17
.L2ae:
  sbrc r21, 0
  asr r17
  sbrc r21, 1
  asr r17
  add r18, r17
write_pwm:
  /* Apply the single +128 offset only after bipolar mixing, write OCR0B, restore timebase. */
  subi r18, 128
  out 41, r18
  mov r25, r26
  reti

  /* The duration table, 16-bit DDS increments, chords, playlist and score. */
.include "score.inc"
