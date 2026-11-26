# Baseline full-player hotspot pilot

This is a bounded CPU investigation made before admitting a new LSF format.
It does not claim that the format compresses better or has an AVR decoder.
Further codec implementation and the full matrix are paused pending the
eight-model encoder result.

`profile_existing.py` replays existing, unchanged LPX player ELFs using a
host-only instruction histogram in the original simavr observer. Every
production source hash is checked against the original build receipt first.
No firmware marker, profiling instruction, counter or state is added. The
original complete PWM and every original timing field must remain identical;
the flat PC counters must sum exactly to the original foreground decode count.

The four completed replays use `chego-p4` and `bread-p6` on ATtiny88 and
ATmega328P, explicit ASM, 16 MHz / 8 kHz, FIFO 32 / prefill 24, gain Q7=128,
the original Timer0/Timer1 recipe and active reserved-register sample IRQ.
They are simulations, not physical-board measurements. The existing baseline
ELFs were reused after verifying all their source hashes against this worktree.

| Flat instruction bucket | Tiny chego P4 | Tiny bread P6 | Mega chego P4 | Mega bread P6 |
| --- | ---: | ---: | ---: | ---: |
| Original decode cycles per sample | 1376.862 | 1316.696 | 612.826 | 616.222 |
| Bit readers, percent | 0.507 | 0.745 | 1.138 | 1.701 |
| LSF converter, percent | 3.274 | 3.418 | 4.084 | 4.054 |
| `prepareSubframe` self, percent | 1.367 | 1.466 | inlined | inlined |
| Separate attenuation helper, percent | 7.190 | 7.519 | inlined | inlined |
| Excitation leaf, percent | inlined | inlined | 9.737 | 9.552 |
| `main`, containing inlined DSP and control, percent | 87.662 | 86.852 | 85.007 | 84.654 |

These are **flat instruction shares**. Calls are charged to the containing
instruction, while callee bodies are charged to the callee. Inlined synthesis,
postfilter, excitation and control instructions remain in `main`; its share is
not a measurement of LPC multiplies alone. Reader shares include excitation
fields as well as spectral fields. Eliminating all reader work would therefore
be an optimistic ceiling for changes that only simplify LSF parsing.

Production already caches static spectra, converts segment anchors rather than
every subframe, rotates anchors, batches remaining counts and has specialized
AVR25/AVR5 sample paths. Preserving those paths avoids the generic-loop overhead
observed in the earlier LG1 experiment. The measurements favor investigating
per-sample work if a substantial CPU reduction is wanted, but they do not yet
identify an admitted new optimization. Potential arithmetic changes must keep
the exact per-product rounding, clipping and state updates; summing unrounded
products would change the waveform. No new assembly or production change is
introduced by this pilot.

[hotspots.json](hotspots.json) retains source/input/ELF/observer hashes, original
compiler options, exact counter-equivalence outcomes and all flat function
totals. Raw per-PC histograms, observers, ELFs and media stay under ignored
`build/`. For reproduction with an existing full-player case directory:

```sh
python3 Codecs/LPX/experimental/LSF1/avr/profile_existing.py \
  --case-run PATH_TO_EXISTING_CASE_DIRECTORY \
  --output build/lsf1-avr/fresh-profile
```

The input directory must contain the original `build.json`, `player.elf`,
`hardware.h`, `actual.pwm` and `timing.json`. The installed toolchain is the
existing GCC 13.3 / simavr 1.6 host binding with libelf, using no new downloaded
code. The firmware remains AVR-GCC 7.3.0 / GNU++11, explicit supported ASM,
actual manufacturer device definitions and the original selectable C fallback.

## Existing-setting CPU pilots on current LPX

After rejecting the new LSF packing, a separate authorized CPU pilot keeps the
best current LPX streams and original ROM producer. It changes only existing
explicit build settings. The eight full builds screen Tiny multiply unroll
4/8/16 and Mega function tuning 7 on both `chego-p4` and `bread-p6`. Function
tuning attributes are gated to actual AVR5, so they were not tested on Tiny.

All eight pass the complete portable-reference PWM, supplied PCM, active IRQ,
timing, EOF, FIFO and observed-stack admission checks. Input bytes are identical
to the hash-verified prior baselines. The six Tiny images are additionally
byte-identical to their baseline linked Flash images. Changing generic multiply
unroll has no effect on these specialized current-player builds.

| Explicit profile, both complete files | Decode CPU cycles/sample | Producer CPU cycles/sample | Program Flash change |
| --- | ---: | ---: | ---: |
| Tiny unroll 4, 8 or 16 versus 2 | 1337.071 → 1337.071 | 1358.071 → 1358.071 | 0 B |
| Mega function tuning 7 versus 0 | 615.072 → 680.184 | 637.072 → 703.184 | +172 B |

Means are total foreground CPU cycles divided by total corresponding successful
source-sample calls, with the same two full files on each side. Mega tuning 7
costs 10.59% more decode CPU and 10.38% more producer CPU. Its observed stack
grows from 24 to 42 bytes, with unchanged 417-byte static SRAM. Tiny remains at
418-byte static SRAM, 27-byte observed stack and 67-byte physical margin.

All pilot images fit physical Flash and the recorded bootloader application
regions. Tiny full images are 4100/5058 bytes, excluding audio 3578/3579 bytes;
Mega tuned full images are 3720/4676 bytes, excluding audio 3198/3197 bytes.
Observed minimum queue is 25–27, output spacing is 1997–2003 cycles and every
run has zero underruns. These are simulations on the same hardware recipe,
not physical boards or universal stack bounds.

No performance profile is selected, no default is changed, and no eight-file
follow-up matrix is run: the bounded screen found no useful speed improvement.
This does not reject untested compiler settings or new mathematical ideas.
[tuning-results.json](tuning-results.json) retains every full result, paired
baseline counters, input/output/image hashes and original compiler/source
receipts. `tune_current.py` reproduces the same bounded screen:

```sh
python3 Codecs/LPX/experimental/LSF1/avr/tune_current.py \
  --output build/lsf1-avr/tuning-pilot-v1 --jobs 2
```

It uses `build/lsf1-common/baselines.json`, verifies its inputs and production
sources against the retained admitted LPX baseline/provenance, freezes the
inputs in a fresh ignored directory, and invokes the unchanged production
builder/verifier. `--profiles` and `--cases` explicitly select a different
bounded set; untested selectors have no measurement claim here. The C arithmetic
implementation and actual AVR memory/device macros remain unchanged.
