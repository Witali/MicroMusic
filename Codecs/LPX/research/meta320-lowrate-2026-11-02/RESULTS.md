# Decoder-budget pilots: no feature adopted

All three ideas retained the protected best stream on the complete public
19200-sample tuning phrase. No new candidate passed the registered combined
PCM/PWM SSE, STOI, source-period and clipping guards. These are tuning results,
not a full-corpus result, listening verdict or proof that every possible
encoder for these formats must lose. The final quality branch does not enable
either new decoder format or the additional brightness feature.

The protected streams remain byte-identical: sparse80 at 578 bytes within the
600-byte/2 kbit/s cap, and ordinary v5/P4 at 900 bytes within the 3 kbit/s cap.
They are the previously accepted pitch/beam results, not weak uniform controls.

| Idea | Budget | Complete proposal attempts | New admitted outputs | Decision |
|---|---:|---:|---:|---|
| Metadata once per 320 samples |3 kbit/s|25|0|Keep ordinary v5/P4|
| Existing header filter grid |2 kbit/s|49 combinations|0|Keep incumbent|
| Existing header filter grid |3 kbit/s|49 combinations|0|Keep incumbent|
| Raw-scale interpolation |2 kbit/s|5|0|Keep sparse80|
| Raw-scale interpolation |3 kbit/s|5|0|Keep ordinary v5/P4|

Header journals include the protected incumbent separately: 50 counted attempts
and 49 unique outputs per budget. The original header occurs in the grid and
is counted even though its bytes duplicate the protected result. All attempted
fitting work, including duplicate final bytes, is retained. Complete anonymous
candidate records and rejection reasons are in [host-evidence.json](host-evidence.json).

## Metadata320

Sharing scale/lag/gain over 40 ms frees 375 bit/s for spectra. The pilot kept
cadences 1/2/4/8 and adaptive plans as separate complete candidates. It performed
348650 parameter fits and 179276800 position/sign trials in 115.56 seconds of
reported pilot wall time. The best new STOI was 0.75455, below the protected
0.75935; its PWM SER was 3.884 versus 4.736 dB. Reusing the incumbent's spectra
saved 112 audio bytes but dropped STOI to 0.69603. Some joint scalar scores were
lower, but their full waveform/intelligibility guards failed.

The rejected dense 898-byte diagnostic increased program Flash by 222 bytes
and notification-subtracted mean producer work by about 9.12%. Its old observer
retains a conservative interrupt-return residual; it is not pooled with the
later precise ramp observer. It produced exact PWM without underruns, but its
sound proxies did not justify adoption. See [decoder-costs.json](decoder-costs.json).

## Existing header filters

The 49-point grid changed only preQ14/brightQ14; the entire payload and file
length remained exact. At 2 kbit/s the highest STOI changed 0.63462→0.63556 while
SER fell2.161→0.377 dB. At 3 kbit/s it changed 0.75935→0.76130 while SER fell
4.736→1.042 dB. Neither exchange passed the existing guards. No target CPU
claim is made for these rejected headers; nonzero brightness would execute
the already existing extra multiply. Pilot wall times were 12.24/10.16 seconds.

## Scale ramp

Version 10 interpolates raw steps, with nearest rounding over eight20-sample
phases. Sparse80 then holds the target for the rest of its320-sample tuple.
The first tuple starts at its target, including valid zero. The independent
model is not an old v5 expansion. Two actual native C paths, raw and Q4-cached,
matched the model; eight small fitted-state preflight cases also passed before
real tuning. Direct-parser, tail, copied-state and default-off checks are
documented with the target evidence.

The pilot included unchanged-payload conversion and waveform/clipping-aware
refits, each with current-block or fixed-next-block lookahead selection. At 2
kbit/s, conversion raised STOI to 0.64720 but worsened SSE. The clip-aware greedy
refit removed all 37 hard clips and improved the joint proxy, but lost0.0399 dB
of SER; the unguarded lookahead reached 0.66859 STOI but lost one of two source-
period matches. At 3 kbit/s all refits lost STOI; none passed every guard. All
tradeoffs remain saved, rather than silently weakening the preregistration.
The pilot wall times were 26.78/11.94 seconds, excluding the fixed preflight.

Same-payload target probes on ATmega328P at 16 MHz used AVR-GCC 7.3.0 with explicit
ASM, queue 256/prefill 192, active interrupts and full19200-sample PWM checks:

| Format | Mean producer work | Program Flash | Static SRAM |
|---|---:|---:|---:|
| Sparse80 plain→ramp |816.666→818.869 cycles/sample (+0.270%)|4880→5196 B|756→760 B|
| P4 plain→ramp |767.730→785.072 cycles/sample (+2.259%)|4574→4996 B|756→760 B|

Both had exact PWM and zero underruns. The cost observer excludes complete
live IRQ intervals including actual RETI steps. These probes establish the
reported diagnostic costs, not acceptance of every refitted stream. The
additional four cold SRAM bytes and small CPU increase fit the proposed cost
allowance, but the tuning quality condition was not met. No physical-board or
heldout-format quality claim follows from the simulation.

## Reproduction and retained boundaries

[PROTOCOL.md](PROTOCOL.md), [HEADER_PROTOCOL.md](HEADER_PROTOCOL.md) and
[RAMP_PROTOCOL.md](RAMP_PROTOCOL.md) fix each experiment's inputs, bounds and
admission. Host models live in the active tools directory; they do not enable
the new formats by default. The executable host experiments are
`encode_meta320.py`, `header_sweep.py` and `scale_ramp_fit.py`. Each accepts a
reference WAV, protected stream and fresh ignored output directory; use
`--help` for explicit pinned native-reference arguments. All output media and
detailed source/compiler/library receipts stay under ignored `build/`.

Set the project's Python dependency path and `LPX_NATIVE_CXX` for native direct
tests. Run the canonical host contract tests and the opt-in native direct
tests before reproducing a numerical pilot. Ramp native references must be
two real version 10 C builds with SPARSE80 and SCALE_RAMP enabled, ASM disabled,
LPC segments 2 and excitation Q4 off/on. The local receipt pins their exact
sources/options/binaries and is verified before and after fitting. Call
`scale_ramp_fit.preflight(receipt)` before a full ramp pilot; it checks both
modes, both loss branches and both lookahead branches without retuning.

All prototypes and their provenance remain on the isolated decoder-budget
branch. No raw corpus audio, private paths, logs, fingerprints or generated
binaries belong in this evidence. No further quality search or decoder
adoption followed these pilot decisions.
