; -----------------------------------------------------------------------------
; Codec2 3200 -> ZX Spectrum 128 / Pentagon AY proof-of-concept decoder
; -----------------------------------------------------------------------------
; CPU: Z80 ~3.5 MHz
; Sound: AY-3-8912 / YM2149 at standard Spectrum 128 ports
; Input frame format: Codec2 mode 3200, 64 bits = 8 bytes per 20 ms frame
;
; IMPORTANT:
;   * The INPUT BITSTREAM layout is compatible with Codec2 3200:
;       voiced0(1), voiced1(1), pitch Wo(7), energy(5), 10 x LSPD(5)
;     and each field is Gray coded, MSB first, as in Codec2 pack.c.
;   * The SYNTHESIS is intentionally simplified for a Z80.  The reference
;     Codec2 decoder converts LSP -> LPC -> harmonic magnitudes and performs
;     sinusoidal synthesis.  This version maps the first three LSP pairs to
;     three AY tone channels and snaps them to pitch harmonics when voiced.
;     Unvoiced frames are rendered with AY noise.
;   * Therefore this is a bitstream-reading, Z80-friendly Codec2 vocoder
;     prototype, NOT a sample-identical implementation of the reference
;     Codec2 decoder.
;
; Build target: ORG 32768.  Start with RANDOMIZE USR 32768.
; One Codec2 frame is decoded per 50 Hz video interrupt (20 ms PAL frame).
; -----------------------------------------------------------------------------

        org 0x8000

FRAME_COUNT equ 218

start:
        ; initialise stream and number of 20 ms frames
        ld hl,sample_data
        ld (stream_ptr),hl
        ld hl,FRAME_COUNT
        ld (frames_left),hl

        ; turn all AY channels off before starting
        call silence
        ei

main_loop:
        ; PAL Spectrum interrupt is 50 Hz = exactly one Codec2 20 ms frame
        halt
        call decode_frame
        call synth_frame

        ld hl,(frames_left)
        dec hl
        ld (frames_left),hl
        ld a,h
        or l
        jr nz,main_loop

        call silence
        ret

; -----------------------------------------------------------------------------
; decode_frame
; Reads one 8-byte Codec2-3200 frame from stream_ptr.
;
; Bit fields are Gray coded and MSB-first.  C contains a one-bit mask into the
; current byte, and HL is advanced by getgray().  After exactly 64 bits HL
; points to the next frame again.
;
; To keep the Z80 work small we reconstruct only what the AY synthesiser needs:
;   - voiced flag (second 10 ms half-frame)
;   - pitch index -> f0 lookup
;   - energy index -> 4-bit AY volume lookup
;   - first 6 LSP-difference indices -> first three LSP-pair centre frequencies
; Remaining four LSPD fields are still consumed to preserve the real frame
; layout.
; -----------------------------------------------------------------------------
decode_frame:
        ld hl,(stream_ptr)
        ld c,0x80                 ; first bit = bit 7 of first byte

        ; voiced flag for first 10 ms half-frame (not used by simplified synth)
        ld b,1
        call getgray

        ; voiced flag for second 10 ms half-frame
        ld b,1
        call getgray
        ld (voiced),a

        ; 7-bit linearly quantised pitch index
        ld b,7
        call getgray
        ld (pitch_index),a

        ; 5-bit Codec2 energy index
        ld b,5
        call getgray
        ld (energy_index),a

        xor a
        ld (lsp_accum),a          ; cumulative LSP position in 25 Hz units

        ; ---- LSPD #0 : standard table 25,50,...800 Hz -----------------------
        ld b,5
        call getgray
        call delta_standard
        call accum_delta
        ld (pair_start),a

        ; ---- LSPD #1 : standard; closes LSP pair 0 -------------------------
        ld b,5
        call getgray
        call delta_standard
        call accum_delta
        ld d,a                    ; current LSP position
        ld a,(pair_start)
        add a,d                   ; pair centre in 12.5 Hz units
        jr nc,center0_ok
        ld a,255
center0_ok:
        ld (center0),a

        ; ---- LSPD #2 : standard --------------------------------------------
        ld b,5
        call getgray
        call delta_standard
        call accum_delta
        ld (pair_start),a

        ; ---- LSPD #3 : wide table; closes LSP pair 1 -----------------------
        ld b,5
        call getgray
        call delta_wide
        call accum_delta
        ld d,a
        ld a,(pair_start)
        add a,d
        jr nc,center1_ok
        ld a,255
center1_ok:
        ld (center1),a

        ; ---- LSPD #4 : wide table ------------------------------------------
        ld b,5
        call getgray
        call delta_wide
        call accum_delta
        ld (pair_start),a

        ; ---- LSPD #5 : wide table; closes LSP pair 2 -----------------------
        ld b,5
        call getgray
        call delta_wide
        call accum_delta
        ld d,a
        ld a,(pair_start)
        add a,d
        jr nc,center2_ok
        ld a,255
