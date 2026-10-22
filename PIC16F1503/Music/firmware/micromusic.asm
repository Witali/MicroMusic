; MicroMusic PIC16F1503 -- true enhanced-midrange PIC machine-code synthesizer.
; Algorithm adapted from Witali/MicroMusic, rhythmic / Lumiere arrangement.
; Audio: RA2/PWM3, internal HFINTOSC 16 MHz, Timer2 62.5 kHz,
; PWM duty interrupt 12.5 kHz (Timer2 postscale /5).
; Three measured, time-dependent tonal wavetable voices plus a noise/drum voice.
; Music events and waveforms are read from 14-bit program Flash through FSR1.
;
; Comments explain sound generation, score decoding and synchronization; the
; individual MOV instructions are intentionally not commented line-by-line.
;
; GPASM/MPASM-like syntax. Locally build with tools/assemble_pic.py, which
; encodes exactly the Microchip DS40001607D enhanced PIC16F1 instruction set.
PROCESSOR 16F1503

; Device SFRs are directly mapped within bank 0 unless specified otherwise.
STATUS      EQU 0x03
FSR0L       EQU 0x04
FSR0H       EQU 0x05
FSR1L       EQU 0x06
FSR1H       EQU 0x07
INTCON      EQU 0x0B
PIR1        EQU 0x11
TMR2        EQU 0x1A
PR2         EQU 0x1B
T2CON       EQU 0x1C
TRISA       EQU 0x0C  ; Bank 1
OSCCON      EQU 0x19  ; Bank 1
PIE1        EQU 0x11  ; Bank 1
ANSELA      EQU 0x0C  ; Bank 3
PWM3DCL     EQU 0x17  ; Bank 12
PWM3DCH     EQU 0x18  ; Bank 12
PWM3CON     EQU 0x19  ; Bank 12

; GPR allocated entirely in Bank 0 (0x20..0x6F). FSR and ISR shadows are
; restored automatically by RETFIE (see datasheet Section 7.5).
V0          EQU 0x20 ; phaseL,H; stepL,H; envelope; age; decay; frame
V1          EQU 0x28
V2          EQU 0x30
MIX         EQU 0x38
DIV64       EQU 0x39
GRID_L      EQU 0x3A
GRID_H      EQU 0x3B
NOTE_LEFT   EQU 0x3C
SCORE_OFF   EQU 0x3D
SECTION     EQU 0x3E
BEAT        EQU 0x3F
DRUM_ENV    EQU 0x40
DRUM_MODE   EQU 0x41
NOISE       EQU 0x42
DRUM_PHASE  EQU 0x43
READ_IDX    EQU 0x44
WRITE_IDX   EQU 0x45
NEXT_IDX    EQU 0x46
TOKEN       EQU 0x47
IDX         EQU 0x48
WAVE        EQU 0x49
GAIN        EQU 0x4A
ACC         EQU 0x4B
BASE        EQU 0x4C
ENV_TICKS   EQU 0x4D
TMP         EQU 0x4E
TMP2        EQU 0x4F
QUEUE       EQU 0x50 ; 16 samples (0x50..0x5F)
UNDERRUN    EQU 0x60 ; diagnostics counter
DRUM_LAST   EQU 0x61 ; last reconstructed percussion sample
; ISR temporaries use common RAM (0x70..0x7F), independent of BSR.
IRQ_SAMPLE  EQU 0x70
IRQ_LOW     EQU 0x71
IRQ_HIGH    EQU 0x72

ORG 0x0000
    GOTO reset
ORG 0x0004
    GOTO pwm_irq

pwm_irq:
    ; The Timer2 interrupt consumes a prepared PWM byte. The producer only
    ; increments WRITE_IDX once the queue slot has been fully written.
    MOVLB 0
    BCF PIR1,1
    MOVF READ_IDX,W
    XORWF WRITE_IDX,W
    BTFSS STATUS,2
    BRA irq_pop
    INCF UNDERRUN,F
    RETFIE
