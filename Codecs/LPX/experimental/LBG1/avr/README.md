# Complete LG1 AVR playback

These are full actual-stream measurements, not isolated arithmetic timings.
Production LPX files and genuine `LG` files are played by the same dedicated
hardware/FIFO/ISR recipe and compared byte for byte with their portable C
decoder output. The current optimized LPX producer remains the baseline.
The LG adapter disables the original class's private ROM shortcuts and uses
the experimental public API, so the result compares these implementations,
not an algorithmic lower bound on either format.

## Retained evidence

- [baseline-results.json](baseline-results.json): 32 complete current LPX runs.
- [lg-results.json](lg-results.json): 96 LG requests, including every physical
  Flash failure and all 87 actual fitting-image playbacks.
- [controls-results.json](controls-results.json): 22 complete control playbacks.
- [summary.json](summary.json): paired cycle totals and resource ranges.
- [build-provenance.json](build-provenance.json): exact compiler options,
  source/device-header hashes, image recipes and observer-equivalence proof.

Source audio, LG/LPX/PCM media, ELF/HEX files and raw logs remain in ignored
`build/`. Retained JSON includes hashes of the actual linked ELF/image,
embedded input and complete/valid PWM output. Build recipes normalize only
checkout/output directory names; flags and source identities are retained.

The matrix is bound to the fixed decoder snapshot in `lg-results.json` and
the listed current baseline inputs at source revision `24fd9416`. Each run
freezes its input bytes and reference PCM before building. Changing a later
encoder manifest or decoder file cannot silently change a recorded run.

## Hardware and admission

Both real compiler targets run at 16 MHz with 8 kHz scheduling: Timer0 CTC,
prescaler 8, `OCR0A=249`, 2000 CPU cycles per sample. Timer1 fast PWM8 uses
prescaler 1 and OC1A/PB1 at 62.5 kHz. This experiment deliberately keeps the
same Timer0/Timer1 recipe on ATtiny88 and ATmega328P; it does not switch Mega
to the separate Nano D3/Timer2 recipe. The FIFO is 32 bytes with prefill24;
playback gain Q7 is128, with no fitted gain or delay. The same assembly ISR
is retained for both arithmetic selections.

Actual device definitions come from the pinned ATtiny_DFP 3.4.278 and the
compiler-selected avr-libc ATmega328P header. AVR-GCC is7.3.0, GNU C++11,
`-Os -flto -mcall-prologues -mrelax`; full options are in build provenance.
The instruction/timer model is simavr1.6. No physical board was measured.

Admission requires correct complete PWM/sample count, zero underruns,
validated queue/timer shutdown, bounded output spacing, preserved interrupt
context, and positive observed stack margin within the real target memory.
ATtiny88 has8192 bytes of physical Flash and512 bytes SRAM; a standard
bootloader's6012-byte application region is checked separately. Mega's
physical limits are32768 Flash and2048 SRAM. No over-limit image is run as
if the device had larger memory.

Nine LG Tiny requests fail the physical Flash link limit. Those rows have
no invented CPU timing. No prefix substitute or external-memory transport
is used to admit a whole recording that does not fit. All fitting ASM LG
speech images have zero underruns. The Tiny C arithmetic controls remain
too slow on complete speech, while their valid queued byte sequences are
still exactly correct. Silence inserted during underruns is retained in
the complete PWM output rather than removed from admission checks.

The original observer already emits valid-only PWM for native Mega. A
staged host-only extension adds the same diagnostic output for Tiny. Replaying
the same unchanged Tiny/Mega ELFs with the original observer gives identical
complete PWM and all45/48 original timing fields; the proof is retained.
Timer, CPU, stack, register-preservation and cycle-accounting logic is unchanged.

## Main results

| Full-file requests | Measured images | Real-time admissions |
| --- | ---: | ---: |
| Current LPX, both targets × C/ASM | 32/32 | 24/32 |
| LG exact/fine/compact, both targets × C/ASM | 87/96 | 66/96 |

ASM admissions are4/8 exact,7/8 fine and7/8 compact on Tiny; all three variants
admit8/8 on Mega. Mega C also admits8/8 in each variant. Only two compact
Tiny images fit the6012-byte bootloader region; no exact or fine Tiny image
fits that smaller region. Current LPX ASM admits every file on both targets.

Sample-weighted **paired complete files that physically fit** give:

| Target / variant, ASM | Paired files | LPX decode → LG decode | LPX producer → LG producer |
| --- | ---: | ---: | ---: |
| Tiny exact | 4 | 1426.450 → 1636.283 | 1447.450 → 1675.284 |
| Tiny fine | 7 | 1366.618 → 1552.390 | 1387.618 → 1591.390 |
| Tiny compact | 7 | 1366.618 → 1549.115 | 1387.618 → 1588.116 |
| Mega exact | 8 | 626.657 → 765.200 | 648.657 → 804.200 |
| Mega fine | 8 | 626.657 → 746.402 | 648.657 → 785.402 |
| Mega compact | 8 | 626.657 → 742.155 | 648.657 → 781.156 |

Numbers are foreground CPU cycles per corresponding successful decode/producer
call, aggregated as sums of cycles divided by sums of calls. Decode means use
`decode_calls`, producer means use `producer_calls`; the original source count
is not replaced with the larger number of timer writes on underrunning C runs.
The producer region is the original head-read-to-FIFO-publication boundary;
startup/header processing outside those regions is not included. ISR costs,
wall intervals, output spacing, minima and peaks are retained separately.

LG ASM program size excluding media is5025–5026 bytes on Tiny and4273–4276
on Mega, versus3578–3579 and3025–3026 for current LPX. Compact LG full images
are5958–7254 bytes on the seven fitting Tiny cases and5206–7450 on Mega.
LG uses420 bytes of static SRAM and42 observed stack bytes on both ASM
targets, leaving50/1586 physical bytes respectively. `sizeof(Decoder)` is386
bytes on both MCUs, verified from actual target objects under C/ASM/generic
selection. These are observed workloads, not stack bounds for arbitrary code.

## Full controls and arithmetic correctness

The22 controls include legal partial streams of1/41/321 samples, two complete
reset playbacks of real speech, forced generic arithmetic and the encoder's
actual1440-sample logarithmic-level/linear-lag control. All22 valid PWM sequences
match portable C;19 meet realtime admission. Both ASM targets and Mega C pass
the true-log curve playback. Tiny C/generic fail only the longer realtime
controls, with their correct valid byte sequence retained.

The generic control explicitly enables assembly globally but sets
`LPX4_ARCH=0`. Actual target objects prove neither handwritten ASM backend is
selected while real AVR25/AVR5 and PROGMEM access remain active. Ordinary C
controls use`LPX4_ENABLE_ASM=0`; no compiler CPU/memory macro is removed.

The first full Mega ASM pilot caught a Q4 contract mismatch: the production
circular LPC leaf expects already-scaled Q4 excitation, whereas the new
decoder supplied unscaled excitation. The corrected branch multiplies by16
before that leaf; the explicitly unscaled C/Tiny path stays unscaled. The
failing pilot is not part of the admitted matrix. Every retained matrix and
control uses the fixed snapshot and matches its portable reference.

## Reproduction

First generate current baseline and LG files as documented in the parent
[whole-decoder study](../../../research/lbg1-2026-11-26/README.md). Then run
inside Linux/WSL with the installed toolchain, using fresh output directories:

```sh
python3 Codecs/LPX/experimental/LBG1/avr/run_full.py --manifest build/lbg1-common/baselines.json --output build/lbg1-avr/baseline-v1 --jobs 2
python3 Codecs/LPX/experimental/LBG1/avr/run_full.py --manifest build/lbg1-encoder/manifest.json --variants exact fine compact --output build/lbg1-avr/lg-matrix-v2 --jobs 2
python3 Codecs/LPX/experimental/LBG1/tests/check_observer_equivalence.py --run build/lbg1-avr/baseline-v1
build/lbg1-encoder/encode-probe selftest build/lbg1-encoder/synthetic-log-rise
python3 Codecs/LPX/experimental/LBG1/tests/make_full_controls.py --output build/lbg1-avr/control-inputs-v2
python3 Codecs/LPX/experimental/LBG1/tests/run_full_controls.py --manifest build/lbg1-avr/control-inputs-v2/manifest.json --output build/lbg1-avr/controls-v2
python3 Codecs/LPX/experimental/LBG1/avr/retain_results.py --baseline build/lbg1-avr/baseline-v1 --experimental build/lbg1-avr/lg-matrix-v2 --controls build/lbg1-avr/controls-v2 --observer-proof build/lbg1-avr/baseline-v1/observer-equivalence/proof.json
```

The corpus run supports a small process pool for independent builds. It reads
the manifest once, freezes selected media/PCM, snapshots decoder and dependency
sources, verifies that linked Flash really contains those exact bytes, and
preserves both successful results and explicit physical-fit failures. Output
must remain below ignored `build/`; no production source, firmware publication,
or hardware configuration is changed by these scripts.
