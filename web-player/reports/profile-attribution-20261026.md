# Validate sampled CPU/peripheral attribution

The diagnostic profiler now validates the complete V8 call tree, sample IDs and
delta stream before publishing its tables. A standalone offline auditor
reconstructs disjoint leaf counts, delta weights, mixed/unknown/support buckets,
work ancestry, non-work observations and a separately labelled caller-context
view. It exports no original frame URLs or compiler object paths.

Validation: **28/28 focused tests pass**, including existing actual WASM dispatch
name checks and 20 new attribution cases. Tree cycles, disconnected components,
duplicate parents, missing samples, malformed deltas and time overruns reject
the profile. A separate CLKI/GPIO/sleep audit passes 49/49 checks; it found no
confirmed device defect and supplies no new silicon timing evidence.

## Retained capture replay

```text
node --test web-player/tests/avr-profile-attribution.test.mjs web-player/tests/avr-profile-functions.test.mjs
node web-player/scripts/audit-device-profile.mjs --input build/profiles/bounded-current-music --out-file build/profiles/attribution-20261026.json
```

All **nine original captures / 8105 samples** reproduce every original all/work
leaf category and sample count. The [derived audit](profile-attribution-20261026.json)
records the exact raw-profile, function-metadata and normalized analyzer-source
hashes. Original inputs remain in the existing ignored capture directory; this
is an offline replay of the earlier bounded-region study, not fresh performance
data for the current runtime. Its native SHA-256 is
`9f1eefa094f9003419251408953309e3b3c4050fc217234b9b95ed0275d87778`.

For `rhythmic`, repeat 0, 1156 total samples include 1153 work-ancestry samples.
Of those, **832 are explicitly mixed native containers**. The first sample
arrived after 21,818 us; median recorded delta is 1562 us against a requested
1000 us; three deltas exceed twice that interval, with 133 us of profile tail
unrepresented. The recorded deltas describe collection intervals, not proven
ownership for the whole interval. Unknown/support frames and GC/VM observations
stay visible.

## Current producer smoke check

```text
node web-player/scripts/profile-device.mjs --kernel --clock physical --frequency 20000000 --frames 512 --repeats 1 --out-dir build/profiles/attribution-smoke-20261026
node web-player/scripts/audit-device-profile.mjs --input build/profiles/attribution-smoke-20261026 --out-file build/profiles/attribution-smoke-audit-20261026.json
```

The current O3 diagnostic rebuild is byte-identical to production before adding
its custom name section. Named/profiled physical capture matches production PCM
and architectural state; its 21 samples also replay exactly. The producer records
the new analyzer in its normalized source-hash inventory. This tiny smoke case
checks integration only, with no throughput or profiler-overhead conclusion.

Production native WASM remains 119010 bytes, SHA-256
`bea029bf125c9f8f6ee3e63197e9a9e15556f35d59464ec3ccd5199c137e0715`;
production libraries, generated compiler identity, peripheral ABI and engine
defaults are unchanged. No JavaScript instruction/edge callbacks were added.

Precise exclusive CPU/peripheral/pin durations, profiler overhead, active-IRQ
audio underruns and physical chip ambiguities remain open. Inlining prevents
closing them from these tables. The full-device checklist remains 23/30.