irq_pop:
    MOVLW QUEUE
    ADDWF READ_IDX,W
    MOVWF FSR0L
    CLRF FSR0H
    MOVIW 0[FSR0]
    MOVWF IRQ_SAMPLE
    INCF READ_IDX,F
    MOVLW 0x0F
    ANDWF READ_IDX,F

    ; PWM3 duty is a 10-bit quantity even when PR2=63. Writing only DCH
    ; would lose the least significant TWO bits of our 8-bit sample.
    MOVF IRQ_SAMPLE,W
    ANDLW 3
    MOVWF IRQ_LOW
    SWAPF IRQ_LOW,F
    LSLF IRQ_LOW,F
    LSLF IRQ_LOW,F
    MOVF IRQ_SAMPLE,W
    MOVWF IRQ_HIGH
    LSRF IRQ_HIGH,F
    LSRF IRQ_HIGH,F
    MOVLB 12
    MOVF IRQ_LOW,W
    MOVWF PWM3DCL
    MOVF IRQ_HIGH,W
    MOVWF PWM3DCH
    RETFIE

reset:
    ; Run from factory-calibrated HFINTOSC at 16 MHz and route PWM3 to RA2.
    ; The configuration word must select INTOSC and disable WDT/LVP.
    MOVLB 1
    MOVLW 0x7A
    MOVWF OSCCON
    BCF TRISA,2
    MOVLB 3
    BCF ANSELA,2

    ; Clear all programme state and the ring buffer; this also keeps the
    ; initial PWM at exactly the midpoint, 128, while the producer warms up.
    MOVLB 0
    MOVLW V0
    MOVWF FSR0L
    CLRF FSR0H
reset_clear:
    CLRW
    MOVWI 0[FSR0]
    INCF FSR0L,F
    MOVLW 0x60
    XORWF FSR0L,W
    BTFSS STATUS,2
    BRA reset_clear
    MOVLW QUEUE
    MOVWF FSR0L
fill_queue:
    MOVLW 128
    MOVWI 0[FSR0]
    INCF FSR0L,F
    MOVLW 0x60
    XORWF FSR0L,W
    BTFSS STATUS,2
    BRA fill_queue
    CLRF UNDERRUN
    CLRF DRUM_LAST
    MOVLW 15
    MOVWF WRITE_IDX  ; 15 initial, centered samples, no underrun during startup.
    MOVLW 0xA7
    MOVWF NOISE
    MOVLW 1
    MOVWF NOTE_LEFT
    CALL read_event

    ; Timer2 PWM carrier=Fosc/[4*(PR2+1)]=62500 Hz. IRQ /5=12500 Hz.
    MOVLW 63
    MOVWF PR2
    CLRF TMR2
    MOVLB 12
    MOVLW 32
    MOVWF PWM3DCH
    CLRF PWM3DCL
    MOVLW 0xC0
    MOVWF PWM3CON
    MOVLB 0
    MOVLW 0x24
    MOVWF T2CON
    BCF PIR1,1
    MOVLB 1
    BSF PIE1,1
    MOVLB 0
    BSF INTCON,6
    BSF INTCON,7

producer:
    ; Ring has one unused slot to distinguish full from empty. Main loop
    ; computes ONE complete 4-voice sample before publishing its index.
    MOVF WRITE_IDX,W
    ADDLW 1
    ANDLW 0x0F
    MOVWF NEXT_IDX
    XORWF READ_IDX,W
    BTFSC STATUS,2
    BRA producer
    CALL render_sample
    MOVWF TMP2
    MOVLW QUEUE
    ADDWF WRITE_IDX,W
    MOVWF FSR0L
    CLRF FSR0H
    MOVF TMP2,W
    MOVWI 0[FSR0]
    MOVF NEXT_IDX,W
    MOVWF WRITE_IDX
    BRA producer

render_sample:
    ; A 16-bit DDS never resets its phase on retrigger or note-off. Each
    ; voice uses measured time-varying harmonics from the compact Flash bank.
    INCF DIV64,F
    MOVLW 50
    XORWF DIV64,W
    BTFSC STATUS,2
    CALL music_tick
    MOVLW 128
    MOVWF MIX

    MOVLW V0
    MOVWF FSR0L
    MOVLW 0x00
    MOVWF BASE
    CALL render_voice
    MOVLW V1
    MOVWF FSR0L
    MOVLW 0x10
    MOVWF BASE
    CALL render_voice
    MOVLW V2
    MOVWF FSR0L
    MOVLW 0x50
    MOVWF BASE
    CALL render_voice
    CALL render_drum
    MOVF MIX,W
    RETURN

