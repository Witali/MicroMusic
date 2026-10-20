/*
 * Four-voice ATtiny13A musical player.
 * GNU AVR assembler syntax; compatible with avr-as and LLVM AVR IAS.
 * CPU: internal 9.6 MHz oscillator, CKDIV8 disabled in software.
 * PWM: Timer0 Fast PWM, TOP=255, prescaler=1, OC0B/PB1 at 37.5 kHz.
 * Channel 0: bowed/smooth lead, channel 1: piano, channel 2: plucked
 * guitar/bass, channel 3: software kick/snare/hat. No floating point.
 *
 * IMPORTANT: main code only spins; interrupt is the sole owner of r0-r31.
 * Therefore there is NO register spilling / saving in the ISR. Never put
 * foreground code that edits these registers without adding preservation.
 */

.section .text
.set F_CPU, 9600000
.include "config.inc"
.global __vectors

/* AVR register map comes from ATtiny13A DS40002307A, register summary. */
.set IO_DDRB,     0x17
.set IO_OCR0B,    0x29
.set IO_TCCR0A,   0x2f
.set IO_TCCR0B,   0x33
.set IO_TIMSK0,   0x39
.set IO_CLKPR,    0x26
.set IO_SPL,      0x3d
.set RAMEND,      0x9f

/* Tiny13 vectors contain one AVR instruction word each. */
.org 0
__vectors:
  rjmp reset
.org 6                         /* TIM0_OVF vector: word address 0x0003 */
  rjmp audio_irq
.org 20                        /* Keep space for the 10 interrupt vectors. */
reset:
  cli
  ldi r16, RAMEND
  out IO_SPL, r16

  /* CKDIV8 is programmed on factory chips: unlock and cancel /8 in 4 cycles. */
  ldi r16, 0x80
  out IO_CLKPR, r16
  clr r16
  out IO_CLKPR, r16

  /* The register file (addresses 0x02..0x19) doubles as our synthesizer RAM. */
  clr r0
  clr r1
  ldi r30, 2
  clr r31
  clr r16
clear_registers:
  st Z+, r16
  cpi r30, 26
  brne clear_registers

  /* Four musical voices start silent; first score event loads their pitches. */
  ldi r16, 4
  mov r21, r16                 /* percussion off until first rhythm trigger */
  ldi r16, 3
  mov r19, r16                 /* no piano until first chord event */
  mov r20, r16                 /* no guitar until first chord event */
  ldi r16, 1
  mov r22, r16                 /* schedule first note after one music tick */
  mov r28, r16                 /* playlist[0] (intro) is entered immediately */
  ldi r30, lo8(section_intro)
  ldi r31, hi8(section_intro)
  ldi r16, 0xa7
  mov r14, r16                 /* nonzero seed for 8-bit noise LFSR */

  /* Hardware PWM generates every edge independently of CPU instruction timing. */
  sbi IO_DDRB, 1               /* PB1 = OC0B audio output */
  ldi r16, 112
  out IO_OCR0B, r16
  ldi r16, 0x23                /* COM0B1=1, WGM01=1, WGM00=1: Fast PWM */
  out IO_TCCR0A, r16
  ldi r16, 1                   /* CS00=1 => clock /1 */
  out IO_TCCR0B, r16
  ldi r16, 2                   /* TOIE0=1 => overflow interrupt */
  out IO_TIMSK0, r16
  sei
idle:
  rjmp idle

/*
 * Each ISR must complete within 256 CPU cycles, including the rare score
 * decoder path. The output goes to the PWM compare register; the timer's
 * double buffer commits the new duty at the next PWM period boundary.
 *
 * r2:r3   lead phase;    r4:r5   lead 16-bit step
 * r6:r7   keys phase;    r8:r9   keys 16-bit step
 * r10:r11 pluck phase;   r12:r13 pluck step
 * r14     noise / kick oscillator state
 * r15,r23 divided music clock; r22 length left, r24 global tick
 * r19,r20 piano/pluck decay; r21 drum decay
 * r25,r29 rhythm subdivision/beat; r28 playlist section index
 * r30:r31 FLASH address of the next encoded music event
 * r0      permanently zero; r1 lead attack stage
 * r16,r17,r18 scratch; r26:r27 saves Z during table lookup.
 */
audio_irq:
  inc r15
  breq sample_divider_low_overflow
  rjmp render_sample
sample_divider_low_overflow:
  ldi r16, 1
  eor r23, r16
  breq music_tick
  rjmp render_sample          /* one sequencer tick per 512 PWM periods */

music_tick:
  inc r24                      /* drives very cheap envelope clocks */
  tst r1
  breq lead_attack_done
  dec r1
lead_attack_done:

  /* Piano fades slowly, guitar fades more quickly after every chord attack. */
  mov r16, r24
  andi r16, 7
  brne piano_decay_done
