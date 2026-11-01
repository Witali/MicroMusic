# Archived optional direct S15 parser

This is a reproducible research artifact, not production integration or
ready-to-flash firmware. `s15-direct.patch` preserves the exact measured
two-file patch. It applies atop SRAM512 profile commit
`28620b5f16e3a698fb4085f1edea9e7d43847d24`; all 11 base files were checked
byte-for-byte against the original private source copy. The patch adds
`LPX4_ENABLE_S15`, default 0, and requires compact-only when 1. The copied
Math, arithmetic backends and SRAM512 workspace remain unchanged.

The original patch has CRLF line endings. The archive retains those bytes
unchanged. `reproduce.py` normalizes a disposable patch and the two touched
source files to LF before applying with `core.autocrlf=false`. This was
checked to reproduce the measured `.h/.cpp` exactly; it does not modify
the archived patch or production source.

The parser accepts version 8 / mode 15 and320/320 geometry. An existing internal
profile bit marks S15/P6 without adding RAM. Parameters are read once/320;
one 7-bit pulse is read/80, with the corresponding80-sample phase. Standard
v5 flag validation remains strict. At the final useful sample, unused
final-packet pulse fields are drained and extra bytes/nonzero padding are
rejected, including on partial 20-sample tails. No extra output is generated.

## Recorded measurement

`measurement.json` is a sanitized projection of the completed source-bound
private native/build/timing receipts. It contains no source audio, private
paths, input identifiers/fingerprints, runtime closure, logs or binaries.
It describes the existing observation, not a fresh run of these portable
reproduction scripts.

- Flash: **4743 program/test-harness +417 audio =5160 bytes**. Startup,
  lookup tables, retained v5 support, marker stores, loop and final image
  padding are included. S15 adds 332 bytes versus the same flag-off image;
  flag-off is byte-identical to the unmodified baseline.
- Static RAM: 403 bytes, comprising 398-byte decoder and 5 marker bytes;
  S15 adds no persistent RAM. Observed stack 54 bytes and conservative gap
  to BSS 54 bytes apply to this workload, without IRQs.
- Complete 19200-sample PWM is native-exact. 113019079 cycles give
  5886.410364583333 cycles/sample; maximum output gap 44277 cycles.
- Native checks cover memory profiles 0/1 and LPC segments 1/2/4: 500 full
  domain comparisons, 7680 partial-tail domain checks, 282 malformed
  rejections and 6 copy/assignment probes. Default-segment output also
  matches both original expansion references and the independent model.

**This is not real-time 8 kHz admission.** The mean exceeds the 2000-cycle
budget at 16 MHz. There is no IRQ-active player, queue, transport or underrun
proof. No ready HEX is provided or implied. No encoder search is needed.

## Reproduction

Run from a repository checkout containing the named base commit and this
artifact. Supply existing host Python dependencies (NumPy, Numba, SoundFile
and the active codec metric dependencies) and your own compiler paths.
The output must be a fresh directory under ignored `build/`. The source
audio/stream remains an external input to this artifact; do not add it here.

First check/apply the archived patch only, with no compilation or simulation:

```sh
python Codecs/LPX/research/lpx-s15-2026-11-01/target_probe/reproduce.py \
  --repo . --output build/s15-reproduction
```

For the measured 417-byte / 19200-sample S15 example, use a fresh directory
and add `--build --input PATH_TO_LOW15_LPX --compiler PATH_TO_AVR_GXX`.
The recipe uses AVR-GCC 7.3.0, C, SRAM512, LPC segments 2 and the flags in
the numeric receipt. The measured builds used the installed toolchain's
Atmel `avr/iotn88.h` (revision 2225, 2011-03-02) through `<avr/io.h>`, with
AVR-LibC 2.0.0 (20150208). The retained short vendor include path does not
exist and supplied no headers; the repository's ATtiny_DFP 3.4.278 was not
consumed. Matching the historical numbers requires the same actual headers
and linked runtime. The script writes only ignored copied sources, logs, maps and ELF/bin/nm;
checks the unique exact audio array; and compares flag-off final binaries.
Other compiler revisions/layouts may produce different sizes.

Native validation of a prepared directory:

```sh
python Codecs/LPX/research/lpx-s15-2026-11-01/target_probe/verify_direct.py \
  --repo . --output build/s15-reproduction --input PATH_TO_LOW15_LPX \
  --compiler PATH_TO_HOST_GXX
```

The validator reads the two existing public compact/quality streams as v5
controls, creates synthetic tails/malformed inputs, and writes the complete
`actual-m1-expected.pwm` oracle. If the original two expansion DLLs are
available unchanged, `--legacy-expansion-dir` adds that historical bridge;
otherwise those 8 historical domain comparisons are explicitly absent.
The independent current model/common/v5 reference checks still run.

After native PASS and the target build, optional instruction-step timing:

```sh
node Codecs/LPX/research/lpx-s15-2026-11-01/target_probe/time_target.mjs \
  build/s15-reproduction .
```

This uses the repository's existing Tiny88 transpiled CPU without block or
flag optimization, stops at the completion marker, checks stack/BSS bounds
and compares every PWM byte with the native oracle. Generated fingerprints
and runtime source/image bindings stay in ignored private receipts. Changing
inputs or simulator/compiler revisions is a new measurement, not a claim
that the historical numeric receipt has been reproduced exactly.
