# UM88: isolated exact timing/control candidates

These are research candidates, not changes to published firmware. The measured
baseline is mono UM88 at `0c306b1`, GNU AVR GCC 7.3.0, AVR25, `-Os`, standard
GCC ABI, explicit `UM_ENABLE_AVR_ASM=1`. No new assembly is introduced. C timing
and control remain selectable on AVR; device access stays in the platform.

The new [rational clock header](../../../ATtiny88/Music/universal/rational-clocks.h)
is unused by the production driver until explicitly included. It divides each
increment and threshold by a common divisor. At 8 MHz control becomes 3/320 and
the fractional percussion advance becomes 2/5; at 12 MHz they become 1/160 and
3/5. Every carry occurs at the same sample. Other clocks have an exact wide
fallback; counter width includes the value before threshold subtraction.
The header supports 16 MHz mathematically; no 16 MHz firmware was validated here.

[Pointer-based um_tick](um88-tick-pointer.c.inc) replaces repeated `voice[i]`
address products by a pointer walk and hoists `1<<tickPhase` once per tick.
Envelope-before-event ordering, WAIT, LOOP, cached wave rules and phase stay
unchanged. Adapt only the function body when integrating with a different decoder.

The [main-loop patch](um88-rational-clocks.patch) targets the parallel stereo
integration snapshot's `platform.c`, UTF-8/LF SHA-256
`c05e47e5595f9dc82502ca0036fae8a29c721486e721ad71a9ca313a62c40cf6`.
It passed read-only `git apply --check` there. It intentionally does not replace
the interpolator, stereo branch or bootloader startup. Copy the header into the
same source directory first. For this mono baseline, the runner applies the
same exact text substitutions to a private copy instead of applying this patch.

Measured full polyphony-study loop plus restart, IRQ active, at 8 MHz:

| Candidate | Busy cycles/sample including IRQ | Engine bytes | Max control cycles | Minimum FIFO frames |
|---|---:|---:|---:|---:|
| Baseline | 738.190 | 2676 | 18410 | 98 |
| Short exact clocks | 715.526 | 2604 | 18410 | 98 |
| Clocks + pointer control | 700.332 | 2534 | 16406 | 108 |

The dense eight-voice fixture improves 924.996 → 887.965 busy cycles/sample;
control 19246 → 17854, FIFO94 → 101. The same unchanged-score PWM oracle passes
at 8 and 12 MHz and 8388608 Hz. This is measured model evidence for those
workloads, not proof for arbitrary scores or another runtime.

An additional `aligned(64)` → `aligned(1)` private experiment changes no active
cycles but saves 12 bytes of padding. In dense playback FIFO end704 → 692,
minimum SP733 and margin29 → 41 after the control candidate. It must not be
combined blindly with an ISR that assumes a fixed page/alignment. It is not
included in the timing patch.

Reproduce without modifying release sources or generated ROM/catalog files:

```text
python tools/test-universal-clock-ratios.py
python tools/review-universal-algorithm.py --report build/universal/algorithm-review/review.json
```

The runner copies original source/vendor files into an ignored temporary tree,
builds every candidate there, executes complete specified loops through the
independent PWM/phase/percussion oracle, then measures an instruction-level cycle
ledger. The profiler separates rejected FIFO polls from useful work and includes
all IRQ entry cycles. It targets the mono ABI of this baseline; a new packed
stereo/compact decoder requires its own integration measurements. Physical
hardware, all long retained songs and every C fallback profile were not tested
for these candidates. Published firmware remains unchanged.