.if INSTR_KEYS == 1
  /* The bass piano strings ring longer: every 16 ticks below ~293 Hz,
   * but every 8 ticks above it. No per-sample envelope multiplication.
   */
  mov r16, r9
  cpi r16, 2
  brsh piano_decay_regular
  sbrc r24, 3
  rjmp piano_decay_done
piano_decay_regular:
.endif
  cpi r19, 3
  brsh piano_decay_done
  inc r19
piano_decay_done:
  mov r16, r24
  andi r16, 7
  brne pluck_decay_done
  cpi r20, 3
  brsh pluck_decay_done
  inc r20
pluck_decay_done:

  /* A 4th channel is a compact rhythmic oscillator/noise generator. */
.if INSTR_DRUMS != 0
  mov r16, r24
  andi r16, 1
  brne drum_decay_done
  cpi r21, 4
  brsh drum_decay_done
  inc r21                     /* kick/snare transient is about 0.11 s */
drum_decay_done:
  inc r25
  cpi r25, 27
  brlo drum_trigger_done
  clr r25
  inc r29
  andi r29, 3
  clr r21                     /* next hit; odd=kick, even=noise */
  ldi r16, 0xa7
  mov r14, r16                 /* deterministic attack each hit */
drum_trigger_done:
.endif

  dec r22
  breq read_event
  rjmp render_sample

/*
 * Music byte: bits 7:3 = pitch index (0..13); bits 2:0 = duration (0..6).
 * 0xE0..0xEF changes harmony without consuming time; 0xFF ends a section.
 * A 16-byte playlist references only six distinct patterns, so repeated
 * sections cost one byte each, never copies of all their notes.
 */
read_event:
  lpm r16, Z+
  cpi r16, 0xff
  breq next_section
  cpi r16, 0xe0
  brlo melodic_event

harmony_event:
  movw r26, r30                /* LPM needs Z; hold score cursor in X */
  andi r16, 0x0f
  lsl r16
  lsl r16                     /* four step-table bytes per chord */
  ldi r30, lo8(chord_steps)
  ldi r31, hi8(chord_steps)
  add r30, r16
  adc r31, r0
  lpm r8, Z+
  lpm r9, Z+
  lpm r12, Z+
  lpm r13, Z+
  clr r6
  clr r7
  clr r10
  clr r11
  clr r19
  clr r20                     /* key/pluck velocity attacks */
  movw r30, r26
  rjmp read_event              /* chord has no duration */

melodic_event:
  /* Decode a duration through a 7-byte table; no multiplication/division. */
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
  lsr r16                     /* 5-bit pitch index */
  cpi r16, REST_INDEX         /* dynamically generated rest code */
  breq note_rest

  /* 16-bit DDS step retains pitch accuracy even for low guitar notes. */
  movw r26, r30
  lsl r16                     /* each note lookup occupies two bytes */
  ldi r30, lo8(note_steps)
  ldi r31, hi8(note_steps)
  add r30, r16
  adc r31, r0
  lpm r4, Z+
  lpm r5, Z+
  movw r30, r26
  clr r2
  clr r3                      /* restart melody oscillator at note-on */
  ldi r16, 3
  mov r1, r16                 /* roughly 40 ms violin fade-in */
  /* Reuse the previous duty for this single PWM period. Music events are
   * rare; deferring sample synthesis by 26.7 us protects the ISR budget.
   */
  rjmp hold_sample

note_rest:
  clr r2
  clr r3
  clr r4
  clr r5
  clr r1
  rjmp hold_sample

next_section:
  /* At section end read only the playlist index, then a one-byte offset. */
  ldi r30, lo8(playlist)
  ldi r31, hi8(playlist)
  add r30, r28
  adc r31, r0
  lpm r16, Z
  inc r28
  cpi r16, 0xff
  brne section_found
  clr r28
  rjmp next_section
section_found:
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

/*
 * Four simultaneous software oscillators, all mixed without AVR MUL.
 * Saw + triangle lead approximates bowed string harmonics; triangle piano
 * is rounded/softer; saw guitar has rapid attenuation. This is intentionally
 * a tiny timbral approximation, not a sample-accurate acoustic model.
 */
/* On a score event the previous PWM duty is repeated once. This prevents
 * the very occasional long score-decoder path from stealing sample time.
 * Still write OCR0B so both hardware and the HEX emulator see each sample.
 */
hold_sample:
  out IO_OCR0B, r18
  reti
render_sample:
  add r2, r4
  adc r3, r5
  mov r18, r3
.if INSTR_LEAD == 1
  mov r16, r3
  sbrc r16, 7
  com r16                     /* triangle component of bowed tone */
  lsr r16
  lsr r16
  lsr r16
  lsr r18
  lsr r18
  lsr r18
  lsr r18
  add r18, r16                /* lead roughly 0..30 */