center2_ok:
        ld (center2),a

        ; LSPD #6..#9.  The simplified 3-formant AY synth does not use these,
        ; but they MUST be consumed: 4 * 5 bits completes the real 64-bit frame.
        ld b,5
        call getgray
        ld b,5
        call getgray
        ld b,5
        call getgray
        ld b,5
        call getgray

        ; HL now points to byte 0 of the next frame.
        ld (stream_ptr),hl

        ; pitch_index -> fundamental frequency in 12.5 Hz units.
        ; Codec2 mode 3200 uses f0 from about 50 to 400 Hz.
        ld a,(pitch_index)
        ld e,a
        ld d,0
        ld hl,pitch_table
        add hl,de
        ld a,(hl)
        ld (pitch_units),a

        ; energy_index -> AY logarithmic-ish volume 0..15.
        ; The table is deliberately nonlinear because AY amplitude is nonlinear
        ; and human loudness is closer to logarithmic than linear.
        ld a,(energy_index)
        ld e,a
        ld d,0
        ld hl,energy_table
        add hl,de
        ld a,(hl)
        ld (base_volume),a
        ret

; -----------------------------------------------------------------------------
; getgray
; Input : HL -> current stream byte, C = bit mask, B = field width (1..7 here)
; Output: A = decoded binary field value
;         HL/C advanced to the next unread bit
; Clobbers D,E,B.  Does NOT use floating point or multiplication.
;
; Codec2 packs each field in Gray code.  Gray -> binary is:
;   b = g ^ (g>>1); b ^= b>>2; b ^= b>>4
; This works for all fields here (max 7 bits).
; -----------------------------------------------------------------------------
getgray:
        ld d,0
getgray_loop:
        sla d
        ld a,(hl)
        and c
        jr z,getgray_zero
        inc d
getgray_zero:
        srl c
        jr nz,getgray_mask_ok
        inc hl
        ld c,0x80
getgray_mask_ok:
        djnz getgray_loop

        ld a,d
        ld e,a
        srl e
        xor e
        ld e,a
        srl e
        srl e
        xor e
        ld e,a
        srl e
        srl e
        srl e
        srl e
        xor e
        ret

; -----------------------------------------------------------------------------
; LSP difference codebooks used by Codec2 3200.
;
; dlsp1,2,3,7,8,9,10 are 32 scalar values 25,50,...800 Hz.
; In units of 25 Hz: delta = index + 1.
;
; dlsp4,5,6 contain 25..200 Hz in 25-Hz steps then 250..1400 Hz in
; 50-Hz steps.  In units of 25 Hz:
;   index < 8 : index+1
;   index >=8 : 2*index-6
; -----------------------------------------------------------------------------
delta_standard:
        inc a
        ret

delta_wide:
        cp 8
        jr c,delta_standard
        add a,a
        sub 6
        ret

; Input A = LSP delta in 25 Hz units.
; Output A = cumulative LSP in 25 Hz units (saturates at 255).
; Preserves HL and C because they hold the bit-stream cursor.
accum_delta:
        ld d,a
        ld a,(lsp_accum)
        add a,d
        jr nc,accum_ok
        ld a,255
accum_ok:
        ld (lsp_accum),a
        ret

; -----------------------------------------------------------------------------
; synth_frame
; Voiced speech:
;   - use first three LSP pair centres as three resonant regions/formants
;   - snap each centre to the nearest harmonic of f0
;   - feed those frequencies to AY channels A/B/C
; Unvoiced speech:
;   - disable tones, enable AY noise
;
; This is intentionally much cheaper than Codec2's reference harmonic
; amplitude reconstruction and overlap/add synthesis.
; -----------------------------------------------------------------------------
synth_frame:
        ld a,(voiced)
        or a
        jr z,synth_unvoiced

        ; mixer register 7: bits 0..2 = tone disable, 3..5 = noise disable
        ; 0x38 => tones enabled, noise disabled on A/B/C.
        ld e,0x38
        ld a,7
        call ay_write

        ; Channel A: first LSP pair centre
        ld a,(pitch_units)
        ld d,a
        ld a,(center0)
        call snap_harmonic
        call set_tone_a

        ; Channel B: second LSP pair centre
        ld a,(pitch_units)
        ld d,a
        ld a,(center1)
        call snap_harmonic
        call set_tone_b

        ; Channel C: third LSP pair centre
        ld a,(pitch_units)
        ld d,a
        ld a,(center2)
        call snap_harmonic
        call set_tone_c

        call set_voiced_volumes
        ret

synth_unvoiced:
        ; 0x07 => tones disabled, noise enabled on all three channels.
        ld e,0x07
        ld a,7
        call ay_write
        ld e,5                    ; fairly bright noise period
        ld a,6
        call ay_write
        call set_unvoiced_volumes
        ret

