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
  ldi r16, 4
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
  ldi r18, 128
  out IO_OCR0B, r18
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
 * r18 carries the last *biased* PWM sample between interrupt calls.
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

  /* Both pitched-string releases share the same 8-tick clock gate.
   * This replaces two identical modulo-8 tests in the previous player.
   */
  mov r16, r24
  andi r16, 7
  brne pitched_decay_done
  cpi r20, 3
  brsh piano_decay
  inc r20                    /* pluck starts to decay right after attack */
piano_decay:
.if INSTR_KEYS == 1
  /* Bass piano strings sustain longer than treble strings. */
  mov r16, r9
  cpi r16, 2
  brsh piano_decay_regular
  sbrc r24, 3
  rjmp pitched_decay_done
piano_decay_regular:
.endif
  cpi r19, 3
  brsh pitched_decay_done
  inc r19
pitched_decay_done:

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
  /* Skip synthesis once per envelope tick; avoid rare >256-cycle paths. */
  rjmp hold_sample

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
 * Four independent voices are *bipolar*. The PWM offset is injected ONLY
 * after all voice contributions have been added, so the DC bias no longer
 * moves when piano/guitar/percussion envelopes change.
 *
 * The centered triangle is retained for the inexpensive violin generator
 * and kick. Piano/guitar waveforms are 4-bit phase tables extracted from
 * sample-based spectra. RCALL/RET and LPM fit the 256-cycle ISR budget.
 * Contributions are bounded: lead ~32, piano ~28, pluck ~28, drums ~16;
 * total stays within signed 8-bit range before adding the fixed +128.
 */

hold_sample:
  out IO_OCR0B, r18
  reti

/* Input: r17 = phase. Output: r17 = approximately -16..+16.
 * Folding creates a triangle; two arithmetic shifts give a signed quarter
 * amplitude. A +3-code bias compensates the downward rounding of ASR.
 * Shared across the harmonic generators (phase, 2*phase, etc.).
 */
fold_bipolar:
  sbrc r17, 7
  com r17
  subi r17, 61
  asr r17
  asr r17
  ret


/* Table-driven timbre experiment: actual measured sample spectral shapes,
 * phase locked for 3 melodic voices. Each is its own 16-bit DDS oscillator.
 * Violin preserved math kernel; piano and guitar 3 ROM bands each.
 * Every 16-sample wave has zero signed DC before PWM=128 is added.
 * Piano and guitar share a 4-bit packed PCM decode routine; violin uses
 * the older, more accurate in tests, mathematical oscillator.
 */
wave_lookup:
  /* Input r16 table offset in bytes, r17 8-bit phase; output r17 packed pair.
   * The caller selects the low or high nibble using its retained phase bit 4.
   * The saved score cursor in X is restored before the interrupt exits.
   */
  ldi r30, lo8(instrument_waves)
  ldi r31, hi8(instrument_waves)
  add r30, r16
  adc r31, r0
  mov r16, r17
  swap r16
  andi r16, 15
  lsr r16
  add r30, r16
  adc r31, r0
  lpm r17, Z
  ret

render_sample:
  movw r26, r30  /* score cursor restored at final mix */
  clr r18
  tst r5
  brne lead_present
  tst r4
  breq lead_finished
lead_present:
  /* Bowed string: a low saw partial + rounded fundamental + octave partial.
   * Preserves the existing low-register shape; octave becomes audible only
   * for the brighter mid/high register. Attack grows in two short steps.
   */
  add r2, r4
  adc r3, r5
  mov r18, r3
  swap r18
  andi r18, 15
  subi r18, 7
  mov r17, r3
  rcall fold_bipolar
.if INSTR_LEAD == 1
  asr r17
  asr r17
  asr r17
  add r18, r17
  mov r16, r5
  cpi r16, 2
  brlo violin_harmonic_done
  mov r17, r3
  lsl r17
  rcall fold_bipolar
  asr r17
  asr r17
  add r18, r17
