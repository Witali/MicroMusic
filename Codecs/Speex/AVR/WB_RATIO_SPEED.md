# Exact WB LPC-response division

Baseline `9772b0a4`, ATmega328P / AVR5, 16 MHz / 2 KB SRAM, AVR GCC 7.3.0,
existing Os/O2/O3 attributes, LTO, mcall-prologues and mrelax. All optional
lower rates and NB4 are linked. The explicitly enabled ASM backend is the
performance target; C remains explicitly selectable on the same AVR.

The ratio in `speex_wb_low_ready` now uses the bounded fifteen-step divider
shared by all five WB modes. It retains the original signed16 divisor cast
before rounding. No reciprocal approximation, coefficient quantization,
filter, QMF, sample format, state or public API changes. See the
[domain proof and scalar/IRQ measurements](../../../docs/avr-asm-cookbook/speex-lpc-ratio-divide.md)
and [source-bound scalar receipt](reports/wb-ratio-unit.json).

## Matched screen completed

The [screen receipt](reports/wb-ratio-screen.json) binds production sources,
input/oracle hashes, both frame traces, firmware and test tools. Every measured
frame is faster and every signed16 output/reset matches its previous reference.

| Mode | Frames per raw/IRQ run | Before cycles/frame | After | Decoder time saved |
| --- | ---: | ---: | ---: | ---: |
| WB3.95 | 1152 | 221014.277 | 220026.909 | 0.447% |
| WB5.75 | 1152 | 228225.476 | 227210.108 | 0.445% |
| WB7.75 | 1152 | 239774.986 | 238755.618 | 0.425% |
| WB9.8 | 249 | 230111.715 | 229080.181 | 0.448% |
| WB12.8 | 64 | 235892.062 | 234877.891 | 0.430% |

Every bare image grows **26 B**, with unchanged static SRAM; measured peak
stack falls **2 B**. These are full linked image costs, distinct from the new
72-byte leaf. Both C controls compile/link only: 31194 -> 31374 B (+180 B).
The 21-source generic C11 export also compiles/links; no complete C decoder
executes or is timed. The C size difference is a remaining secondary target.

Production timer/PWM runs cover another **3769 frames**, exact signed16 and
PWM, zero underruns and 990..1010-cycle sample intervals. Additional foreground
load remains 8% for WB3.95/9.8/12.8 and 3% for WB5.75/7.75. Minimum queues are
30/25/20/7/7 samples respectively. These runs use ready RAM packets and do not
measure external transport latency or physical-board/analog behavior.

The screen takes up to 64 initial frames from each available recording,
including all 18 low-rate streams per mode. Current worktrees lack the old
complete WB9.8/WB12.8 corpora. WB9.8 instead uses four historical published
ASM captures; WB12.8 uses the retained 2200-frame independent continuous SPI
corpus. Their provenance is explicit; no new independent WB9.8 oracle is claimed.

## Complete available-corpus validation

Both complete raw epochs pass **34869 frames each**: three full
10627-frame lower-rate corpora, 788 WB9.8 public-phrase/dialogue frames and
2200 WB12.8 continuous frames. Matching complete active-IRQ runs pass another
**34869 frames**, with exact signed16/PWM and zero underruns. There are no
resets inside a recording. All sample intervals remain 990..1010 cycles.
The [full receipt](reports/wb-ratio-full.json) binds sources, both per-frame
traces, all input/oracle hashes and loaded output evidence. Every raw frame
is faster; the original-corpus availability limits above still apply.

| Mode | Before cycles/frame | After | Decoder CPU at 16 MHz | Loaded min queue |
| --- | ---: | ---: | ---: | ---: |
| WB3.95 | 222570.328 | 221580.720 | 69.553% -> 69.244% | 30 |
| WB5.75 | 231269.798 | 230252.190 | 72.272% -> 71.954% | 25 |
| WB7.75 | 241189.073 | 240167.464 | 75.372% -> 75.052% | 20 |
| WB9.8 | 223849.484 | 222831.359 | 69.953% -> 69.635% | 7 |
| WB12.8 | 236755.899 | 235741.397 | 73.986% -> 73.669% | 6 |

These are paired whole-workload means, including coverage inputs in lower
rates; the mode workloads differ, so the CPU column is not a same-recording
comparison between bitrates. Savings are 989.608..1021.609 cycles/frame,
or 0.424..0.455% of decoder time. Flash, static SRAM and peak-stack changes
remain exactly those in the screen. Minimum free SRAM with loaded output
is 412/408/403/398/391 B. These ready-RAM checks establish this bounded simulator
admission; external SPI delivery and physical-board timing are not refreshed.
No firmware/gallery refresh or publication is part of this stage.

Reproduction uses a separate baseline checkout at `9772b0a4` and fresh ignored
`build/speed-next` output. `tests/run_wb_ratio_stage.py` has `prepare`, `build`,
`controls`, `raw` and `irq` phases; `--screen` limits each recording to 64 frames.
`prepare` takes `--low-corpus`, `--spi-corpus`, `--gallery-root` (the retained
three-phrase build) and `--dialogue-root`. Build both epochs with `--epoch
before|after --source-root <codec-root> --avr-gcc <pinned-gcc>`; `controls`
takes the baseline codec root, `--avr-gcc` and a host `--cc` for compile/link
only. The export destination must be fresh. Run raw/IRQ with `--node <node>`.

```sh
python Codecs/Speex/AVR/tests/audit_wb_ratio.py --check
python Codecs/Speex/AVR/tests/audit_wb_ratio_stage.py --screen
python Codecs/Speex/AVR/tests/audit_wb_ratio_stage.py --record
python Codecs/Speex/AVR/tests/audit_wb_ratio_stage.py
```

Next measured candidates remain open: a 16-bit remainder branch for smaller
divisors, exact finite NB1 pitch roots and shared-quarter HB interpolation.
Their isolated benefits are not yet whole-decoder admission.
