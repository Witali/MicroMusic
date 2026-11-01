# CLKPR switching no longer accumulates timestamp rounding

The internal-clock board cleared its numerator remainder whenever a pending
CLKPR change became active. At a fractional source period, this discarded the
progress past an exact edge that had been projected up onto an integer
picosecond. Repeated writes restarted from each rounded edge. A legal generated
/1→/2→/1 loop at 9 MHz drifted **14,223 ps** after 32,000 iterations / 64,000
switches, exceeding the verification model's maximum 10 ns software error.

The fix retains that source remainder when installing the new divider. It
changes no instruction, timer count, IRQ arbitration or selected transition
policy. Reset still initializes its own phase. See the
[independent source-period proof](../../docs/avr-asm-cookbook/verification-event-tolerance.md#preserve-the-source-remainder-across-a-prescaler-change).

Microchip [DS40002307A6.3.1](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf#page=33)
specifies a glitch-free switching interval and leaves the exact ripple phase
unpredictable. The retained T1+T2 lower-bound digital fixture is still explicit;
this correction does not establish physical CLKPR/RESET accuracy or close the
hardware measurement item. The main plan remains **24/31**, seven open.

## Verification

All **131/131 focused checks and 2723/2723 default tests pass**, without failures,
skips or cancellations.

The same final test source passes against the corrected native runtime and
fails 13 of 16 cases against the pinned historical runtime from `312df174`.
The three integer-period controls pass both versions. Current tests cover all
81 divider pairs in ordinary, verification and optimized execution; repeated
writes at 9 MHz, 11,000,003 Hz and 10 MHz; exact PC/cycle/retirement counts;
every CTC TOP0 Timer0 edge; and observations ±1 ps around a pending switch.

A separate current-native test performs 1000 fractional switches, checking the
exact numerator remainder, absolute rational time, Timer0 count and equality
between cached deadlines and the direct scanner. The historical whole-device
compatibility test now changes CLKPR at an integer-aligned source before the
fractional OSCCAL change. This preserves its unchanged-behavior comparison;
the old fractional CLKPR bug is covered by independent analytical expectations.

The extended [10 ns acceptance replay](virtual-event-accuracy-20261101.json)
passes **44 scenarios / 18,066 events**, with maximum error **1 ps** against
floor-projected analytical references. Added cases retain absolute time over
64,001 CLKPR writes and Timer0 output through /2↔/8 changes. There is no
per-step allowance or first-event alignment. These are software fixtures, not
silicon measurements or host execution-speed benchmarks.

The [before/after evidence](clkpr-phase-20261101.json) pins the final producer and
test sources, historical artifact, complete compiler/native input graphs and
TAP hashes. It checks unchanged generated CPU bytes and final data/Flash/EEPROM
for three clock fixtures. The [test index](clkpr-phase-tests-20261101.json)
records the completed focused/full suites and independent rebuild.

## Artifacts and compatibility

The import-free native runtime is **124666 bytes**, SHA-256
`6bf2a19266bba639461dcb9495919eaa5ec2c138f2354a448a1d4ea3e4ca7219`.
It retains the same 117 function exports, fixed two-page memory, 8192-byte stack
and 80-byte resumable context. Only native body184 changes, 524→515 bytes;
the other 217 function bodies are identical. The legacy `avr.wasm` is unchanged.

The loader URL and generated compiler/cache identity are refreshed. Persistent
translations are also partitioned by the native hash. Existing portable
packages retain their embedded runtime; rebuild a package with the corrected
native asset to obtain this correction. No external programming operation,
package schema, manufacturer definition or system installation is added.

```powershell
node web-player/scripts/generate-avr-cache-identity.mjs --check
node --test web-player/tests/attiny13a-clkpr-phase.test.mjs web-player/tests/device-deadline-cache.test.mjs
node --test web-player/tests/*.test.mjs
node web-player/scripts/verify-clkpr-phase.mjs --baseline 312df174
node web-player/scripts/verify-virtual-event-accuracy.mjs
node web-player/scripts/build-device-wasm.mjs --out-dir build/clkpr-phase-rebuild
```

Reuse the pinned compiler, manufacturer pack and official PDF in the existing
download registry. No new external download is needed.