.else
  sbrc r18, 7
  com r18                     /* smoother flute-like triangle */
  lsr r18
  lsr r18
.endif
  sbrc r1, 0
  lsr r18
  sbrc r1, 1
  lsr r18                     /* two-step bow attack */
  lsl r18                     /* lead is loudest part of arrangement */

  add r6, r8
  adc r7, r9
  mov r16, r7
.if INSTR_KEYS == 1
  cpi r19, 3                 /* piano damper: stop the decayed note */
  brsh keys_silent
.endif
  sbrc r16, 7
  com r16
  lsr r16
  lsr r16                     /* 5-bit rounded piano wave */
.if INSTR_KEYS == 1
  /* Piano register tracking (step high byte is a cheap pitch proxy):
   * low (<~293 Hz): second harmonic survives the first decay stage;
   * mid (~293..439 Hz): second harmonic only in the hammer attack;
   * high (>=~440 Hz): triangle fundamental, no extra harmonic.
   * The upper registers must have fewer harmonics, as on real piano.
   */
  mov r17, r9
  cpi r17, 3
  brsh keys_harmonic_done
  tst r19
  breq piano_harmonic
  cpi r17, 2
  brsh keys_harmonic_done
  cpi r19, 2
  brsh keys_harmonic_done
piano_harmonic:
  mov r17, r7
  lsl r17
  sbrc r17, 7
  com r17
  lsr r17
  lsr r17
  lsr r17
  /* The second harmonic of low notes softens before disappearing. */
  tst r19
  breq piano_harmonic_add
  lsr r17
piano_harmonic_add:
  add r16, r17
keys_harmonic_done:
  sbrc r19, 0
  lsr r16
  sbrc r19, 1
  lsr r16                     /* dying piano string */
.endif
  add r18, r16
keys_silent:

  add r10, r12
  adc r11, r13
  mov r16, r11
.if INSTR_PLUCK == 1
  cpi r20, 3                 /* guitar: mute after short release */
  brsh pluck_silent
  /* Plucked string: soft triangle tail + sharp saw attack transient. */
  mov r17, r16
  sbrc r16, 7
  com r16
  lsr r16
  lsr r16
  lsr r16
  lsl r16
  /* Register-aware pluck: up to ~293 Hz use a stronger saw transient;
   * from ~293 to ~586 Hz use half strength; above ~586 Hz suppress it.
   * Even partials vanish as this attack ages, as for a plucked string.
   */
  tst r20
  brne guitar_attack_done
  mov r26, r13
  cpi r26, 4
  brsh guitar_attack_done
  lsr r17
  lsr r17
  lsr r17
  lsr r17
  cpi r26, 2
  brlo guitar_harmonic_add
  lsr r17
 guitar_harmonic_add:
  add r16, r17
 guitar_attack_done:
.else
  lsr r16
  lsr r16
  lsr r16                     /* simple saw for bass */
.endif
.if INSTR_PLUCK == 1
  sbrc r20, 0
  lsr r16
  sbrc r20, 1
  lsr r16                     /* much faster pluck decay */
.endif
  add r18, r16
pluck_silent:

.if INSTR_DRUMS != 0
  cpi r21, 4
  brsh no_drum_audio
.if INSTR_DRUMS == 2
  /* Four beats share one percussion voice: kick, hat, snare, hat. */
  mov r17, r29
  andi r17, 3
  breq kick_wave
  cpi r17, 2
  breq snare_noise
  cpi r21, 2                 /* closed hi-hat: short noise burst */
  brsh no_drum_audio
  rjmp snare_noise
kick_wave:
  /* Kick: 8-bit triangle, frequency falls during the transient. */
  sbrc r15, 0
  rjmp kick_not_advanced
  ldi r17, 4
  sub r17, r21
  add r14, r17
kick_not_advanced:
  mov r16, r14
  sbrc r16, 7
  com r16
  lsr r16
  rjmp fade_percussion
.else
  cpi r21, 2                 /* hat-only build: closed hi-hat decay */
  brsh no_drum_audio
.endif
snare_noise:
  /* 8-bit LFSR; no sample table and no full-period multiply. */
  lsl r14
  brcc noise_no_xor
  ldi r17, 0x1d
  eor r14, r17
noise_no_xor:
  mov r16, r14
  lsl r16
  lsl r16
  eor r16, r14              /* metallic edge: cross-mix LFSR taps */
  andi r16, 0x3f
fade_percussion:
  sbrc r21, 0
  lsr r16
  sbrc r21, 1
  lsr r16
  add r18, r16
no_drum_audio:
.endif
  subi r18, -56                /* DC bias; peak stays below OCR0B=255 */
  out IO_OCR0B, r18
  reti

/* Built-in Python converter generates just the tables/method switches used. */
.include "score.inc"
