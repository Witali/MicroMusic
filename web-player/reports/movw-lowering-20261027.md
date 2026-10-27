# MOVW word-copy lowering

AVR MOVW now uses one `i32.load16_u` and one `i32.store16` for a register pair
stored in shared memory. Its previous lowering used two byte loads and two byte
stores. Bounded regions with cached register locals retain their two-local copy.
No instruction clock, IRQ, RESET, SREG or public-state boundary changes.

The [cookbook entry](../../docs/avr-asm-cookbook/movw-word-lowering.md) links the
official AVR instruction/device specifications and WASM binary/execution rules.
These are ordinary MVP operations, with no new runtime helper or JavaScript
callback. This is a bytecode-size/memory-traffic improvement; execution speed was
not measured and no hardware or real-time support is inferred.

## Exact historical comparison

The [verifier](../scripts/verify-movw-lowering.mjs) loads the actual compiler from
commit `6f95e913`, verifies all 39 other compiler-source graph inputs unchanged,
and uses the same current JS wrapper and native device for both emitted CPUs.
Every catalog manifest is unchanged. Non-MOVW instruction bodies, basic blocks
without MOVW, cached region bodies, wrappers and driver bodies remain
byte-identical. Captures also assert that neither CPU module is rebound during
execution, so a self-programming update cannot silently replace the historical
generator with the current generator.

Across the 12 entries in `firmware.json` and `hq4-firmware.json`, **44 of 48**
generated module/policy combinations shrink. The four `hq4-vinni` modules stay
byte-identical. Full hashes, module sizes and source identities are retained in
[the machine-readable evidence](movw-lowering-20261027.json).

| Policy | Variants | Smaller | Saved bytes per changed module |
| --- | ---: | ---: | ---: |
| Legacy | 12 | 11 | 112–882 |
| Full compatible | 12 | 11 | 88–915 |
| Resumable | 12 | 11 | 84–882 |
| Bounded regions with phase locals | 12 | 11 | 84–882 |

For example, `rhythmic`'s full-compatible module shrinks 167,750 → 167,501 bytes,
and its bounded/phase-local module shrinks 290,760 → 290,522 bytes. The latter
still contains uncached instruction/basic-block copies; the cached region code
itself is unchanged.

## Functional and integration checks

**26 new focused tests** cover all 256 legal register-pair combinations with
seven representative 16-bit values in seven execution policies. They verify
the independent expected copy, every other data byte, SREG, PC and one-cycle
cost. Other cases exercise accepted dependent blocks, odd ABI base alignment,
cached-region/public-entry state, source edits while suspended, RESET cancellation
and a tied Timer0 IRQ. A separate reviewer reproduced late source sampling with
both actual historical and candidate compilers; the new lowering retains that
existing project phase contract.

The default suite passes **2525/2525** and shared tools pass **61/61**, totalling
**2586**. The new tests and focused 67-case run are included in the default count,
not additional checks to add again. TAP hashes are pinned in the JSON report.

Three active-IRQ music cases each run 4096 frames at 48 kHz in both compatible and
physical modes. All 96 old/new checkpoints preserve exact PCM, pins/timestamps,
public CPU/device state, native diagnostics, data, EEPROM, Flash and IRQ frames.

| Firmware | Compatible IRQs / pin observations | Physical IRQs / pin observations |
| --- | ---: | ---: |
| rhythmic | 3198 / 6397 | 798 / 1597 |
| lumiere-stereo | 3198 / 8565 | 798 / 1877 |
| alicia | 3197 / 6395 | 797 / 1595 |

Policy differences and fuse startup account for different spans of active CPU
execution between modes; comparisons are strictly old/new within the same mode.
No output-equivalence claim compares these two model configurations to each other.

Production native WASM is unchanged: 124,505 bytes, SHA-256
`ad3e472582cbca5f7d0d57b7b17776c58a03f9b5f7eb89b55fda89ea84389fc7`.
The regenerated compiler identity is
`f9db0099f03d50657ee08e1e98ea10d6b4aab44bca0d0d734a302938ed67d505`.
The full-device checklist remains 24/31; this is partial progress on register
traffic, with no new peripheral coverage or closure of hardware-dependent items.

```text
node web-player/scripts/generate-avr-cache-identity.mjs --check
node --test web-player/tests/*.test.mjs
node --test tools/avr-music-target-core.test.mjs tools/music-startup.test.mjs
node web-player/scripts/verify-movw-lowering.mjs --output web-player/reports/movw-lowering-20261027.json --full-tap build/movw-full.log --shared-tap build/movw-shared.log
```

The TAP files above are ignored local logs from the recorded runs. Recreate them
when replaying the report; the verifier requires complete, entirely passing TAP.