render_voice:
    ; Phase += step, with carry. The phase top nibble indexes a 16-sample
    ; wavetable, its next lower bit selects the packed low/high 4-bit value.
    MOVIW 0[FSR0]
    MOVWF WAVE
    MOVIW 2[FSR0]
    ADDWF WAVE,F
    MOVF WAVE,W
    MOVWI 0[FSR0]
    MOVIW 1[FSR0]
    MOVWF WAVE
    MOVIW 3[FSR0]
    ADDWFC WAVE,F
    MOVF WAVE,W
    MOVWI 1[FSR0]
    MOVIW 4[FSR0]
    ANDLW 0x0F
    BTFSC STATUS,2
    RETURN
    MOVWF GAIN
    SWAPF WAVE,W
    ANDLW 15
    MOVWF IDX
    LSRF IDX,F

    ; Piano and nylon guitar have four successive spectral frames (attack
    ; through sustain); violin stays on a single register-dependent waveform.
    MOVF BASE,W
    BTFSC STATUS,2
    BRA register_choice
    MOVIW 7[FSR0]
    MOVWF TMP
    SWAPF TMP,W
    ADDWF IDX,F
register_choice:
    MOVIW 3[FSR0]
    MOVWF TMP
    MOVLW 8
    SUBWF TMP,W
    BTFSC STATUS,0
    BSF IDX,3
    MOVF BASE,W
    ADDWF IDX,W
    MOVWF FSR1L
    MOVLW 0x86 ; wave_table placed at Flash word address 0x0600.
    MOVWF FSR1H
    MOVIW 0[FSR1]
    MOVWF WAVE
    ; The voice's phase-high bit4 selects the upper packed nibble.
    MOVIW 1[FSR0]
    ANDLW 0x10
    BTFSS STATUS,2
    SWAPF WAVE,F
    MOVF WAVE,W
    ANDLW 15
    ADDLW 0xF8
    MOVWF WAVE
    CALL scale_wave
    MOVF ACC,W
    ADDWF MIX,F
    RETURN

scale_wave:
    ; Lookup the exact signed 4-bit waveform * 4-bit envelope >> 2.
    ; The host generator precomputes all 256 products, taking no PIC
    ; multiplications, temporary 16-bit sums or floating-point operations.
    MOVF WAVE,W
    ADDLW 8
    MOVWF TMP
    SWAPF TMP,W
    IORWF GAIN,W
    MOVWF FSR1L
    MOVLW 0x84 ; gain_table is at Flash word 0x0400.
    MOVWF FSR1H
    MOVIW 0[FSR1]
    MOVWF ACC
    RETURN

render_drum:
    ; Drum noise is regenerated every FOURTH sample. Its previous value
    ; is held between output steps, preserving the 12.5 kHz audio update rate
    ; while freeing cycles for the piano/guitar wavetable lookup.
    MOVF DIV64,W
    ANDLW 3
    BTFSS STATUS,2
    BRA drum_cached
    ; An 8-bit LFSR supplies snare/hat noise. Kick uses a swept low-pitch
    ; ramp. Both share the same scaling routine with all tonal instruments.
    MOVF DRUM_ENV,F
    BTFSC STATUS,2
    BRA drum_zero
    LSLF NOISE,F
    BTFSC STATUS,0
    BRA noise_feedback
noise_ready:
    MOVF DRUM_MODE,F
    BTFSC STATUS,2
    BRA kick_sound
    MOVF NOISE,W
    ANDLW 31
    ADDLW 240
    MOVWF WAVE
    MOVF DRUM_MODE,W
    XORLW 2
    BTFSC STATUS,2
    ASRF WAVE,F
    BRA drum_gain
noise_feedback:
    MOVLW 0x1D
    XORWF NOISE,F
    BRA noise_ready
kick_sound:
    MOVF DRUM_ENV,W
    ADDLW 6
    ADDWF DRUM_PHASE,F
    MOVF DRUM_PHASE,W
    ANDLW 31
    ADDLW 240
    MOVWF WAVE
drum_gain:
    MOVF DRUM_ENV,W
    MOVWF GAIN
    CALL scale_wave
    ASRF ACC,F  ; Softer percussion mix /2 for headroom.
    MOVF ACC,W
    MOVWF DRUM_LAST
    BRA drum_cached
