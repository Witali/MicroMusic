# Resume CPU APIs after manual-clock SPM completion

`step()`, instruction-counted `run()` and compatible `runBlock()` now refresh
changed Flash before their next fetch, and check again on return. Previously,
SPM completed by public `clock()` left the adapter bound to an old generation.
The native readiness guard correctly refused stale code, but these entry points
returned without executing anything. Calling a timed runner happened to repair
the binding; it should not be necessary to make a single CPU step work.

The fix is confined to the ATtiny13A adapter. Timed/audio runners keep their
existing refresh/retry loops; active instruction/IRQ continuations retain their
latched code. Invalid instruction limits still fail before compilation or clock
changes. Both monolithic and incremental linking work, including an initial
precompiled package. No native C/WASM, manufacturer definitions, peripheral
timing or default compilation policy changes.

The regression firmware performs a real page erase, buffer fill and page write
through SPM. A timed call stops during the second operation; `clock(100000)`
completes it. The test selects PC128 to check the very first public CPU entry at
the newly written code, without any host ROM mutation. Native generation is2,
while the old adapter remains bound to1. Previously `step` left r20=0 and
`run(2)`/`runBlock` returned0/false. Now r20 becomes0x5A immediately; two-instruction
runs also set r21=0xA5. PC and CPU-cycle deltas are exactly1 or2, physical
retirement deltas match, and EEPROM/debug state are preserved.

[Before](spm-entrypoints-20261026/before.txt):12 failures/3 passes with the new
15-case regression on baseline922ba5ac. [After](spm-entrypoints-20261026/after.txt):
all15 pass. Both clocks, both compilation policies, packages and invalid inputs
are covered. Physical timed-run counts also match the native retirement count
across ordinary SPM waits. The last two passing test labels were clarified after
the broad run, with all15 focused assertions rerun and no further runtime edits.

[Full suite](spm-entrypoints-20261026/full-summary.txt):1972 passes, no failures or
skips; the preceding focused integration run also passed78 tests. Source/native
hashes and individual regression outcomes are in
[the evidence record](spm-entrypoints-20261026/validation.json).
The native runtime remains119010bytes with SHA-256
`bea029bf125c9f8f6ee3e63197e9a9e15556f35d59464ec3ccd5199c137e0715`.
No performance or physical-chip measurement is claimed. Plan status remains
23/30, seven open; external ISP/HVSP/programmer interfaces remain excluded.

```text
node --test web-player/tests/attiny13a-spm-entrypoints.test.mjs
node --test web-player/tests/*.test.mjs tools/music-startup.test.mjs tools/avr-music-target-core.test.mjs
node web-player/scripts/generate-avr-cache-identity.mjs --check
```

Official basis: [Microchip DS40002307A, sections16.1–16.3](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf)
defines page erase/fill/write and CPU halting during erase/write. The JS
resumption bug and its repair are established by executable regression tests,
not inferred from a physical chip. The emitted instruction bytes are unchanged.
