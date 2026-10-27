# Verification virtual events: 10 ns acceptance

The full ATtiny13A verification simulator now has an executable acceptance
comparator for the user's 10 ns virtual-event requirement. It accepts at most
10,000 ps of absolute error per corresponding event. Event count/order and all
discrete fields remain exact. Site mode, unsafe timestamps and caller-supplied
tolerance changes reject; device/runtime time is not quantized or modified.

The [real-device-model replay](../scripts/verify-virtual-event-accuracy.mjs)
passes **41 scenarios / 17,890 compared events**, with maximum timestamp
difference **1 ps** against independently computed references. This is software
agreement under explicit fixtures, not measured accuracy of a physical chip.

| Fixture group | Scenarios | Compared events |
| --- | ---: | ---: |
| Internal clock checkpoints, irregular large spans | 3 | 27 |
| Timer0 CTC counter/sticky flags | 15 | 15,045 |
| Timer0 CTC OC0A output | 15 | 255 |
| Generated GPIO firmware, whole/partitioned | 6 | 1536 |
| Ideal external 20 MHz CLKI on PB3 | 1 | 1024 |
| Neighboring inputs beyond `2^53` ps under held RESET | 1 | 3 |

Internal source fixtures use 9,000,000, 9,600,000 and 9,696,000 Hz at a declared
OSCCAL point, D1 and a selected zero-startup profile. Rational references are
projected down onto integer picoseconds while native deadlines round upward;
this accounts for the observed 0–1 ps comparison difference. The checker never
normalizes traces to an observed initial edge or accumulates per-step tolerance.

CTC tests cover TOP 0/1/3/31/255. Starting at reset counter zero without writing
TCNT avoids compare blocking; the reference checks the full `1 + TOP` period,
delayed flag behavior and output toggle phase. The valid CTC TOP=0 case is
distinct from the still unresolved phase-correct WGM5 TOP=0 behavior.

The generated LDI/OUT/RJMP firmware drives PB0 according to official instruction
cycles, including DDR publication, then repeats its high/low pair every four
cycles. All 512 cycles retire the expected 385 instructions with exact GPR/PC/
SREG state. Whole execution and 31 irregular observation partitions preserve
complete public state, data, EEPROM and Flash. The CLKI fixture preserves 1024
source transitions, 512 CPU cycles and 256 loop retirements. The held-RESET
case retains all three neighboring transitions at absolute large timestamps.

See the [cookbook constraints and official references](../../docs/avr-asm-cookbook/verification-event-tolerance.md).
The [JSON report](virtual-event-accuracy-20261027.json) pins the source graph,
native build inputs, compiler identity, per-scenario reference/actual trace hashes
and completed focused TAP. The full verification policy is selected explicitly;
the simplified site model is never used as the reference.

**53/53 focused checks pass**, including 15 new comparator tests and the
existing configuration, physical-clock, CLKI and integrated Timer0 checks.
Negative cases cover the inclusive 10 ns endpoint, 10,001 ps failure, accumulating
drift, changed flags/cycles, missing/reordered edges, unsafe integer state and
outer/nested getters. Invalid getters execute zero times. No broad runtime suite
was repeated because no runtime source or binary changed.

```text
node --test web-player/tests/avr-verification-events.test.mjs web-player/tests/emulation-configurations.test.mjs web-player/tests/attiny13a-physical-clock.test.mjs web-player/tests/attiny13a-clki-clock.test.mjs web-player/tests/attiny13a-device-timer0.test.mjs
node web-player/scripts/verify-virtual-event-accuracy.mjs --output web-player/reports/virtual-event-accuracy-20261027.json --test-tap build/virtual-event-accuracy-tests.log
```

Retain the first command's output as the named ignored TAP file to regenerate
the evidence. Native WASM remains 124,505 bytes, SHA-256
`ad3e472582cbca5f7d0d57b7b17776c58a03f9b5f7eb89b55fda89ea84389fc7`;
compiler identity remains
`f9db0099f03d50657ee08e1e98ea10d6b4aab44bca0d0d734a302938ed67d505`.
No production source, binary, cache schema or engine default changes.

The supplied clock/pad timing choices are not measured silicon curves. These
fixtures do not establish 10 ns hardware accuracy for unknown analog, RESET,
CLKPR, debugWIRE or Timer0 modes. The full plan remains **24/31**, seven open;
the new tolerance does not close those evidence requirements.