drum_zero:
    CLRF DRUM_LAST
drum_cached:
    MOVF DRUM_LAST,W
    ADDWF MIX,F
    RETURN

music_tick:
    ; Compute expensive score/envelope events only once every 50 output
    ; samples. The ring buffer absorbs occasional long music events.
    CLRF DIV64
    INCF ENV_TICKS,F
    MOVLW V0
    MOVWF FSR0L
    CALL update_bow
    MOVLW V1
    MOVWF FSR0L
    MOVLW 12
    MOVWF BASE
    CALL update_pluck
    MOVLW V2
    MOVWF FSR0L
    MOVLW 8
    MOVWF BASE
    CALL update_pluck
    MOVF DRUM_ENV,F
    BTFSC STATUS,2
    BRA grid_tick
    DECF DRUM_ENV,F
grid_tick:
    ; Fractional sixteenth-note grid, derived from the original 80 BPM
    ; score. A carry advances the rhythm step, not the audio timer.
    MOVLW 0x76
    ADDWF GRID_L,F
    MOVLW 0x05
    ADDWFC GRID_H,F
    BTFSS STATUS,0
    RETURN
    CALL step_grid
    RETURN

update_bow:
    ; Bowed violin: gentle (~200 ms) attack to level 14 and a controlled
    ; note-off release. Avoid an abrupt phase reset at the end of a note.
    MOVIW 4[FSR0]
    MOVWF TMP
    ANDLW 15
    MOVWF GAIN
    BTFSC STATUS,2
    RETURN
    BTFSC TMP,7
    BRA do_release
    INCF ENV_TICKS,W
    ANDLW 3
    BTFSS STATUS,2
    RETURN
    MOVLW 14
    SUBWF GAIN,W
    BTFSC STATUS,0
    RETURN
    INCF TMP,F
    MOVF TMP,W
    MOVWI 4[FSR0]
    RETURN

update_pluck:
    ; Piano/guitar have a moving spectral frame during the transient.
    ; Higher keys decay faster, and note-off triggers a short release.
    MOVIW 4[FSR0]
    MOVWF TMP
    ANDLW 15
    MOVWF GAIN
    BTFSC STATUS,2
    RETURN
    BTFSC TMP,7
    BRA do_release
    MOVIW 5[FSR0]
    ADDLW 1
    MOVWI 5[FSR0]
    ANDLW 7
    BTFSS STATUS,2
    BRA pluck_decay
    MOVIW 7[FSR0]
    MOVWF TMP2
    MOVLW 3
    SUBWF TMP2,W
    BTFSC STATUS,0
    BRA pluck_decay
    INCF TMP2,F
    MOVF TMP2,W
    MOVWI 7[FSR0]
pluck_decay:
    MOVIW 6[FSR0]
    ADDLW 1
    MOVWI 6[FSR0]
    MOVWF TMP2
    MOVIW 3[FSR0]
    MOVWF IDX
    MOVLW 8
    SUBWF IDX,W
    BTFSC STATUS,0
    BRA decay_fast
    MOVF BASE,W
    ADDLW 5
    BRA decay_compare
decay_fast:
    MOVF BASE,W
    ; Lower decay counts make high notes slightly shorter.
decay_compare:
    SUBWF TMP2,W
    BTFSS STATUS,0
    RETURN
    CLRW
    MOVWI 6[FSR0]
    DECF TMP,F
    MOVF TMP,W
    MOVWI 4[FSR0]
    RETURN

do_release:
    ; Both melodic and harmonic note-offs are independent voice states.
    ; The 4-bit envelope goes down every second 244 Hz control tick.
    BTFSS ENV_TICKS,0
    RETURN
    MOVF GAIN,W
    ADDLW 0xFF
    MOVWF GAIN
    MOVF GAIN,W
    IORLW 0x80
    MOVWI 4[FSR0]
    RETURN

step_grid:
    ; Every second grid position has a kick/snare/closed-hat trigger.
    BTFSC BEAT,0
    BRA grid_no_drum
    MOVLW 15
    MOVWF DRUM_ENV
    MOVLW 0
    MOVWF DRUM_MODE
    MOVF BEAT,F
    BTFSC STATUS,2
    BRA grid_no_drum
    MOVLW 1
    MOVWF DRUM_MODE
    MOVLW 4
    XORWF BEAT,W
    BTFSS STATUS,2
    MOVLW 2
    MOVWF DRUM_MODE
grid_no_drum:
    INCF BEAT,F
    MOVLW 7
    ANDWF BEAT,F
    MOVF NOTE_LEFT,F
    BTFSC STATUS,2
    RETURN
    DECF NOTE_LEFT,F
    BTFSC STATUS,2
    CALL read_event
    RETURN

read_event:
    ; F0..FE release selected voices (bit mask); FF means next repeated
    ; section; E0..EF update accompaniment; low events encode lead pitch
    ; and duration in 5+3 bits. Iterate over immediate controls.
    MOVLW 0x87
    MOVWF FSR1H
    MOVF SCORE_OFF,W
    MOVWF FSR1L
    MOVIW 0[FSR1]
    MOVWF TOKEN
    INCF SCORE_OFF,F
    MOVLW 255
    XORWF TOKEN,W
    BTFSC STATUS,2
    BRA next_section
    MOVLW 240
    SUBWF TOKEN,W
    BTFSC STATUS,0
    BRA event_note_off
    MOVLW 224
    SUBWF TOKEN,W
    BTFSC STATUS,0
    BRA event_chord
    BRA event_lead

next_section:
    INCF SECTION,F
    MOVLW 15
    XORWF SECTION,W
    BTFSC STATUS,2
    CLRF SECTION
    MOVF SECTION,W
    ADDLW 0xC5 ; playlist_table = 0x06C5
    MOVWF FSR1L
    MOVLW 0x86
    MOVWF FSR1H
    MOVIW 0[FSR1]
    MOVWF SCORE_OFF
    BRA read_event

event_note_off:
    BTFSC TOKEN,0
    BSF V0+4,7
    BTFSC TOKEN,1
    BSF V1+4,7
    BTFSC TOKEN,2
    BSF V2+4,7
    BTFSC TOKEN,3
    CLRF DRUM_ENV
    BRA read_event

event_chord:
    MOVF TOKEN,W
    ANDLW 0x0F
    MOVWF IDX
    LSLF IDX,F
    LSLF IDX,F
    MOVF IDX,W
    ADDLW 0xAA ; chord_table starts at 0x06AA
    MOVWF FSR1L
    MOVLW 0x86
    MOVWF FSR1H
    MOVIW 0[FSR1]
    MOVWF V1+2
    MOVIW 1[FSR1]
    MOVWF V1+3
    MOVIW 2[FSR1]
    MOVWF V2+2
    MOVIW 3[FSR1]
    MOVWF V2+3
    MOVLW 15
    MOVWF V1+4
    MOVWF V2+4
    CLRF V1+5
    CLRF V2+5
    CLRF V1+6
    CLRF V2+6
    CLRF V1+7
    CLRF V2+7
    BRA read_event

event_lead:
    MOVF TOKEN,W
    ANDLW 7
    ADDLW 0xBE ; duration_table 0x06BE
    MOVWF FSR1L
    MOVLW 0x86
    MOVWF FSR1H
    MOVIW 0[FSR1]
    MOVWF NOTE_LEFT
    ; Decode note index while preserving token for note length.
    MOVF TOKEN,W
    MOVWF IDX
    LSRF IDX,F
    LSRF IDX,F
    LSRF IDX,F
    MOVLW 13
    XORWF IDX,W
    BTFSC STATUS,2
    BRA lead_rest
    MOVLW 14
    XORWF IDX,W
    BTFSC STATUS,2
    RETURN
    LSLF IDX,F
    MOVF IDX,W
    ADDLW 0x90 ; note_table 0x0690
    MOVWF FSR1L
    MOVIW 0[FSR1]
    MOVWF V0+2
    MOVIW 1[FSR1]
    MOVWF V0+3
    MOVLW 0x41 ; flag bit6 attack, amplitude1 for bowed violin
    MOVWF V0+4
    CLRF V0+5
    CLRF V0+6
    CLRF V0+7
    RETURN
lead_rest:
    BSF V0+4,7
    RETURN

INCLUDE "gain_tables.inc"
INCLUDE "wave_tables.inc"
INCLUDE "music_tables.inc"
END
