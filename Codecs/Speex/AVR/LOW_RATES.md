# Optional low-rate profiles

Implementation and admission are complete. Target remains
ATmega328P, 16 MHz, 2 KB SRAM; explicit AVR ASM is the playback target.
Portable C fallback selection and the existing compact Q7/16-tap QMF remain.
Original Xiph 1.2.1 files, mode tables and BSD provenance stay unchanged.

## Stage 1: NB5.95 / WB7.75

`SPEEX_ENABLE_NB2=1` adds submode 2: 119 meaningful bits / 15 bytes, 160
samples at 8 kHz. Combined with HB1 it uses 155 bits / 20 bytes, 320 samples
at 16 kHz. Padding is ignored; length/mode/HB checks precede state updates.
Feature defaults to zero. `--low-rates 1` selects it in the AVR builders.
Feature bits select NB2=1, NB8=2, NB1=4; availability is described per stage.

LBR LSP/LPC and IIR are shared. Ten-sample pitch/innovation primitives are
reused with `exc_10_16_table` (160 B), and the 32 no-subframe-correction
energies are generated from upstream constants. NB3 and NB2 share one
short-pitch controller with the codebook selected outside its sample loop.
HB1 reuses the existing excitation buffer and fold kernel, not a new frame.
The no-correction maximum scale is 115088100, within the existing 121000000
primitive domain; the same pitch gain codebook keeps existing signed24 bounds.

Initial screening: three retained RU/EN clips, 40 frames each. NB matches
untouched Xiph PCM; WB matches the independent established compact-profile
oracle, including first-frame reset replay. The continuous WB player checks
the same 120 frames with timers/IRQ, exact s16/PWM and zero underruns.
These are initial tests, not the final full-corpus admission.

AVR GCC 7.3.0, existing mixed Os/O2/O3, LTO/mcall-prologues/mrelax;
avr8js 0.21.1. NB-only mailbox is 11546 B Flash / 1094 B static SRAM;
WB mailbox 18350 / 1275 B, or +948 / +1342 B Flash versus the minimum
NB8/WB9.8 images. The smaller packet mailbox accounts for the SRAM difference;
no new core synthesis buffer is allocated. WB screen mean 245158.833 cycles,
maximum 251095; these exclude output/interrupts. IRQ player leaves 423 B SRAM,
minimum queue 29 with no added foreground load. No board timing is claimed.

## Admission sequence (completed)

Add NB3.95/WB5.75 forced-pitch reconstruction, then NB2.15/WB3.95 noise and
vocoder processing, preserving the original random sequence and state across
rate changes. Follow with full corpus, padding/error/reset/mixed-mode checks,
default-image identity, C export, Flash delivery and active-IRQ admission.
Do not infer reduced CPU cost merely from reduced bitrate.

## Stage 2: NB3.95 / WB5.75

`SPEEX_ENABLE_NB8=1` adds 79-bit / 10-byte NB and 115-bit / 15-byte WB
packets. `--low-rates 3` enables both new pairs. The original forced pitch
builds prediction before adding innovation; feeding completed output back
would change PCM. For lags 17..144, at most two rounded predictor ancestors
are needed within a 40-sample subframe. Recover those from completed history
and pass small ranges through the existing three-tap kernel with outer gains
zero. A 24-byte stack edge replaces an additional 80-byte frame buffer.
The common HB1 controller selects the 20-sample/32-vector Flash codebook and
feeds the same ten-sample and folding primitives. LSP/LPC/IIR/QMF stay shared.

The same three-clip initial screen passes 120 NB and 120 WB exact/reset frames.
The WB player passes 120 continuous frames with timers/IRQ, exact PCM/PWM,
zero underruns, queue minimum 13 and 397 B free SRAM at zero extra load.
Both pairs together use 13044 B NB / 20024 B WB bare Flash. The original
minimum WB image remains byte-identical with lower rates disabled.
Full-corpus timing and mixed-mode admission remain the final stage.

## Stage 3: NB2.15 / WB3.95 (approximately 4 kbit/s WB)

`SPEEX_ENABLE_NB1=1` adds 43-bit / 6-byte NB and 79-bit / 10-byte WB packets.
`--low-rates 7` enables all three new pairs; the NB4 feature is independent.
There is no invented 4.000-kbit/s format: WB3.95 is the standard HB1 combination.
DTX/PLC, enhancer and highpass remain outside the restricted profile.

