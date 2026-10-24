# LPC2 Improved, Tiny and HQ4/Q3: source audit

This is a read-only architecture comparison. It does not establish a listening
win or MCU qualification. The current priority is a quality-first PC reference
and measured compression; 1024-byte Flash is temporarily not a selection gate.

## Versions and naming

`ATmega328/Sound/reference/lpc2-voice/lpc2_v11_original.html` already contains
**LPC2 Improved**: order-10 LSF, mixed excitation, pitch tracking, eight synthesis
subframes and a formant postfilter. These features were not introduced by Voice
v2. The LSF conversion/quantization, pitch-candidate, Viterbi and LPC-window
functions in the two saved pages are literally identical.

Voice v2's saved reference is
`ATmega328/Sound/reference/lpx3/lpc2_v2_reference.html`. Its main format change is
a per-recording F0 range in the existing 36-byte header. The old version uses
fixed 55–420 Hz (v11 lines 360–362); v2 defaults to 65–850 Hz (v2 lines 360–362,
478–505). Both retain six pitch bits. The logarithmic step is approximately
55.86 cents in the old range and 70.65 cents in the wider default range. Wider
range avoids clamping high voices but does not itself improve quantization.
The v2 encoder also accepts an optional external `pitchGuideHz` array
(lines 456–460); the normal browser UI does not run Python pYIN.

**LPX3 is a separate residual-bearing format.** Its Python implementation
`reference/lpx3/hybrid_codec.py`, lines 1–10 and 134–183, embeds LPC2 plus
2/3/4 bits of excitation per sample and a scale byte per block. The LPX3 decoder
(lines 186–209) uses the interpolated LPC envelope and de-emphasis, with optional
brightness. It does not synthesize the LPC2 chirp/modes/gain or its formant
postfilter. Its better waveform agreement is bought with actual residual data.
Even interpolation differs on transient attacks: the LPX3 coefficient extractor
uses fixed subframe fractions (lines 23–37), whereas LPC2 accelerates rising
transients. Do not label LPX3 results as plain LPC2 Improved results.

## What the LPC2 reference actually does

Line references in this section are to `lpc2_v2_reference.html`.

| Mechanism | Source evidence |
|---|---|
| Ten voiced LSF values, 39 bits; four unvoiced values, 18 bits | 360, 397–401, 468 |
| Ordered LSF, minimum spacing; conversion back to all-pole LPC | 364–395 |
| Centered overlapping Hamming analysis, separate order-10/order-4 fits | 440–451 |
| Pre-emphasis before analysis, residual-error gain | 448–451 |
| Up to five normalized-autocorrelation F0 candidates, fractional refinement | 402–414 |
| Global voiced/unvoiced/F0 path with continuity and large-jump penalties | 416–438 |
| Noise, mixed, voiced, transient mode selection | 464–468 |
| Coefficient reuse; silence and repeated frames cost fewer bits | 470–488 |
| Eight subframes, LSF/log-gain/period interpolation, faster transient attack | 515–517 |
| Persistent fractional pulse countdown, no frame phase reset | 510–514, 523 |
| Simultaneous chirp and noise, or high-passed noise on mixed/transient modes | 522–525 |
| Ten-pole synthesis, formant postfilter, de-emphasis | 526–528 |

The default 15-sample chirp (line 311) has area approximately zero and energy
0.99981. Multiplication by `sqrt(period)` approximately normalizes its power
per period. **Its zero-area property is lost when the period is shorter than
15 samples:** line 523 resets `chirpIndex` at every new pulse, truncating the
previous chirp. This starts above 800 Hz at 12 kHz or above 500 Hz at 7.5 kHz.
Copying this exact source into a high-voice 7.5-kHz profile needs an explicit
period-aware zero-DC check or a phase-scaled source.

An ordinary nonrepeated voiced frame costs 5 energy + 2 mode + 1 reuse +
6 pitch + 39 LSF = 53 bits, or 2.65 kbit/s at a 20-ms step, before the header.
A nonrepeated unvoiced frame is 26 bits; silence uses five bits. This is a
useful low-rate envelope/excitation baseline, not a waveform-preserving codec.

## Comparisons with the existing cores

HQ4 `codec/model.py` lines 14–49 uses eight byte lattice states, four-bit
reflection coefficients, linear 0–15 excitation gain, an integer period and a
four-sample pulse **or** binary noise. `mode` bits choose the second/third pulse
sample strengths, not LPC2's mixed/transient modes. Frame updates reset phase
(line 25) and replace filter/gain immediately. The voiced pulse area is
positive, 4–6 times gain per cycle, rather than zero.

`codec/hq4_q3.py` preserves these source/transition choices (lines 25–78).
Its coefficient multiplication divides by eight rather than sixteen, expanding
the useful stable range to +/-7/8 but making the grid coarser (1/8 vs 1/16).
The optional T1 recurrence (lines 79–83) boosts low-frequency content and DC;
it is not a multi-pole formant postfilter. Both cores retain byte rounding and
modulo arithmetic; valid fit candidates must avoid internal wrap events.

Tiny is a different architecture. `codec/fixed_period.py` lines 79–120 uses
learned 32-sample periodic waveforms, phase interpolation, a continuous 16-bit
DDS accumulator, neighboring-frame crossfades and independent noise residual.
It already has several smoothing/mixing features absent from HQ4. Its remaining
problems cannot be attributed simply to a missing interpolation switch.

## Listening defaults are additional variables

Switching the page to LPC2 selects 12 kHz and 20 ms (v2 line 993), whereas the
existing Tiny/HQ4 references use 7.5 kHz. Defaults also include pre=.85,
32-ms analysis, postfilter=.35, brightness +4 dB and high-pass 70 Hz (line 32).
The output code applies a brightness tilt with whole-file energy matching,
high-pass/DC correction and peak reduction to .98 (lines 119–150, 172–177).
Input peak normalization/DC removal is enabled by default (lines 19, 68–89).
The browser's basic input resampler is linear interpolation (line 61).

Measure the unchanged core output separately from UI output processing. Start
at the same frozen corpus rate/levels; any later native-rate study needs a
separate reference policy. Upsampling an existing band-limited reference does
not recover its missing high-frequency content. A lower spectral error after
arbitrary level matching is not proof of faithful raw gain or waveform shape.

## Reuse priorities and future MCU work

1. Establish the exact native LPC2 reference on the frozen corpus, including
   round-tripped packed frames. Measure raw and UI-processed outputs separately.
2. Ablate stable envelope precision/order, LSF/gain interpolation, fractional
   F0, mixed/transient excitation and postfilter. Jointly refit each new core;
   do not infer a win from changing a pulse in an already fitted model.
3. Keep an explicit raw gain/DC check, intelligibility guard and multiple
   spectral components. Use the residual-bearing LPX3 curve to quantify the
   quality lost by a generic excitation model, with its real byte cost.
4. After achieving an audible quality reference, reduce its stream with
   measured rate/distortion tradeoffs. Reuse and interpolation already offer
   savings without making all source voices share a fixed pulse shape.

Removing the Flash limit does not make the browser implementation an ATtiny13A
port. Its three Float64 histories alone occupy 240 bytes, before coefficients,
stack and other state; ATtiny13A has 64 bytes SRAM. A later port needs explicit
fixed-point state/accumulator widths, stable coefficient updates, overflow
checks and measured cycles. Precomputing analysis/LSF conversions on the encoder
can move work away from the MCU, at a separately reported stream-size cost.
No MCU feasibility is claimed by this source audit.