violin_harmonic_done:
.else
  asr r17
  asr r17
  add r18, r17
.endif
  sbrc r1, 0
  asr r18
  sbrc r1, 1
  asr r18
  lsl r18
lead_finished:
  /* Piano: measured C3, D4 and A5 sustained spectra, with attack envelope.
   * Slower note decay than the earlier electronic triangle model.
   */
  add r6, r8
  adc r7, r9
  cpi r19, 4
  brsh piano_done
  mov r17, r9
  ldi r16, 0
  cpi r17, 2
  brlo piano_read
  ldi r16, 8
  cpi r17, 4
  brlo piano_read
  ldi r16, 16
piano_read:
  mov r17, r7
  rcall wave_lookup
  sbrc r7, 4
  swap r17
  andi r17, 15
  subi r17, 8
  lsl r17
  lsl r17
  /* Acoustic piano holds volume for first 2 decay stages; bass lasts longer. */
  sbrc r19, 1
  asr r17
  /* Reference A5 piano decays in ~146ms; strengthen damping in the upper
   * register without touching the more slowly decaying bass strings.
   * Release cannot be exact without separate MIDI note-off events.
   */
  mov r16, r9
  cpi r16, 4
  brlo piano_bass_env
  sbrc r19, 0
  asr r17
  sbrc r19, 1
  asr r17
  rjmp piano_env_done
piano_bass_env:
  /* Low C3 is ~0.65 at 200ms and ~0.25 by 500ms; its second
   * and fourth envelope stages require another 6dB attenuation.
   */
  cpi r16, 2
  brsh piano_env_done
  sbrc r19, 0
  asr r17
piano_env_done:
  add r18, r17
piano_done:
  /* Pluck: guitar G2, D4 and A4 spectra with decaying sustain. */
  add r10, r12
  adc r11, r13
  cpi r20, 4
  brsh pluck_done
  mov r17, r13
  ldi r16, 24
  cpi r17, 2
  brlo pluck_read
  ldi r16, 32
  cpi r17, 3
  brlo pluck_read
  ldi r16, 40
pluck_read:
  /* Only the low guitar register gets a second transient spectrum.
   * Two extra clauses cost less than a general-purpose patch oscillator.
   */
  cpi r16, 24
  brne pluck_steady
  tst r20
  brne pluck_steady
  ldi r16, 48
pluck_steady:
  mov r17, r11
  rcall wave_lookup
  sbrc r11, 4
  swap r17
  andi r17, 15
  subi r17, 8
  lsl r17
  lsl r17
  /* Plucked guitar decays much more slowly than the earlier synth. */
  sbrc r20, 1
  asr r17
  add r18, r17
pluck_done:
  movw r30, r26
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
  cpi r21, 2
  brsh no_drum_audio
  rjmp snare_noise
kick_wave:
  /* Kick: transient drops in frequency. Reuse the centered triangle fold. */
  sbrc r15, 0
  rjmp kick_not_advanced
  ldi r17, 4
  sub r17, r21
  add r14, r17
kick_not_advanced:
  mov r17, r14
  rcall fold_bipolar
  rjmp fade_percussion
.else
  cpi r21, 2
  brsh no_drum_audio
.endif
snare_noise:
  /* Single 8-bit LFSR shared by snare and hat; signed noise has ~zero DC. */
  lsl r14
  brcc noise_no_xor
  ldi r17, 0x1d
  eor r14, r17
noise_no_xor:
  mov r17, r14
  lsl r17
  lsl r17
  eor r17, r14
  andi r17, 0x3f
  subi r17, 32
  asr r17
fade_percussion:
  sbrc r21, 0
  asr r17
  sbrc r21, 1
  asr r17
  add r18, r17
no_drum_audio:
.endif
  subi r18, -128           /* one fixed PWM midpoint regardless of polyphony */
  out IO_OCR0B, r18
  reti

/* Built-in Python converter generates just the tables/method switches used. */

.include "score.inc"
.include "waveforms.inc"