The original 32-bit LCG sequence starts at 1000 and advances 160 times per
NB1 frame. HB1 regenerates it from a four-byte frame-start seed snapshot.
Its five possible symbols are scaled once, with pulse/noise weights hoisted
out of the sample loop. The existing 80-byte output area holds 40 byte indices
in its upper half and is expanded forward safely. Vocoder phase fits uint8;
only exact rounded/weighted signed16 state is retained. The feedback mean
keeps its required int32 accumulator and original rounding. No PCM precision
change or new full-frame buffer is involved.

The initial literal version passes 640 exact/reset WB frames but averages
415676.1 cycles (maximum 419657), exceeding the frame budget. Exact finite-
domain/word optimizations reduce the same 16x40-frame screen to 266736.491
cycles (maximum 270622). These timings exclude ISR/output. All PCM is still
exact to the established compact-profile oracle. All three new pairs together
use 22022 B WB bare Flash, 1288 B static SRAM at a 10-byte mailbox width.
The initial three-clip/120-frame WB IRQ screen passes with exact s16/PWM,
zero underruns, min queue 18 and 395 B free SRAM, at zero extra load.
NB2.15 independently passes 120 original-Xiph exact/reset frames.

`tests/prove_low_noise.py` checks every signed16 high word against the
original noise equation, all 32 legal scales, state/phase bounds and both
byte orders for alias expansion. The literal slow comparison patch is retained
under the cookbook examples; it is not an admitted playback backend.
See [the reusable technique](../../../docs/avr-asm-cookbook/speex-five-symbol-noise.md).
Final full-recording, mixed-mode, bad-packet and delivery results follow below.

## Exact forced-prediction arithmetic

Use the existing selectable signed16 multiply and arithmetic >>13 primitive
for the at-most-two forced-pitch ancestors. Each input/product bound is
unchanged, every rounding step remains, and no new ASM implementation is added.
On the same three-clip/120-frame WB5.75 screen, mean cycles decrease
247514.067 -> 245738.742 and maximum 265776 -> 255464. Flash changes
20024 -> 20052 B (+28), stack 221 -> 219 B; PCM/reset remain exact.
The original literal WB3.95 comparison patch is pinned to stage-3 commit
`aa928a00`, before this independent forced-pitch change.

## Final admission

The stages above record initial screens. All three flags remain optional and
default to zero. Each works independently; `--low-rates 7 --enable-nb4` enables
all five NB and five compact WB rates. LSP/LPC, IIR, pitch, folding and QMF
remain shared across rates.

| Feature | NB kbit/s | NB bytes/20 ms | WB kbit/s | WB bytes/20 ms | Raw WB storage kbit/s |
| --- | ---: | ---: | ---: | ---: | ---: |
| `SPEEX_ENABLE_NB1=1` | 2.15 | 6 | 3.95 | 10 | 4.0 |
| `SPEEX_ENABLE_NB8=1` | 3.95 | 10 | 5.75 | 15 | 6.0 |
| `SPEEX_ENABLE_NB2=1` | 5.95 | 15 | 7.75 | 20 | 8.0 |
| Always enabled NB3 | 8.0 | 20 | 9.8 | 25 | 10.0 |
| `SPEEX_ENABLE_NB4=1` | 11.0 | 28 | 12.8 | 32 | 12.8 |

Raw storage includes ignored padding. WB3.95 uses 79 meaningful bits, so
byte-aligned files occupy exactly 4.0 kbit/s. Files contain complete fixed-width
raw packets, with Ogg framing removed before playback.

The final all-features ASM mailbox images use **17248 B NB / 24750 B WB Flash**.
Enabling only NB2, NB8 or NB1 with WB and keeping NB4 disabled uses 18410,
19278 or 19716 B respectively. These include the test mailboxes, so are not
firmware-independent library-size estimates. Disabling the new flags reproduces
all four previous minimal ASM images byte for byte: 10598/12940 B NB and
17008/19806 B WB.

Natural-speech timings are frame-weighted over 16 complete Russian/English
recordings in the all-features image. The maximum includes coverage/padding.
These figures exclude timers, interrupts and input/output; the denominator is
320000 cycles per 20 ms at 16 MHz.