; -----------------------------------------------------------------------------
; snap_harmonic
; Input : A = desired formant centre in 12.5 Hz units
;         D = fundamental f0 in 12.5 Hz units
; Output: A = nearest integer harmonic of f0, min one fundamental
;
; Uses repeated subtraction.  It is called only 3*50 = 150 times/s, so this is
; far cheaper on a Z80 than a general multiply/divide routine.
; -----------------------------------------------------------------------------
snap_harmonic:
        ld e,0
snap_loop:
        cp d
        jr c,snap_remainder
        sub d
        ld b,a
        ld a,e
        add a,d
        jr c,snap_saturate
        ld e,a
        ld a,b
        jr snap_loop

snap_remainder:
        ; A is the remainder. Round to nearest harmonic.
        add a,a
        cp d
        jr c,snap_floor
        ld a,e
        add a,d
        jr c,snap_saturate
        jr snap_nonzero

snap_floor:
        ld a,e
snap_nonzero:
        or a
        jr nz,snap_done
        ld a,d                    ; never return 0 Hz for a voiced frame
snap_done:
        ret
snap_saturate:
        ld a,255
        ret

; -----------------------------------------------------------------------------
; AY tone helpers.
; ay_period_table maps frequency index u = f/12.5 Hz to
; period ~= AY_CLOCK/(16*f), clamped to the 12-bit AY period range.
; -----------------------------------------------------------------------------
set_tone_a:
        call lookup_period
        ld a,0
        call ay_write
        ld e,d
        ld a,1
        call ay_write
        ret

set_tone_b:
        call lookup_period
        ld a,2
        call ay_write
        ld e,d
        ld a,3
        call ay_write
        ret

set_tone_c:
        call lookup_period
        ld a,4
        call ay_write
        ld e,d
        ld a,5
        call ay_write
        ret

; Input A = frequency in units of 12.5 Hz
; Output DE = 12-bit AY tone period, low byte E / high byte D
lookup_period:
        ld l,a
        ld h,0
        add hl,hl
        ld de,ay_period_table
        add hl,de
        ld e,(hl)
        inc hl
        ld d,(hl)
        ret

; -----------------------------------------------------------------------------
; Volume shaping.  AY volume registers are 0..15.
; Voiced: A strongest, B -1, C -2.
; Unvoiced noise is deliberately lower on B/C to avoid excessive hiss.
; -----------------------------------------------------------------------------
set_voiced_volumes:
        ld a,(base_volume)
        ld e,a
        ld a,8
        call ay_write

        ld a,(base_volume)
        or a
        jr z,voiced_b_ready
        dec a
voiced_b_ready:
        ld e,a
        ld a,9
        call ay_write

        ld a,(base_volume)
        cp 2
        jr nc,voiced_c_sub
        xor a
        jr voiced_c_ready
voiced_c_sub:
        sub 2
voiced_c_ready:
        ld e,a
        ld a,10
        call ay_write
        ret

set_unvoiced_volumes:
        ld a,(base_volume)
        ld e,a
        ld a,8
        call ay_write

        ld a,(base_volume)
        cp 2
        jr nc,unvoiced_b_sub
        xor a
        jr unvoiced_b_ready
unvoiced_b_sub:
        sub 2
unvoiced_b_ready:
        ld e,a
        ld a,9
        call ay_write

        ld a,(base_volume)
        cp 4
        jr nc,unvoiced_c_sub
        xor a
        jr unvoiced_c_ready
unvoiced_c_sub:
        sub 4
unvoiced_c_ready:
        ld e,a
        ld a,10
        call ay_write
        ret

silence:
        xor a
        ld e,a
        ld a,8
        call ay_write
        xor a
        ld e,a
        ld a,9
        call ay_write
        xor a
        ld e,a
        ld a,10
        call ay_write
        ret

; Input A = AY register number, E = value.
; Spectrum 128/Pentagon AY ports: select 0xFFFD, data 0xBFFD.
ay_write:
        push bc
        ld bc,0xfffd
        out (c),a
        ld a,e
        ld bc,0xbffd
        out (c),a
        pop bc
        ret

; -----------------------------------------------------------------------------
; Mutable decoder state (code is loaded into RAM, so self-contained data is OK)
; -----------------------------------------------------------------------------
stream_ptr:     dw sample_data
frames_left:    dw FRAME_COUNT
voiced:         db 0
pitch_index:    db 0
energy_index:   db 0
pitch_units:    db 8
base_volume:    db 0
lsp_accum:      db 0
pair_start:     db 0
center0:        db 40
center1:        db 100
center2:        db 160

; -----------------------------------------------------------------------------
; Tables generated by build.py
; -----------------------------------------------------------------------------
pitch_table:
        incbin "pitch.tbl"
energy_table:
        incbin "energy.tbl"
ay_period_table:
        incbin "ayperiod.tbl"

; 218 * 8 bytes = 1744 bytes of test stream.
sample_data:
        incbin "speech.c2zx"
sample_end:
