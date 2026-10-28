# Complete host timing and paired v5 diagnostic evidence

The host runner now records every decode duration, including chains longer than
64,000 samples. This host-only change saves **0 B AVR Flash**. Its purpose is to
make timing comparisons complete and to reuse an unchanged linked image safely
when only its host validator changes.

The separate decoder comparison uses the fixed-tail baseline `b8f473a6` and final
decoder source **`5c7e0592`**, under the same diagnostic harness. On all 111 normal
images and five images with 100 additional cycles per audio IRQ, the final source
saves **218–222 B of full linked Flash** and **45 B of static SRAM**. Every complete
PWM output matches both the independent integer model and the frozen output;
there are no decoder errors or underruns. Normal weighted decode wall cycles
increase **5.619%**; the stress set increases **6.084%**. These size savings belong
to the decoder changes, not to host statistics.

| Diagnostic set | Images | Profiled samples | Mean cycles/sample, baseline → final | Max 160-sample sum, baseline → final |
| --- | ---: | ---: | ---: | ---: |
| Normal IRQ | 111 | 5,743,258 | 783.147 → 827.149 | 149,667 → 158,050 |
| Extra 100 cycles/IRQ | 5 | 723,264 | 806.812 → 855.899 | 153,245 → 162,995 |

`summary.json` retains full source, toolchain, host runner, loaded-library and
validator provenance. `rows.json` contains paired numerical results under
anonymous `diagnostic-NNN` identifiers. There are no recording names, private
paths, or per-recording stream, media, PCM/PWM or ELF fingerprints in this folder.
Private input/artifact bindings remain in ignored receipts; aggregate manifest
hashes identify the immutable inventory without disclosing its individual keys.

## What was corrected and checked

The former runner stored up to 64,000 durations in an array. The new
[`profile_durations.h`](../../validation/atmega328p/profile_durations.h) maintains
64-bit count/total/maximum, a 160-entry duration ring, and exact rolling 40/80/160
window maxima. It rejects count/total overflow before mutating statistics. The
runner labels current results `streaming-v2`. Its existing two-billion-cycle
simulation limit remains; this is not unlimited execution.

[`runner-equivalence.json`](runner-equivalence.json) records actual old/new
simavr execution of the **same existing AVR images**, without an AVR relink:

- At 8,000 samples, all prior report fields and the complete PWM output agree.
- At 281,632 samples, all non-duration fields and complete PWM agree. The old
  duration count is 64,000; the new count is 281,632, equal to produced, played
  and timer ticks, with no errors, underruns or statistics overflow.
- Historical capped reports require explicit `historical=True` or
  `--historical-runner`; they cannot silently become current full-coverage
  evidence. A capped average is never compared with a full-chain average here.

The compiled host statistics test checks 300,000 generated durations against
independent prefix/window calculations, including 64,000, 64,001 and 281,632
boundaries, values above 32 bits, reset and overflow without partial mutation.

## Build, inspection and host validation are separate

[`benchmark_speech_flash.py`](../../01_ACTIVE_Q0_CODEC/tools/benchmark_speech_flash.py)
and [`measure_speech_firmware.py`](../../01_ACTIVE_Q0_CODEC/tools/measure_speech_firmware.py)
retain three distinct identities:

1. **AVR build:** actual transitive compiled source, compiler/assembler/linker,
   vendor and GCC headers, startup/runtime libraries, compiler options, derived
   harness and exact generated stream header. The full source inventory also
   remains available for decoder/model correspondence.
2. **Artifact inspection:** inspection tools and proof implementation. A changed
   inspector rechecks sections, full linked `.text + .data`, SRAM and exact
   ordered embedded arrays without attributing a host change to AVR code.
3. **Host validation:** runner binary and C/header sources, actual `ldd`-resolved
   libraries, transitive local Python/model dependencies, Python/package versions
   and optional calling validator sources. A changed identity forces fresh
   simulation/model validation while retaining a valid unchanged AVR image.

[`cache-validation.json`](cache-validation.json) records the actual compact smoke:
one AVR link across the first run, an identical cache hit and a simulated host
provenance change that forces fresh validation without relinking. Legacy-only
C and explicit ASM paths were also validated; the C fallback's 364 underruns are
not a real-time admission. Separate unit cases mutate the binary, cost metadata,
PWM, timing JSON and verification metadata; stale evidence is not reused. They
also cover output escape/aliases, exact duplicate-array storage, changed source,
strict full coverage and explicit historical coverage. See the source-pinned
test inventory in [`validation-protocol.json`](validation-protocol.json).

## Measurement scope

Target: ATmega328P / AVR5 GNU ABI, AVR-GCC 7.3.0, 16 MHz CPU and 8 kHz audio.
The diagnostic image uses queue 512 / prefill 384, explicit supported AVR ASM,
unroll 1, tuning 0, `-Os -flto -mcall-prologues -mrelax`, v3 feature mask 24,
speech/compact enabled and compact-only parsing. The stress images add
`LPX4_PROFILE_IRQ_LOAD=100`; the common compiler-options list in `summary.json`
shows the normal setting. Vendor register headers remain separate from arithmetic
backend selection. The portable C fallback remains explicitly selectable.

Full Flash means the actual linked `.text + .data`, including encoded streams,
startup, queue/player and retained diagnostic counters/markers. Program Flash
is that total minus exact embedded stream bytes. SRAM is static `.data + .bss`.
Measured decode intervals include interrupts and diagnostic flag work. These
are **diagnostic firmware** figures, not the minimum production player footprint;
application-player savings require a separate production-image comparison.

The minimum observed queue is 386 for both sources. Minimum observed stack
margin rises from 893 to 939 B, **after `profile_ready`**. This is not a startup
or universal worst-case stack proof. simavr 1.6 is used; no physical board,
analog output, arbitrary interrupt load or unmeasured profile is admitted by
these results.

## Reproduction

Use Python 3.12 and the package/runtime versions pinned in `summary.json`, a
native C++ compiler for host tests, the pinned AVR-GCC installation and simavr
1.6 development libraries. Run from the repository root. The exact corpus and
immutable inventory must be supplied locally; they are intentionally excluded.
The inventory is the existing `timing/results.json`, `firmware/all-costs.json`,
`selection/results.json`, ordered stream files and frozen full PWM files.

On Linux, build the current host runner (WSL uses the same command with paths
translated and an optional library directory):

```sh
mkdir -p build/full-duration
gcc -O2 -std=c11 $(pkg-config --cflags simavr) \
  Codecs/LPX/validation/atmega328p/sim_profile.c \
  $(pkg-config --libs simavr) -o build/full-duration/sim_profile
```

Set `LPX_STUDY`, `LPX_BASELINE_SOURCE`, `LPX_FINAL_SOURCE` and `AVR_BIN` to local
paths. Source directories must match the corresponding source inventory in
`summary.json`; keep them immutable. Replay the same 111+5 jobs for each source:

```sh
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/validate_v5_runtime.py \
  --study "$LPX_STUDY" --source "$LPX_BASELINE_SOURCE" \
  --output build/full-duration/baseline --avr-bin "$AVR_BIN" \
  --runner build/full-duration/sim_profile --workers 3
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/validate_v5_runtime.py \
  --study "$LPX_STUDY" --source "$LPX_FINAL_SOURCE" \
  --output build/full-duration/final --avr-bin "$AVR_BIN" \
  --runner build/full-duration/sim_profile --workers 3
python Codecs/LPX/research/full-duration-runtime-2026-10-28/compare_diagnostics.py \
  build/full-duration/baseline build/full-duration/final build/full-duration/paired
```

Do not run the comparator with Python optimization flags: its validation uses
assertions. This exact saved comparator checks the private identity join and
exports only anonymous results. For Windows/WSL, add `--wsl Ubuntu --lib` with
the locally supplied simavr library directory. All output directories stay
inside the ignored repository `build/` directory.

For host runner equivalence, obtain the old runner source from commit
`d727211c:Codecs/LPX/validation/atmega328p/sim_profile.c`, compile both host
runners, and execute each as `runner same.elf valid.pcm8 timing.json` on unchanged
short/long images. Compare every old report field on the short image; on the
long image exclude only `decode_calls` and the five `decode_wall_cycles_*`
duration fields, then require exact full PWM, current complete counts and zero
errors/underruns. Source hashes and the measured lengths are retained in
`runner-equivalence.json`. Compiling a host runner does not relink the AVR ELF.

The focused suite can run with tools/tests directories on `PYTHONPATH`:

```sh
PYTHONPATH=Codecs/LPX/01_ACTIVE_Q0_CODEC/tools:Codecs/LPX/01_ACTIVE_Q0_CODEC/tests \
  python -m unittest test_profile_durations test_measurement_provenance \
    test_measure_speech_firmware test_select_speech_budget
```

The saved receipt records 21 passing tests. The runner and cache smoke are
separate actual AVR/simavr checks, not simulated by those unit-test mocks.
Host-runtime implementation commits: `fd71fb2d` and `b433623d`.