| Profile | Speech cycles/frame | Speech CPU | Maximum CPU |
| --- | ---: | ---: | ---: |
| NB2.15 | 112616 | 35.19% | 35.65% |
| NB3.95 | 102392 | 32.00% | 35.12% |
| NB5.95 | 101159 | 31.61% | 33.32% |
| WB3.95 | 267682 | 83.65% | 84.68% |
| WB5.75 | 244790 | 76.50% | 80.18% |
| WB7.75 | 245059 | 76.58% | 78.80% |

WB3.95 needs the noise/vocoder path and is slower than higher-rate modes.
Every PCM word is preserved: there is no quality tradeoff from narrower
arithmetic. NB matches unmodified fixed-point Xiph 1.2.1. WB matches the
independent compact Q7/16-tap oracle, still an approximation of full Xiph QMF.

The source-bound `reports/low-final-*.json` evidence covers:

- 10627 exact/reset frames for each new profile: 16 complete voice clips
  (6467 frames), 4096 constructed coverage frames and 64 padding frames.
  The four existing profiles pass another 41813 frames with all new flags
  enabled: **105575 raw decoder frames** in total.
- Each new WB mode passes all 10627 frames with unbroken history, production
  PWM/Timer1/Timer2/IRQ/queue code, and exact s16/PWM. Separate zero-load and
  9600-cycle/frame (3%) extra-work runs total **63762 frames**, with zero
  underruns. The 3% runs retain minimum queues 8/13/18 and free SRAM
  395/382/377 B for WB3.95/5.75/7.75. Packets are ready in RAM; external SPI
  latency is outside this admission.
- Internal-Flash slices for six new modes plus WB9.8/WB12.8: 1024 frames,
  timers/IRQ, 3% added work, zero underruns. Each 128-frame slice resets;
  these do not prove continuous long external-file playback.
- 1024 mixed-mode API frames per family, switching among 1/2/8/3/4. Invalid
  lengths, null pointers, unknown modes and bad HB headers are rejected before
  the next exact valid output (6144 NB / 7168 WB rejected calls). Padding,
  input immutability and reset replay are checked.
- Independent feature masks 1/2/4: 128 exact/reset WB frames each. C11 export
  compiles and links without `.S` or duplicate sources; the C decoder is not
  executed or timed in this admission.

AVR GCC 7.3.0, existing mixed Os/O2/O3, LTO/mcall-prologues/mrelax and avr8js
0.21.1 are used. Results are from ISA simulation, not a physical board or
analog output. DTX/PLC, stereo, enhancer, highpass, other HB modes and 32-kHz
ultra-wideband remain outside this restricted profile.

## Reproduce

Use the retained speech corpus, FFmpeg/libspeex and the independent Xiph
oracle built by `build_wb.py --cc ... --reference`. New tests expose `--help`:

```sh
python Codecs/Speex/AVR/tests/prepare_low_profiles.py --speech-root <speech-root> --oracle <oracle-executable>
python Codecs/Speex/AVR/tests/augment_low_profiles.py --corpus Codecs/Speex/AVR/build/low-corpus --oracle <oracle-executable>
python Codecs/Speex/AVR/tests/build_low_profiles.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_wb.mjs --firmware Codecs/Speex/AVR/build/low-final/wb395 --streams Codecs/Speex/AVR/build/low-corpus/wb395/streams --oracle Codecs/Speex/AVR/build/low-corpus/wb395/oracle
python Codecs/Speex/AVR/tests/check_low_disabled.py --avr-gcc avr-gcc
python Codecs/Speex/AVR/tests/check_low_features.py --avr-gcc avr-gcc
python Codecs/Speex/AVR/tests/verify_low_flash.py --avr-gcc avr-gcc --oracle <oracle-executable>
python Codecs/Speex/AVR/tests/audit_low_rates.py --corpus Codecs/Speex/AVR/build/low-corpus
```

`build_low_profiles.py --players --frame-load-cycles 9600 --out <directory>`
builds full-history WB players. Run `verify_wb_stream.mjs` with `--firmware`,
`--streams`, `--oracle` per profile. `prepare_low_mix.py` and `build_low_api.py`
prepare mixed input/firmware for `verify_low_api.mjs`. Audio media and firmware
binaries stay outside Git. The audit verifies retained source/report hashes.
