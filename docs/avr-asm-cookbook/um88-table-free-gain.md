# UM88: exact gain without the 256-byte table

Original project optimization, isolated against `41e456a9`. The figures below
exclude later control, initialization, pointer-binding, and IRQ optimizations.
[Machine-readable measurements](measurements/um88-table-free-gain.json) retain
the core hashes, arithmetic checks, active-IRQ results, and rejected variants.
No new third-party implementation was imported.

## Bounds and rounding

Each packed waveform nibble represents `q = nibble - 8`, with `q` in −8…7.
The envelope level `L` is 0…15, so `q*L` fits signed eight bits: −120…105.
Compute that exact product before applying the existing gain shifts.

An eight-voice raw group is bounded by −64…56; the independent oracle also
checks −64…63. Its gain is `floor(g*L/8)`, not truncation toward zero.
The old two-lookup decomposition is equivalent: writing `g = 8*a + b`,
with `0 <= b < 8`, gives `a*L + floor(b*L/8)`. The replacement forms the
signed 16-bit product, then performs three arithmetic right shifts. Subsequent
attenuation and both pan shifts retain their original order and rounding.

The portable C arithmetic helper uses four conditional additions:

```c
int16_t term = value, product = 0;
if (level & 1) product = term;
term += term; if (level & 2) product += term;
term += term; if (level & 4) product += term;
term += term; if (level & 8) product += term;
```

All intermediates fit `int16_t`; doubling by addition avoids undefined negative
left shifts. Arithmetic right shift follows the tested GNU AVR C behavior,
which the original implementation already required. The helper has no device
register or Flash access; waveform reads stay behind `storage.h`.

## Backend and ABI constraints

Target: ATtiny88 / AVR25, without hardware MUL, GNU ABI, AVR GCC 7.3.0,
`-Os -fno-jump-tables -ffunction-sections -fdata-sections -Wl,--gc-sections`.
The 16 MHz measurements refer to the MH-ET board's above-rating clock;
they do not establish an increased manufacturer speed rating for ATtiny88.
The same arithmetic is available through an explicitly selectable C fallback.
ASM is selected only by the real `__AVR_ATtiny88__` define together with
`UM_ENABLE_AVR_ASM=1`; C remains the default and is usable on that AVR itself.

The ASM wave-cache path uses an eight-bit four-bit-level product. Grouped
mixing uses a signed 16-bit shift/add product. The packed L/R return ABI,
callee-saved registers, zero register, phase updates, gain flags, raw-wave
mode, percussion, and both dictionary layouts remain unchanged. No state
field or hardware-memory access is added. The old `gain-table.inc` may remain
as a reference, but the selected implementation does not include or link it.

## Isolated size and timing

| Kernel | C, 8/16 MHz | ASM, 8/16 MHz |
|---|---:|---:|
| Indexed renderer and original table | 3068 / 3120 B | 2930 / 2982 B |
| Bounded gain and pointer-traversed C renderer | 2786 / 2838 B | 2710 / 2762 B |

The ASM gain change saves 220 core bytes and 224 bytes after song alignment.
C saves 282 bytes against the indexed baseline, or 270 bytes against a
pointer-traversed renderer that retains the table. These are code-size
measurements for the stated builds, not a general CPU speedup claim.

At 8 MHz, the four-held-voice C workload passes with either pointer renderer.
Its maximum render cost falls from 337 to 287 cycles, while the maximum
control burst rises from 11,153 to 12,433 cycles; minimum FIFO falls from
124 to 117 frames. Faster steady rendering does not imply cheaper control.

The indexed direct-multiply replacement was rejected: four held C voices
underrun after 0.131 s. Forced-inline shift/add without pointer traversal
also fails after 0.063 s. Their register allocation makes even the ordinary
render path slower. Pointer traversal is part of the selected C change.
A smaller direct-multiply pointer variant still renders slower than the
table pointer variant: 353 versus 337 cycles. The bounded helper avoids it.

## Independent correctness and active-IRQ admission

At **both** clocks, each selected backend passes 16,992 independent signed
mix cases, all four pans, 34,816 cached-wave cases, and 576 mono/stereo IRQ
cases. Checks include exact phases, gains, cached waves, wrap/empty queues,
callee-saved registers, nonzero-r1 ISR entry, and stack restoration.

The selected ASM is byte-identical to the arithmetic ASM used for these
complete active-IRQ audits on both boards:

| Workload | Ring bytes / dictionary | Baseline → candidate minimum FIFO | Baseline → candidate maximum cycles |
|---|---|---:|---:|
| Dense changes to all eight voices, every control tick | 128 / fast | 26 → 24 | Control: 19,574 → 19,942 |
| Same dense workload | 192 / compact9 | 58 → 56 | Control: 26,120 → 26,488 |
| Actual eight-voice grouped Mariachi, full ~31.16 s loop and restart | 128 / fast | 67 → 67 | Render: 482 → 494 |
| Same retained Mariachi score | 192 / compact9 | 117 → 117 | Render: 482 → 494 |

All checks preserve every expected control frame, tonal mix, interpolated
PWM frame, and percussion state, with no FIFO underrun or lost interrupt.
The dense control increase is 368 cycles; the real grouped-render increase
is 12 cycles. The buffer margins remain positive for these workloads.

A 128-byte nonnegative half-table was also checked. It saves only 102 ASM
bytes and raises dense control by 520 cycles; its FIFO minima are 23/55.
The full arithmetic replacement is smaller and has better dense margins.

The [isolated implementation patch](examples/um88-table-free-gain.patch)
applies to `41e456a9`, before the separately measured control/IRQ changes.
Reproduction uses `tools/test-universal-backends.mjs` with the isolated
`conformance-8000000` / `conformance-16000000` directories named in the JSON,
plus `tools/audit-universal-music.mjs` on each measured image directory.
`tools/test-universal-admission.py:fixture` supplies the unchanged dense score.
These are instruction/IRQ model results, not physical-silicon measurements.
Final combined firmware still requires its own complete admission and song audits.

References: [Microchip ATtiny48/88 datasheet](https://ww1.microchip.com/downloads/en/DeviceDoc/doc8008.pdf),
[AVR instruction set](https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-Instruction-Set-Manual-DS40002198A.pdf),
and the project's retained Microchip ATtiny_DFP 3.4.278 definitions.
